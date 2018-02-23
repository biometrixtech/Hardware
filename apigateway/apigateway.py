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
    for key in ['password', 'hardware_model', 'settings_key', 'firmware_version']:
        if key not in request.json:
            raise ApplicationException(400, 'InvalidSchema', 'Missing required request parameters: {}'.format('key'))
    try:
        cognito_client.admin_create_user(
            UserPoolId=os.environ['COGNITO_USER_POOL_ID'],
            Username=mac_address,
            TemporaryPassword=request.json['password'],
            UserAttributes=[
                {'Name': 'custom:hardware_model', 'Value': request.json['hardware_model']},
                {'Name': 'custom:mac_address', 'Value': mac_address},
                {'Name': 'custom:settings_key', 'Value': request.json['settings_key']},
                {'Name': 'custom:firmware_version', 'Value': request.json['firmware_version']},
                {'Name': 'custom:owner_uuid', 'Value': ''}
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


@app.route('/v1/accessory/<mac_address>/login', methods=['POST'])
def handle_accessory_login(mac_address):
    for key in ['password']:
        if key not in request.json:
            raise ApplicationException(400, 'InvalidSchema', 'Missing required request parameters: {}'.format('key'))
    response = cognito_client.admin_initiate_auth(
        UserPoolId=os.environ['COGNITO_USER_POOL_ID'],
        ClientId=os.environ['COGNITO_USER_POOL_CLIENT_ID'],
        AuthFlow='ADMIN_NO_SRP_AUTH',
        AuthParameters={
            'USERNAME': mac_address,
            'PASSWORD': request.json['password']
        },
    )
    print(json.dumps(response))
    if 'ChallengeName' in response and response['ChallengeName'] == "NEW_PASSWORD_REQUIRED":
        # Need to set a new password
        response = cognito_client.admin_respond_to_auth_challenge(
            UserPoolId=os.environ['COGNITO_USER_POOL_ID'],
            ClientId=os.environ['COGNITO_USER_POOL_CLIENT_ID'],
            ChallengeName='NEW_PASSWORD_REQUIRED',
            ChallengeResponses={'USERNAME': mac_address, 'NEW_PASSWORD': request.json['password']},
            Session=response['Session']
        )
        print(json.dumps(response))

    expiry_date = datetime.datetime.now() + datetime.timedelta(seconds=response['AuthenticationResult']['ExpiresIn'])
    return json.dumps({
        'username': mac_address,
        'authorization': {
            'jwt': response['AuthenticationResult']['AccessToken'],
            'expires': expiry_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
    }, default=json_serialise)


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
