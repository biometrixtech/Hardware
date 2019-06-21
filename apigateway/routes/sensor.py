from flask import request, Blueprint
import datetime

from fathomapi.utils.decorators import require
from fathomapi.utils.xray import xray_recorder

from models.sensor import Sensor

app = Blueprint('sensor', __name__)


@app.route('/<mac_address>', methods=['PATCH', 'PUT'])
@require.authenticated.any
@xray_recorder.capture('routes.sensor.patch')
def handle_sensor_patch(mac_address):
    xray_recorder.current_subsegment().put_annotation('sensor_id', mac_address)
    ret = _patch_sensor(mac_address, request.json)
    return {'sensor': ret}


@app.route('/', methods=['PATCH'])
@require.authenticated.any
@require.body({'sensors': list})
@xray_recorder.capture('routes.sensor.multipatch')
def handle_sensor_multipatch():
    ret = [_patch_sensor(s['mac_address'], s) for s in request.json['sensors']]
    return {'sensors': ret}


@xray_recorder.capture('routes.sensor._patch_sensor')
def _patch_sensor(mac_address, body):
    if len(mac_address.split(":")) == 4:
        mac_address += ":00:00"
    sensor = Sensor(mac_address)
    if not sensor.exists() or request.method == 'PUT':
        body['created_date'] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        ret = sensor.create(body)
    else:
        ret = sensor.patch(body)
    return ret
