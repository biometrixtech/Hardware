from aws_xray_sdk.core import xray_recorder
from botocore.exceptions import ClientError
from flask import Blueprint, request
from semver import VersionInfo
import base64
import boto3
import os

from decorators import authentication_required
from exceptions import ApplicationException, InvalidSchemaException, DuplicateEntityException
from models.firmware import Firmware

app = Blueprint('firmware', __name__)


@app.route('/<device_type>/<semver:version>', methods=['GET'])
@xray_recorder.capture('routes.firmware.get')
def handle_firmware_get(device_type, version):
    return {'firmware': Firmware(device_type, version).get()}


@app.route('/<device_type>/<semver:version>/download', methods=['GET'])
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


@app.route('/<device_type>/<semver:version>', methods=['POST'])
@authentication_required
@xray_recorder.capture('routes.firmware.upload')
def handle_firmware_upload(device_type, version):
    firmware = Firmware(device_type, version)
    if firmware.exists():
        raise DuplicateEntityException()

    # Upload the firmware file
    s3_key = f'firmware/{args.devicetype}/{args.version}'
    s3_bucket.put_object(Key=s3_key, Body=open(filepath, 'rb'))
    cprint(f'Uploaded firware file from {filepath} to s3://{s3_bucket.name}/{s3_key}', colour=Fore.GREEN)

    firmware.create(request.json)
    return {"status": "success"}, 201


def validate_semver_tag(new_tag, old_tags):
    """
    Check for various version consistency gotchas
    :param VersionInfo new_tag:
    :param list[VersionInfo] old_tags:
    :return:
    """
    for old_tag in old_tags:
        if old_tag == new_tag:
            raise InvalidSchemaException(f'Release {new_tag} already exists')
        elif old_tag > new_tag:
            if old_tag.major != new_tag.major:
                # It's ok to prepare a legacy release
                pass
            elif old_tag.minor != new_tag.minor:
                # It's ok to patch an old minor release when a new minor release exists
                pass
            else:
                raise InvalidSchemaException(f'Cannot release {new_tag} because a later version {old_tag} already exists.')

    # Prevent skipping versions
    previous_tag = get_previous_semver(new_tag)
    for old_tag in old_tags:
        if old_tag >= previous_tag:
            break
    else:
        raise InvalidSchemaException(f'Cannot release {new_tag} because it skips (at least) version {previous_tag}.')

    if os.environ['ENVIRONMENT'] == 'production' and new_tag.prerelease is not None:
        raise InvalidSchemaException('Pre-release versions (ie with build suffixes) cannot be deployed to production')


def get_previous_semver(v: VersionInfo) -> VersionInfo:
    """
    Return a semantic version which is definitely less than the target version
    :param VersionInfo v:
    :return: VersionInfo
    """
    if v.build is not None:
        raise InvalidSchemaException(f'Cannot calculate previous version because {v} has a build number')

    if v.prerelease is not None:
        prerelease_parts = v.prerelease.split('.')
        if prerelease_parts[-1].isdigit() and int(prerelease_parts[-1]) > 1:
            return VersionInfo(v.major, v.minor, v.patch, prerelease_parts[0] + '.' + str(int(prerelease_parts[-1]) - 1))

    if v.patch > 0:
        return VersionInfo(v.major, v.minor, v.patch - 1)

    if v.minor > 0:
        return VersionInfo(v.major, v.minor - 1, 0)

    if v.major > 0:
        return VersionInfo(v.major - 1, 0, 0)

    raise Exception(f'Could not calculate a previous version for {v}')
