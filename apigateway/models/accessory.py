from botocore.exceptions import ClientError
import boto3
import datetime
import json
import os

from models.entity import Entity
from fathomapi.utils.exceptions import DuplicateEntityException, InvalidSchemaException, NoSuchEntityException, \
    UnauthorizedException
from fathomapi.utils.formatters import format_datetime

cognito_client = boto3.client('cognito-idp')


class Accessory(Entity):
    def __init__(self, mac_address):
        self._mac_address = mac_address.upper()
        super().__init__({'mac_address': self._mac_address})

    @staticmethod
    def schema():
        with open('schemas/accessory.json', 'r') as f:
            return json.load(f)

    def get(self):
        try:
            res = cognito_client.admin_get_user(
                UserPoolId=os.environ['COGNITO_USER_POOL_ID'],
                Username=self._mac_address,
            )
        except ClientError as e:
            if 'UserNotFoundException' in str(e):
                raise NoSuchEntityException()
            raise

        custom_properties = {prop['Name'].split(':')[-1]: prop['Value'] for prop in res['UserAttributes']}

        ret = self.primary_key
        for key in self.get_fields(primary_key=False):
            if key in custom_properties:
                ret[key] = self.cast(key, custom_properties[key])
            else:
                ret[key] = self.schema()['properties'][key].get('default', None)
        try:
            ret['last_sync_date'] = format_datetime(res['UserLastModifiedDate'])
        except:
            ret['last_sync_date'] = None
        return ret

    def patch(self, body):
        attributes_to_update = []
        attributes_to_delete = []
        for key in self.get_fields(immutable=False, primary_key=False):
            if key in body:
                if body[key] is None:
                    attributes_to_delete.append('custom:{}'.format(key))
                else:
                    attributes_to_update.append({'Name': 'custom:{}'.format(key), 'Value': str(body[key])})

        if self.exists():
            cognito_client.admin_update_user_attributes(
                UserPoolId=os.environ['COGNITO_USER_POOL_ID'],
                Username=self._mac_address,
                UserAttributes=attributes_to_update
            )
            cognito_client.admin_delete_user_attributes(
                UserPoolId=os.environ['COGNITO_USER_POOL_ID'],
                Username=self._mac_address,
                UserAttributeNames=attributes_to_delete
            )
        else:
            # TODO
            raise NotImplementedError

        return self.get()

    def create(self, body):
        body['mac_address'] = self._mac_address
        for key in self.get_fields(required=True):
            if key not in body:
                raise InvalidSchemaException('Missing required request parameters: {}'.format(key))
        try:
            cognito_client.admin_create_user(
                UserPoolId=os.environ['COGNITO_USER_POOL_ID'],
                Username=self._mac_address,
                TemporaryPassword=body['password'],
                UserAttributes=[
                    {'Name': 'custom:{}'.format(key), 'Value': body[key]}
                    for key in self.get_fields(primary_key=False)
                    if key in body
                ],
                MessageAction='SUPPRESS',
            )

            # Log in straight away so there's no risk of the Cognito user expiring
            self.login(body['password'])

            return self.get()

        except ClientError as e:
            if 'UsernameExistsException' in str(e):
                raise DuplicateEntityException()
            else:
                print(json.dumps({'exception': str(e)}))
                raise

    def login(self, password):
        try:
            response = cognito_client.admin_initiate_auth(
                UserPoolId=os.environ['COGNITO_USER_POOL_ID'],
                ClientId=os.environ['COGNITO_USER_POOL_CLIENT_ID'],
                AuthFlow='ADMIN_NO_SRP_AUTH',
                AuthParameters={
                    'USERNAME': self._mac_address,
                    'PASSWORD': password
                },
            )
        except ClientError as e:
            if 'UserNotFoundException' in str(e):
                raise NoSuchEntityException()
            if 'NotAuthorizedException' in str(e):
                details = str(e).split(':')[-1].strip(' ')
                raise UnauthorizedException(details)
            raise
        if 'ChallengeName' in response and response['ChallengeName'] == "NEW_PASSWORD_REQUIRED":
            # Need to set a new password
            response = cognito_client.admin_respond_to_auth_challenge(
                UserPoolId=os.environ['COGNITO_USER_POOL_ID'],
                ClientId=os.environ['COGNITO_USER_POOL_CLIENT_ID'],
                ChallengeName='NEW_PASSWORD_REQUIRED',
                ChallengeResponses={'USERNAME': self._mac_address, 'NEW_PASSWORD': password},
                Session=response['Session']
            )

        expiry_date = datetime.datetime.now() + datetime.timedelta(
            seconds=response['AuthenticationResult']['ExpiresIn'])
        return {
            'jwt': response['AuthenticationResult']['AccessToken'],
            'expires': expiry_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
