from botocore.exceptions import ClientError
import boto3
import json
import os
import sys
from flask import request, jsonify
from flask_lambda import FlaskLambda
from serialisable import json_serialise

from aws_xray_sdk.core import patch_all
patch_all()

cognito_client = boto3.client('cognito-idp')

app = FlaskLambda(__name__)


class ApplicationException(Exception):
    def __init__(self, status_code, status_code_text, message):
        self._status_code = status_code
        self._status_code_text = status_code_text
        self._message = message

    @property
    def status_code(self):
        return self._status_code

    @property
    def status_code_text(self):
        return self._status_code

    @property
    def message(self):
        return self._message


@app.route('/v1/accessory/<mac_address>/register', methods=['POST'])
def handle_accessory_register(mac_address):
    print(request.json)
    for key in ['password', 'hardwareModel', 'settingsKey', 'firmwareVersion']:
        if key not in request.json:
            raise ApplicationException(400, 'InvalidSchema', 'Missing required request parameters: {}'.format('key'))
    try:
        cognito_client.admin_create_user(
            UserPoolId=os.environ['COGNITO_USER_POOL_ID'],
            Username=mac_address,
            TemporaryPassword=request.json['password'],
            UserAttributes=[
                {'Name': 'custom:hardwareModel', 'Value': request.json['hardwareModel']},
                {'Name': 'custom:macAddress', 'Value': mac_address},
                {'Name': 'custom:settingsKey', 'Value': request.json['settingsKey']},
                {'Name': 'custom:firmwareVersion', 'Value': request.json['firmwareVersion']},
                {'Name': 'custom:ownerUUID', 'Value': ''}
            ],
            MessageAction='SUPPRESS',
        )
        return '{"status": "success"}'

    except ClientError as e:
        print(e)
        if 'UsernameExistsException' in str(e):
            raise ApplicationException(409, 'DuplicateMacAddress', 'Duplicate MAC address')
        else:
            raise

    except Exception:
        raise


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
