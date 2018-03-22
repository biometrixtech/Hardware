from boto3.dynamodb.conditions import Key
import boto3
import json
import os

from models.entity import DynamodbEntity
from exceptions import NoSuchEntityException


class Firmware(DynamodbEntity):

    def __init__(self, device_type, version, updated_date=None):
        super().__init__({'device_type': device_type, 'version': version})
        self._updated_date = updated_date

    @property
    def device_type(self):
        return self.primary_key['device_type']

    @property
    def version(self):
        return self.primary_key['version']

    def _get_dynamodb_resource(self):
        return boto3.resource('dynamodb').Table(os.environ['DYNAMODB_FIRMWARE_TABLE_NAME'])

    @staticmethod
    def schema():
        with open('schemas/firmware.json', 'r') as f:
            return json.load(f)

    def get(self):
        if self.version.upper() == 'LATEST':
            res = self._query_dynamodb(Key('device_type').eq(self.device_type), 1, False)
        else:
            res = self._query_dynamodb(Key('device_type').eq(self.device_type) & Key('version').eq(self.version))

        if len(res) == 0:
            raise NoSuchEntityException()
        return res[0]

    def patch(self, body, upsert=True):
        if upsert:
            # Firmware updating not implemented yet
            raise NotImplementedError()
        else:
            return super().patch(body, False)
