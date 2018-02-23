import datetime
import boto3
import json
import os
import sys

from accessory import Accessory
from firmware import Firmware
from flask import request
from flask_lambda import FlaskLambda
from serialisable import json_serialise
from aws_xray_sdk.core import xray_recorder, patch_all

from exceptions import ApplicationException, InvalidSchemaException

patch_all()


app = FlaskLambda(__name__)


@app.route('/v1/accessory/<mac_address>/register', methods=['POST'])
def handle_accessory_register(mac_address):
    print(request.json)
    accessory = Accessory(mac_address)
    accessory.create(request.json)
    return '{"status": "success"}'


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

    if 'accessory' not in request.json:
        raise ApplicationException(400, 'InvalidSchema', 'Missing required request parameters: accessory')
    accessory = Accessory(mac_address)
    res['accessory'] = accessory.patch(request.json['accessory'])

    if 'sensors' not in request.json:
        raise ApplicationException(400, 'InvalidSchema', 'Missing required request parameters: sensors')
    res['sensors'] = []
    for sensor in request.json['sensors']:
        res['sensors'].append(_patch_sensor(mac_address, sensor, True))

    res['latest_firmware'] = {
        'accessory': Firmware('accessory', 'latest').get(),
        'sensor': Firmware('sensor', 'latest').get()
    }
    return json.dumps(res, default=json_serialise)


def _patch_sensor(mac_address, body, exists=None):
    # TODO
    return {
        'mac_address': mac_address,
        "battery_level": 0.57,
        "memory_level": 0.57,
        "firmware_version": "1.2",
        "gyro_offset": [
          0.572344,
          0.572344,
          0.572344
        ]
    }


@app.errorhandler(500)
def handle_server_error(e):
    tb = sys.exc_info()[2]
    return json.dumps({'message': str(e.with_traceback(tb))}, default=json_serialise), 500, {'Status': type(e).__name__}


@app.errorhandler(404)
def handle_unrecognised_endpoint(e):
    return '{"message": You must specify an endpoint}', 404, {'Status': 'UnrecognisedEndpoint'}


@app.errorhandler(ApplicationException)
def handle_application_exception(e):
    print('appexc')
    return json.dumps({'message': e.message}, default=json_serialise), e.status_code, {'Status': e.status_code_text}


def handler(event, context):
    ret = app(event, context)
    # Round-trip through our JSON serialiser to make it parseable by AWS's
    return json.loads(json.dumps(ret, sort_keys=True, default=json_serialise))


if __name__ == '__main__':
    app.run(debug=True)
