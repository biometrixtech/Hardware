from base_test import BaseTest
from botocore.exceptions import ClientError
import boto3


cognito_client = boto3.client('cognito-idp', region_name='us-west-2')
cognito_user_pool_id = None
for up in cognito_client.list_user_pools(MaxResults=60)['UserPools']:
    if up['Name'] == 'hardware-dev-accessories':
        cognito_user_pool_id = up['Id']


class TestAccessoryRegisterInvalidMacAddress(BaseTest):
    endpoint = 'accessory/notamacaddress/register'
    method = 'POST'
    expected_status = 500


class TestAccessoryRegisterNoBody(BaseTest):
    endpoint = 'accessory/01:02:03:04:05/register'
    method = 'POST'
    body = None
    expected_status = 500


class TestAccessoryRegisterEmptyBody(BaseTest):
    endpoint = 'accessory/01:02:03:04:05/register'
    method = 'POST'
    body = {}
    expected_status = 400


class TestAccessoryRegister(BaseTest):
    endpoint = 'accessory/01:02:03:04:05/register'
    method = 'POST'
    body = {
        "password": 'abcdefgh',
        "hardware_model": '2.1',
        "firmware_version": '1.2',
        "settings_key": '1234567890abcdef',
    }
    expected_status = 201

    def validate_aws_pre(self):
        try:
            cognito_client.admin_get_user(
                UserPoolId=cognito_user_pool_id,
                Username='01:02:03:04:05'
            )
            self.fail('Accessory should not be registered prior to test')
        except Exception as e:
            if 'UserNotFound' not in str(e):
                self.fail(str(e))

    def validate_aws_post(self):
        res = cognito_client.admin_get_user(
            UserPoolId=cognito_user_pool_id,
            Username='01:02:03:04:05'
        )
        self.assertIn('Username', res)
        self.assertEqual('01:02:03:04:05', res['Username'])

    def validate_response(self, body, headers, status):
        self.assertIn('status', body)
        self.assertEqual('success', body['status'])

    def tearDown(self):
        cognito_client.admin_delete_user(
            UserPoolId=cognito_user_pool_id,
            Username='01:02:03:04:05'
        )

