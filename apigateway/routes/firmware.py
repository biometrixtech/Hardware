from flask import Blueprint, send_file
import base64
import boto3
import os

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
    s3_object = boto3.resource('s3').Object(
        os.environ['S3_FIRMWARE_BUCKET_NAME'],
        '{}/{}'.format(firmware['device_type'], firmware['version'])
    )
    body = s3_object.get()['Body'].read()
    headers = {
        'Content-Disposition': 'attachment; filename={}.bin'.format(firmware['device_type']),
        'Content-Type': 'application/octet-stream'
    }
    return base64.encodebytes(body).decode('utf-8'), 200, headers
