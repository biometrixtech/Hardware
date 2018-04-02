from aws_xray_sdk.core import xray_recorder
from botocore.exceptions import ClientError
from flask import Blueprint
import base64
import boto3
import os

from exceptions import ApplicationException
from models.firmware import Firmware

app = Blueprint('firmware', __name__)


@app.route('/<device_type>/<version>', methods=['GET'])
@xray_recorder.capture('routes.firmware.get')
def handle_firmware_get(device_type, version):
    return {'firmware': Firmware(device_type, version).get()}


@app.route('/<device_type>/<version>/download', methods=['GET'])
@xray_recorder.capture('routes.firmware.download')
def handle_firmware_download(device_type, version):
    firmware = Firmware(device_type, version).get()
    try:
        s3_object = boto3.resource('s3').Object(
            os.environ['S3_FIRMWARE_BUCKET_NAME'],
            'firmware/{}/{}'.format(firmware['device_type'], firmware['version'])
        )
        body = s3_object.get()['Body'].read()
    except ClientError as e:
        if 'NoSuchKey' in str(e):
            raise ApplicationException(500, 'ServerError', 'Could not locate firmware binary')
        else:
            raise e

    headers = {
        'Content-Disposition': 'attachment; filename={}.bin'.format(firmware['device_type']),
        'Content-Type': 'application/octet-stream'
    }
    return base64.encodebytes(body).decode('utf-8'), 200, headers
