from aws_xray_sdk.core import xray_recorder, patch_all
import boto3
import datetime
import json
import os
import sys
import uuid

from accessory import Accessory
from exceptions import ApplicationException, InvalidSchemaException, NoSuchEntityException
from firmware import Firmware
from flask import request
from flask_lambda import FlaskLambda
from sensor import Sensor
from serialisable import json_serialise

patch_all()


app = FlaskLambda(__name__)


@app.route('/v1/accessory/<mac_address>/register', methods=['POST'])
def handle_accessory_register(mac_address):
    print(request.json)
    accessory = Accessory(mac_address)
    accessory.create(request.json)
    return '{"status": "success"}', 201


@app.route('/v1/accessory/<mac_address>/login', methods=['POST'])
def handle_accessory_login(mac_address):
    if 'password' not in request.json:
        raise InvalidSchemaException('Missing required request parameters: password')
    accessory = Accessory(mac_address)
    return json.dumps({
        'username': mac_address,
        'authorization': accessory.login(request.json['password'])
    }, default=json_serialise)


@app.route('/v1/accessory/<mac_address>/sync', methods=['POST'])
def handle_accessory_sync(mac_address):
    res = {}

    if 'event_date' not in request.json:
        raise ApplicationException(400, 'InvalidSchema', 'Missing required request parameters: event_date')

    if 'accessory' not in request.json:
        raise ApplicationException(400, 'InvalidSchema', 'Missing required request parameters: accessory')
    accessory = Accessory(mac_address)
    res['accessory'] = accessory.patch(request.json['accessory'])

    if 'sensors' not in request.json:
        raise ApplicationException(400, 'InvalidSchema', 'Missing required request parameters: sensors')
    res['sensors'] = []
    for sensor in request.json['sensors']:
        # TODO work out how we're actually persisting this data
        res['sensors'].append(sensor)

    # Save the data in a time-rolling ddb log table
    _save_sync_record(mac_address, request.json['event_date'], res)

    res['latest_firmware'] = {
        'accessory': Firmware('accessory', 'latest').get(),
        'sensor': Firmware('sensor', 'latest').get()
    }
    return json.dumps(res, default=json_serialise)


@app.route('/v1/sensor/<mac_address>', methods=['PATCH'])
def handle_sensor_patch(mac_address):
    sensor = Sensor(mac_address)
    if not sensor.exists():
        ret = sensor.create(request.json)
    else:
        ret = sensor.patch(request.json)
    return json.dumps({'sensor': ret}, default=json_serialise)


@app.route('/v1/firmware/<device_type>/<version>', methods=['GET'])
def handle_firmware_get(device_type, version):
    res = {'firmware': Firmware(device_type, version).get()}
    return json.dumps(res, default=json_serialise)


@app.route('/v1/misc/uuid', methods=['GET'])
def handle_misc_uuid():
    return json.dumps({'uuids': [str(uuid.uuid4()) for _ in range(32)]})


@app.route('/v1/misc/time', methods=['GET'])
def handle_misc_time():
    return json.dumps({'current_date': datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")})


def _save_sync_record(mac_address, event_date, body):
    item = {
        'accessory_mac_address': mac_address,
        'event_date': event_date,
    }
    for k, v in body['accessory'].items():
        item['accessory_{}'.format(k)] = v
    for i in range(len(body['sensors'])):
        for k, v in body['sensors'][i].items():
            item['sensor{}_{}'.format(i + 1, k)] = v

    dynamodb_resource = boto3.resource('dynamodb').Table(os.environ['DYNAMODB_ACCESSORYSYNCLOG_TABLE_NAME'])
    dynamodb_resource.put_item(Item=item)


@app.errorhandler(500)
def handle_server_error(e):
    tb = sys.exc_info()[2]
    return json.dumps({'message': str(e.with_traceback(tb))}, default=json_serialise), 500, {'Status': type(e).__name__}


@app.errorhandler(404)
def handle_unrecognised_endpoint(_):
    return '{"message": "You must specify an endpoint"}', 404, {'Status': 'UnrecognisedEndpoint'}


@app.errorhandler(ApplicationException)
def handle_application_exception(e):
    print('appexc')
    return json.dumps({'message': e.message}, default=json_serialise), e.status_code, {'Status': e.status_code_text}


def handler(event, context):
    print(json.dumps(event))
    ret = app(event, context)
    ret['headers']['Content-Type'] = 'application/json'
    # Round-trip through our JSON serialiser to make it parseable by AWS's
    return json.loads(json.dumps(ret, sort_keys=True, default=json_serialise))


if __name__ == '__main__':
    app.run(debug=True)
