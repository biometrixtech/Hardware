from datetime import datetime
from flask import request, Blueprint
import boto3
import os

from fathomapi.comms.service import Service
from fathomapi.utils.decorators import require
from fathomapi.utils.exceptions import InvalidSchemaException, NoSuchEntityException, DuplicateEntityException
from fathomapi.utils.xray import xray_recorder
from models.accessory import Accessory
from models.firmware import Firmware
from models.sensor import Sensor
from models.accessory_data import AccessoryData

app = Blueprint('accessory', __name__)
PREPROCESSING_API_VERSION = '2_0'


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
    try:
        datetime.strptime(request.json['event_date'], "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise InvalidSchemaException("event_date parameter must be in '%Y-%m-%dT%H:%M:%SZ' format")

    request.json['accessory']['last_sync_date'] = request.json['event_date']
    accessory = Accessory(mac_address)
    res['accessory'] = accessory.patch(request.json['accessory'])
    
    res['sensors'] = []
    for sensor in request.json['sensors']:
        # TODO work out how we're actually persisting this data
        res['sensors'].append(sensor)

    res['wifi'] = request.json.get('wifi', {})
    res['time'] = request.json.get('time', {})

    # Save the data in a time-rolling ddb log table
    _save_sync_record(mac_address, request.json['event_date'], res)

    result = {}
    result['latest_firmware'] = {}
    for firmware_type in ['accessory', 'ankle', 'hip']:  #, 'sensor']:
        try:
            result['latest_firmware'][f'{firmware_type}_version'] = Firmware(firmware_type, 'latest').get()['version']
        except NoSuchEntityException:
            result['latest_firmware'][f'{firmware_type}_version'] = None

    user_id = res['accessory']['owner_id']
    if user_id is not None:
        try:
            preprocessing_service = Service('preprocessing', PREPROCESSING_API_VERSION)
            endpoint = f"user/{user_id}/last_session"
            resp = preprocessing_service.call_apigateway_sync(method='GET',
                                                              endpoint=endpoint)
            result['last_session'] = resp['last_session']
        except:
            result['last_session'] = None
            return result, 503
    else:
        result['last_session'] = None
    return result


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
