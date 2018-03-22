from flask import Blueprint

from decorators import authentication_required
from models.firmware import Firmware

app = Blueprint('firmware', __name__)


@app.route('/<device_type>/<version>', methods=['GET'])
@authentication_required
def handle_firmware_get(device_type, version):
    return {'firmware': Firmware(device_type, version).get()}


@app.route('/<device_type>/<version>/download', methods=['GET'])
@authentication_required
def handle_firmware_download(device_type, version):
    firmware = Firmware(device_type, version).get()
    raise NotImplementedError()
