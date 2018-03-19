from aws_xray_sdk.core import xray_recorder, patch_all
import boto3
import datetime
import json
import os
import sys
import traceback
import uuid

from accessory import Accessory
from exceptions import ApplicationException, InvalidSchemaException, NoSuchEntityException
from firmware import Firmware
from flask import request, Response, jsonify
from flask_lambda import FlaskLambda
from sensor import Sensor
from serialisable import json_serialise

patch_all()


class ApiResponse(Response):
    @classmethod
    def force_type(cls, rv, environ=None):
        if isinstance(rv, dict):
            # Round-trip through our JSON serialiser to make it parseable by AWS's
            rv = json.loads(json.dumps(rv, sort_keys=True, default=json_serialise))
            rv = jsonify(rv)
        return super().force_type(rv, environ)


app = FlaskLambda(__name__)
app.response_class = ApiResponse


@app.route('/v1/accessory/<mac_address>/register', methods=['POST'])
@app.route('/hardware/accessory/<mac_address>/register', methods=['POST'])
def handle_accessory_register(mac_address):
    accessory = Accessory(mac_address)
    accessory.create(request.json)
    return {"status": "success"}, 201


@app.route('/v1/accessory/<mac_address>', methods=['GET'])
@app.route('/hardware/accessory/<mac_address>', methods=['GET'])
def handle_accessory_get(mac_address):
    accessory = Accessory(mac_address).get()
    return {'accessory': accessory}


@app.route('/v1/accessory/<mac_address>', methods=['PATCH'])
@app.route('/hardware/accessory/<mac_address>', methods=['PATCH'])
def handle_accessory_patch(mac_address):
    accessory = Accessory(mac_address)
    if not accessory.exists():
        ret = accessory.create(request.json)
    else:
        ret = accessory.patch(request.json)
    return ret


@app.route('/v1/accessory/<mac_address>/login', methods=['POST'])
@app.route('/hardware/accessory/<mac_address>/login', methods=['POST'])
def handle_accessory_login(mac_address):
    if 'password' not in request.json:
        raise InvalidSchemaException('Missing required request parameters: password')
    accessory = Accessory(mac_address)
    return {
        'username': mac_address,
        'authorization': accessory.login(request.json['password'])
    }


@app.route('/v1/accessory/<mac_address>/sync', methods=['POST'])
@app.route('/hardware/accessory/<mac_address>/sync', methods=['POST'])
def handle_accessory_sync(mac_address):
    res = {}

    for required_parameter in ['event_date', 'accessory', 'sensors']:
        if required_parameter not in request.json:
            raise ApplicationException(400, 'InvalidSchema', 'Missing required request parameters: {}'.format(required_parameter))

    # event_date must be in correct format
    try:
        datetime.datetime.strptime(request.json['event_date'], "%Y-%m-%dT%H:%M:%SZ")
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


@app.route('/v1/sensor/<mac_address>', methods=['PATCH'])
@app.route('/hardware/sensor/<mac_address>', methods=['PATCH'])
def handle_sensor_patch(mac_address):
    ret = _patch_sensor(mac_address, request.json)
    return {'sensor': ret}


@app.route('/v1/sensor', methods=['PATCH'])
@app.route('/hardware/sensor', methods=['PATCH'])
def handle_sensor_multipatch():
    if 'sensors' not in request.json or not isinstance(request.json['sensors'], list):
        raise InvalidSchemaException('Missing required parameter sensors')
    ret = [_patch_sensor(s['mac_address'], s) for s in request.json['sensors']]
    return {'sensors': ret}


def _patch_sensor(mac_address, body):
    sensor = Sensor(mac_address)
    if not sensor.exists():
        ret = sensor.create(body)
    else:
        ret = sensor.patch(body)
    return ret


@app.route('/v1/firmware/<device_type>/<version>', methods=['GET'])
@app.route('/hardware/firmware/<device_type>/<version>', methods=['GET'])
def handle_firmware_get(device_type, version):
    return {'firmware': Firmware(device_type, version).get()}


@app.route('/v1/misc/uuid', methods=['GET'])
@app.route('/hardware/misc/uuid', methods=['GET'])
def handle_misc_uuid():
    return {'uuids': [str(uuid.uuid4()) for _ in range(32)]}


@app.route('/v1/misc/time', methods=['GET'])
@app.route('/hardware/misc/time', methods=['GET'])
def handle_misc_time():
    return {'current_date': datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")}


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


@app.errorhandler(500)
def handle_server_error(e):
    tb = sys.exc_info()[2]
    return {'message': str(e.with_traceback(tb))}, 500, {'Status': type(e).__name__}


@app.errorhandler(404)
def handle_unrecognised_endpoint(_):
    return {"message": "You must specify an endpoint"}, 404, {'Status': 'UnrecognisedEndpoint'}


@app.errorhandler(ApplicationException)
def handle_application_exception(e):
    traceback.print_exception(*sys.exc_info())
    return {'message': e.message}, e.status_code, {'Status': e.status_code_text}


def handler(event, context):
    print(json.dumps(event))
    ret = app(event, context)
    # Unserialise JSON output so AWS can immediately serialise it again...
    ret['body'] = ret['body'].decode('utf-8')
    print(json.dumps(ret))
    return ret


if __name__ == '__main__':
    app.run(debug=True)
