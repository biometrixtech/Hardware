from models.accessory import Accessory
from exceptions import ApplicationException, InvalidSchemaException, NoSuchEntityException, UnauthorizedException
from flask import request, Blueprint
from datetime import datetime
import boto3
import os

from decorators import authentication_required
from models.firmware import Firmware
from models.sensor import Sensor

app = Blueprint('accessory', __name__)


@app.route('/<mac_address>/register', methods=['POST'])
def handle_accessory_register(mac_address):
    accessory = Accessory(mac_address)
    accessory.create(request.json)
    return {"status": "success"}, 201


@app.route('/<mac_address>', methods=['GET'])
@authentication_required
def handle_accessory_get(mac_address):
    print('should be authenticated')
    accessory = Accessory(mac_address).get()
    return {'accessory': accessory}


@app.route('/<mac_address>', methods=['PATCH'])
@authentication_required
def handle_accessory_patch(mac_address):
    accessory = Accessory(mac_address)
    if not accessory.exists():
        ret = accessory.create(request.json)
    else:
        ret = accessory.patch(request.json)
    return ret


@app.route('/<mac_address>/login', methods=['POST'])
def handle_accessory_login(mac_address):
    if 'password' not in request.json:
        raise InvalidSchemaException('Missing required request parameters: password')
    accessory = Accessory(mac_address)
    return {
        'username': mac_address,
        'authorization': accessory.login(request.json['password'])
    }


@app.route('/<mac_address>/sync', methods=['POST'])
@authentication_required
def handle_accessory_sync(mac_address):
    res = {}

    for required_parameter in ['event_date', 'accessory', 'sensors']:
        if required_parameter not in request.json:
            raise ApplicationException(400, 'InvalidSchema', 'Missing required request parameters: {}'.format(required_parameter))

    # event_date must be in correct format
    try:
        datetime.strptime(request.json['event_date'], "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ApplicationException(400, 'InvalidSchema', "event_date parameter must be in '%Y-%m-%dT%H:%M:%SZ' format")

    accessory = Accessory(mac_address)
    res['accessory'] = accessory.patch(request.json['accessory'])

    res['sensors'] = []
    for sensor in request.json['sensors']:
        # TODO work out how we're actually persisting this data
        res['sensors'].append(sensor)

    # Save the data in a time-rolling ddb log table
    _save_sync_record(mac_address, request.json['event_date'], res)

    res['latest_firmware'] = {
        'accessory_version': Firmware('accessory', 'latest').get()['version'],
        'sensor_version': Firmware('sensor', 'latest').get()['version']
    }
    return res


def _save_sync_record(mac_address, event_date, body):
    item = {
        'accessory_mac_address': mac_address.upper(),
        'event_date': event_date,
    }
    accessory_fields = Accessory(mac_address).get_fields(immutable=False, primary_key=False)
    for k in accessory_fields:
        if k in body['accessory']:
            item['accessory_{}'.format(k)] = body['accessory'][k]
    for i in range(len(body['sensors'])):
        sensor = Sensor(body['sensors'][i]['mac_address'])
        sensor_fields = sensor.get_fields(primary_key=True) + sensor.get_fields(immutable=False)
        for k in sensor_fields:
            if k in body['sensors'][i]:
                item['sensor{}_{}'.format(i + 1, k)] = sensor.cast(k, body['sensors'][i][k])

    dynamodb_resource = boto3.resource('dynamodb').Table(os.environ['DYNAMODB_ACCESSORYSYNCLOG_TABLE_NAME'])
    dynamodb_resource.put_item(Item=item)
