from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError
import boto3
import datetime
import json
import os

from dynamodbupdate import DynamodbUpdate
from entity import Entity
from exceptions import DuplicateEntityException, InvalidSchemaException, NoSuchEntityException

dynamodb_resource = boto3.resource('dynamodb').Table(os.environ['DYNAMODB_FIRMWARE_TABLE_NAME'])


class Firmware(Entity):
    def __init__(self, device_type, version, updated_date=None):
        self._device_type = device_type
        self._version = version
        self._updated_date = updated_date
        self._exists = None

    @staticmethod
    def schema():
        with open('schemas/firmware.json', 'r') as f:
            return json.load(f)

    @property
    def exists(self):
        if self._exists is None:
            pass
        return self._exists

    def get(self):
        if self._version.upper() == 'LATEST':
            res = _query_dynamodb(Key('device_type').eq(self._device_type), 1, False)
        else:
            res = _query_dynamodb(Key('device_type').eq(self._device_type) & Key('version').eq(self._version))

        if len(res) == 0:
            raise NoSuchEntityException()
        return res[0]

    def create(self, body):
        for key in self._get_required_fields():
            if key not in body and key not in ['device_type', 'version']:
                raise InvalidSchemaException('Missing required request parameters: {}'.format(key))
        try:
            upsert = DynamodbUpdate()
            for key in self._get_mutable_fields() + self._get_immutable_fields():
                if key in body:
                    if self.schema()['properties'][key]['type'] in ['list', 'object']:
                        upsert.add(key, set(body[key]))
                    else:
                        upsert.set(key, body[key])
                    if key in self._get_immutable_fields():
                        pass

            dynamodb_resource.update_item(
                Key={'device_type': self._device_type, 'version': self._version},
                # ConditionExpression=Attr('id').not_exists() | Attr('sessionStatus').eq(
                #     'UPLOAD_IN_PROGRESS'),
                UpdateExpression=upsert.update_expression,
                ExpressionAttributeValues=upsert.parameters,
            )

            return self.get()

        except ClientError as e:
            print(e)
            if 'UsernameExistsException' in str(e):
                raise DuplicateEntityException()
            else:
                raise


def _query_dynamodb(key_condition_expression, limit=10000, scan_index_forward=True, exclusive_start_key=None):
    if exclusive_start_key is not None:
        ret = dynamodb_resource.query(
            Select='ALL_ATTRIBUTES',
            Limit=limit,
            KeyConditionExpression=key_condition_expression,
            ExclusiveStartKey=exclusive_start_key,
            ScanIndexForward=scan_index_forward,
        )
    else:
        ret = dynamodb_resource.query(
            Select='ALL_ATTRIBUTES',
            Limit=limit,
            KeyConditionExpression=key_condition_expression,
            ScanIndexForward=scan_index_forward,
        )
    if 'LastEvaluatedKey' in ret:
        # There are more records to be scanned
        return ret['Items'] + _query_dynamodb(key_condition_expression, limit, scan_index_forward, ret['LastEvaluatedKey'])
    else:
        # No more items
        return ret['Items']
