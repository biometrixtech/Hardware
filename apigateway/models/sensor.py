import boto3

from fathomapi.api.config import Config
from fathomapi.models.dynamodb_entity import DynamodbEntity


class Sensor(DynamodbEntity):
    _dynamodb_table_name = Config.get('DYNAMODB_SENSOR_TABLE_NAME')
    # def _get_dynamodb_resource(self):
    #     return boto3.resource('dynamodb').Table(Config.get('DYNAMODB_SENSOR_TABLE_NAME'))

    def __init__(self, mac_address):
        super().__init__({'mac_address': mac_address.upper()})

    @property
    def mac_address(self):
        return self.primary_key['mac_address']
