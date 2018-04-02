from aws_xray_sdk.core import xray_recorder
import datetime

from exceptions import InvalidSchemaException
from flask import request, Blueprint

from decorators import authentication_required
from models.sensor import Sensor

app = Blueprint('sensor', __name__)


@app.route('/<mac_address>', methods=['PATCH'])
@authentication_required
@xray_recorder.capture('routes.sensor.patch')
def handle_sensor_patch(mac_address):
    xray_recorder.current_subsegment().put_annotation('sensor_id', mac_address)
    ret = _patch_sensor(mac_address, request.json)
    return {'sensor': ret}


@app.route('/', methods=['PATCH'])
@authentication_required
@xray_recorder.capture('routes.sensor.multipatch')
def handle_sensor_multipatch():
    if 'sensors' not in request.json or not isinstance(request.json['sensors'], list):
        raise InvalidSchemaException('Missing required parameter sensors')
    ret = [_patch_sensor(s['mac_address'], s) for s in request.json['sensors']]
    return {'sensors': ret}


def _patch_sensor(mac_address, body):
    sensor = Sensor(mac_address)
    if not sensor.exists():
        body['created_date'] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        ret = sensor.create(body)
    else:
        ret = sensor.patch(body)
    return ret
