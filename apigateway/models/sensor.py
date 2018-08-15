import json
import os
import boto3

from models.entity import DynamodbEntity


class Sensor(DynamodbEntity):

    def __init__(self, mac_address):
        super().__init__({'mac_address': mac_address.upper()})

    @property
    def mac_address(self):
        return self.primary_key['mac_address']

    def _get_dynamodb_resource(self):
        return boto3.resource('dynamodb').Table(os.environ['DYNAMODB_SENSOR_TABLE_NAME'])

    @staticmethod
    def schema():
        with open('schemas/sensor.json', 'r') as f:
            return json.load(f)
