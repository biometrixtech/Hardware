from datetime import datetime, timedelta
from flask import request, Blueprint
import boto3
from boto3.dynamodb.conditions import Key
import os

from fathomapi.api.config import Config
from fathomapi.comms.service import Service
from fathomapi.utils.decorators import require
from fathomapi.utils.exceptions import InvalidSchemaException, NoSuchEntityException, DuplicateEntityException
from fathomapi.utils.xray import xray_recorder
from fathomapi.utils.formatters import format_datetime, parse_datetime
from models.accessory import Accessory
from models.firmware import Firmware
from models.sensor import Sensor
from models.accessory_data import AccessoryData

app = Blueprint('accessory', __name__)
PREPROCESSING_API_VERSION = '2_0'
USERS_API_VERSION = '2_4'


@app.route('/<mac_address>/register', methods=['POST'])
@xray_recorder.capture('routes.accessory.register')
def handle_accessory_register(mac_address):
    xray_recorder.current_subsegment().put_annotation('accessory_id', mac_address)
    accessory = Accessory(mac_address)
    accessory.create(request.json)
    try:
        AccessoryData(mac_address).create(request.json)
    except DuplicateEntityException as e:  #if there's one already do nothing
        print(e)

    return {"status": "success"}, 201


@app.route('/<mac_address>', methods=['GET'])
@require.authenticated.any
@xray_recorder.capture('routes.accessory.get')
def handle_accessory_get(mac_address):
    xray_recorder.current_subsegment().put_annotation('accessory_id', mac_address)
    accessory = Accessory(mac_address).get()
    res = {}
    res['accessory'] = accessory
    res['latest_firmware'] = {}
    for firmware_type in ['accessory']:
        try:
            res['latest_firmware'][f'{firmware_type}_version'] = Firmware(firmware_type, 'latest').get()['version']
        except NoSuchEntityException:
            res['latest_firmware'][f'{firmware_type}_version'] = None

    return res


@app.route('/<mac_address>', methods=['PATCH'])
@require.authenticated.any
@xray_recorder.capture('routes.accessory.patch')
def handle_accessory_patch(mac_address):
    xray_recorder.current_subsegment().put_annotation('accessory_id', mac_address)
    accessory = Accessory(mac_address)
    if not accessory.exists():
        ret = accessory.create(request.json)
    else:
        ret = accessory.patch(request.json)
    return ret


@app.route('/<mac_address>/login', methods=['POST'])
@require.body({'password': str})
@xray_recorder.capture('routes.accessory.login')
def handle_accessory_login(mac_address):
    xray_recorder.current_subsegment().put_annotation('accessory_id', mac_address)
    accessory = Accessory(mac_address)
    return {
        'username': mac_address,
        'authorization': accessory.login(request.json['password'])
    }


@app.route('/<mac_address>/sync', methods=['POST'])
@require.authenticated.any
@require.body({'event_date': str, 'accessory': str, 'sensors': list})
@xray_recorder.capture('routes.accessory.sync')
def handle_accessory_sync(mac_address):
    xray_recorder.current_subsegment().put_annotation('accessory_id', mac_address)
    res = {}

    # event_date must be in correct format
    # try:
    #     format_datetime(request.json['event_date'])
    # except ValueError:
    #     raise InvalidSchemaException("event_date parameter must be in '%Y-%m-%dT%H:%M:%SZ' format")

    event_date = format_datetime(datetime.utcfromtimestamp(Config.get('REQUEST_TIME') / 1000))
    request.json['accessory']['last_sync_date'] = event_date
    accessory = Accessory(mac_address)
    res['time'] = request.json.get('time', {})
    if 'local' in res['time']:
        request.json['accessory']['local_time'] = res['time']['local']
    if 'true' in res['time']:
        request.json['accessory']['true_time'] = res['time']['true']
    res['accessory'] = accessory.patch(request.json['accessory'])
    if 'true_time' in res['accessory']:
        del res['accessory']['true_time']
    if 'local_time' in res['accessory']:
        del res['accessory']['local_time']

    
    res['sensors'] = []
    for sensor in request.json['sensors']:
        # TODO work out how we're actually persisting this data
        res['sensors'].append(sensor)

    res['wifi'] = request.json.get('wifi', {})

    # Save the data in a time-rolling ddb log table
    _save_sync_record(mac_address, event_date, res)

    result = {}
    result['latest_firmware'] = {}
    for firmware_type in ['accessory', 'ankle', 'hip']:  #, 'sensor']:
        try:
            result['latest_firmware'][f'{firmware_type}_version'] = Firmware(firmware_type, 'latest').get()['version']
        except NoSuchEntityException:
            result['latest_firmware'][f'{firmware_type}_version'] = None

    user_id = res['accessory']['owner_id']
    if user_id is not None:
        if 'battery_level' in res['accessory'] and res['accessory']['battery_level'] < .3:
            notify_user_of_low_battery(user_id)
        try:
            result['last_session'] = get_last_session(user_id)

            if result['last_session'] is not None:
                result['last_session'] = correct_clock_drift(result['last_session'], mac_address)
        except Exception:
            result['last_session'] = None
            return result, 503
    else:
        result['last_session'] = None
    return result


@app.route('/<mac_address>/check_sync', methods=['POST'])
@require.authenticated.any
@xray_recorder.capture('routes.accessory.check_sync')
def handle_accessory_check_sync(mac_address):
    # TODO: Remove this
    if mac_address.upper() == "3C:A0:67:57:26:9A":
        mac_address = "3C:A0:67:57:26:99"
    elif mac_address.upper() == "3C:A0:67:57:2B:F8":
        mac_address = "3C:A0:67:57:2B:F7"
    xray_recorder.current_subsegment().put_annotation('accessory_id', mac_address)
    seconds_elapsed = request.json['seconds_elapsed']
    end_time = datetime.utcfromtimestamp(Config.get('REQUEST_TIME') / 1000) + timedelta(seconds=10)
    start_time = end_time - timedelta(seconds=seconds_elapsed + 20)
    start_date_time = format_datetime(start_time)
    end_date_time = format_datetime(end_time)
    print(start_date_time, end_date_time)
    if sync_in_range(mac_address.upper(), start_date_time, end_date_time):
        return {'sync_found': True}
    else:
        return {'sync_found': False}


@xray_recorder.capture('routes.accessory._save_sync_record')
def _save_sync_record(mac_address, event_date, body):
    item = {
        'accessory_mac_address': mac_address.upper(),
        'event_date': event_date,
    }
    accessory_fields = Accessory(mac_address).get_fields(immutable=False, primary_key=False)
    for k in accessory_fields:
        if k in body['accessory'] and body['accessory'][k] is not None:
            item['accessory_{}'.format(k)] = body['accessory'][k]
    for i in range(len(body['sensors'])):
        if len(body['sensors'][i]['mac_address'].split(":")) == 4:
            body['sensors'][i]['mac_address'] += ":00:00"
        sensor = Sensor(body['sensors'][i]['mac_address'])
        sensor_fields = sensor.get_fields(primary_key=True) + sensor.get_fields(immutable=False)
        for k in sensor_fields:
            if k in body['sensors'][i]:
                item['sensor{}_{}'.format(i + 1, k)] = sensor.cast(k, body['sensors'][i][k])

    if 'tasks' in body['wifi']:
        item['wifi_tasks'] = body['wifi']['tasks']
    if 'job' in body['wifi']:
        item['wifi_job'] = body['wifi']['job']
    if 'weak' in body['wifi']:
        item['wifi_weak'] = body['wifi']['weak']
    if 't_weak' in body['wifi']:
        item['wifi_t_weak'] = body['wifi']['t_weak']
    if 'na' in body['wifi']:
        item['wifi_na'] = body['wifi']['na']
    if 't_na' in body['wifi']:
        item['wifi_t_na'] = body['wifi']['t_na']

    if 'local' in body['time']:
        item['local_time'] = body['time']['local']
    if 'true' in body['time']:
        item['true_time'] = body['time']['true']

    dynamodb_resource = boto3.resource('dynamodb').Table(os.environ['DYNAMODB_ACCESSORYSYNCLOG_TABLE_NAME'])
    dynamodb_resource.put_item(Item=item)


def get_last_session(user_id):
    preprocessing_service = Service('preprocessing', PREPROCESSING_API_VERSION)
    endpoint = f"user/{user_id}/last_session"
    resp = preprocessing_service.call_apigateway_sync(method='GET',
                                                      endpoint=endpoint)
    return resp['last_session']


def correct_clock_drift(last_session, accessory_id):
    if 'last_true_time' in last_session:
        last_true_time = last_session.get('last_true_time')
        del last_session['last_true_time']
        if last_true_time is not None:
            event_date, offset_applied = apply_clock_drift_correction(accessory_id,
                                                                      last_session['event_date'],
                                                                      last_true_time)
            last_session['event_date'] = event_date
            session_id = last_session['id']
            # TODO: preprocessing does not have async queue
            patch_session(session_id, offset_applied)
    return last_session


def apply_clock_drift_correction(accessory_id, event_date, true_time_sync_before_session):
    next_sync = get_next_sync(accessory_id, event_date)
    offset_applied = 0
    try:
        if next_sync is not None:
            event_date *= 1000  # convert to ms resolution
            # get values for first sync after session
            true_time_sync_after_session = next_sync['true_time']
            local_time_sync_after_session = next_sync['local_time']
            # get total error
            error = local_time_sync_after_session - true_time_sync_after_session
            # get time difference between events
            time_elapsed_since_last_sync = event_date - true_time_sync_before_session
            time_between_syncs = true_time_sync_after_session - true_time_sync_before_session
            min_time = 8 * 3600 * 1000
            if time_between_syncs > min_time and time_elapsed_since_last_sync > min_time:  # make sure enouth time has passed
                offset_applied = round(time_elapsed_since_last_sync / time_between_syncs * error, 0)
                event_date += offset_applied
            else:
                print("recently synced, do not need to update")
            event_date = int(event_date / 1000)  # revert back to s resolution
    except Exception as e:
        print(e)
    return event_date, offset_applied


def get_next_sync(accessory_id, event_date):
    try:
        dynamodb_resource = boto3.resource('dynamodb').Table(os.environ['DYNAMODB_ACCESSORYSYNCLOG_TABLE_NAME'])
        event_date_string = datetime.utcfromtimestamp(event_date).strftime("%Y-%m-%dT%H:%M:%SZ")
        result = dynamodb_resource.query(KeyConditionExpression=Key('accessory_mac_address').eq(accessory_id.upper()) &\
                                                                Key('event_date').gt(event_date_string))['Items']
        if len(result) > 0:
            result = sorted(result, key=lambda k: k['event_date'])
            next_sync = result[0]
            try:
                return {
                    'true_time': float(next_sync.get('true_time')),
                    'local_time': float(next_sync.get('local_time'))
                }
            except TypeError as e:
                print(e)
    except Exception as e:  # catch all exceptions
        print(e)
    return None


def patch_session(session_id, offset_applied):
    try:
        endpoint = f"session/{session_id}"
        preprocessing_service = Service('preprocessing', PREPROCESSING_API_VERSION)
        preprocessing_service.call_apigateway_sync(method='PATCH',
                                                    endpoint=endpoint,
                                                    body={'start_time_adjustment': offset_applied}
                                                    )
    except Exception as e:
        print(e)


def sync_in_range(accessory_id, start_date_time, end_date_time):
    try:
        dynamodb_resource = boto3.resource('dynamodb').Table(os.environ['DYNAMODB_ACCESSORYSYNCLOG_TABLE_NAME'])
        kcx = Key('accessory_mac_address').eq(accessory_id.upper()) & \
              Key('event_date').between(start_date_time, end_date_time)
        result = dynamodb_resource.query(KeyConditionExpression=kcx)['Items']
        if len(result) > 0:
            return True
    except Exception as e:  # catch all exceptions
        print(e)
    return False


def notify_user_of_low_battery(user_id):
    users_service = Service('users', USERS_API_VERSION)
    body = {"message": "Your FathomPRO kit is about to die!!!! Go charge it now!!!!!",
            "call_to_action": "VIEW_PLAN"}
    users_service.call_apigateway_async(method='POST',
                                        endpoint=f'/user/{user_id}/notify',
                                        body=body)
