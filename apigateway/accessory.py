from botocore.exceptions import ClientError
import boto3
import datetime
import json
import os

from entity import Entity
from exceptions import DuplicateEntityException, InvalidSchemaException, NoSuchEntityException

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
            if 'ResourceNotFoundException' in str(e):
                raise NoSuchEntityException()
            raise

        custom_properties = {prop['Name'].split(':')[-1]: prop['Value'] for prop in res['UserAttributes']}

        ret = self.primary_key
        for key in self.get_fields(primary_key=False):
            if key in custom_properties:
                field_type = self.get_field_type(key)
                ret[key] = field_type(custom_properties[key])
            else:
                ret[key] = self.schema()['properties'][key].get('default', None)
        return ret

    def patch(self, body):
        attributes = [
            {'Name': 'custom:{}'.format(key), 'Value': str(body[key])}
            for key in self.get_fields(immutable=False, primary_key=False)
            if key in body
        ]

        if self.exists():
            cognito_client.admin_update_user_attributes(
                UserPoolId=os.environ['COGNITO_USER_POOL_ID'],
                Username=self._mac_address,
                UserAttributes=attributes
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
            return self.get()

        except ClientError as e:
            print(e)
            if 'UsernameExistsException' in str(e):
                raise DuplicateEntityException()
            else:
                raise

    def login(self, password):
        response = cognito_client.admin_initiate_auth(
            UserPoolId=os.environ['COGNITO_USER_POOL_ID'],
            ClientId=os.environ['COGNITO_USER_POOL_CLIENT_ID'],
            AuthFlow='ADMIN_NO_SRP_AUTH',
            AuthParameters={
                'USERNAME': self._mac_address,
                'PASSWORD': password
            },
        )
        print(json.dumps(response))
        if 'ChallengeName' in response and response['ChallengeName'] == "NEW_PASSWORD_REQUIRED":
            # Need to set a new password
            response = cognito_client.admin_respond_to_auth_challenge(
                UserPoolId=os.environ['COGNITO_USER_POOL_ID'],
                ClientId=os.environ['COGNITO_USER_POOL_CLIENT_ID'],
                ChallengeName='NEW_PASSWORD_REQUIRED',
                ChallengeResponses={'USERNAME': self._mac_address, 'NEW_PASSWORD': password},
                Session=response['Session']
            )
            print(json.dumps(response))

        expiry_date = datetime.datetime.now() + datetime.timedelta(
            seconds=response['AuthenticationResult']['ExpiresIn'])
        return {
            'jwt': response['AuthenticationResult']['AccessToken'],
            'expires': expiry_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
