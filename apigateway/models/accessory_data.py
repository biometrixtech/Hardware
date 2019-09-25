from boto3.dynamodb.conditions import Attr

from fathomapi.api.config import Config
from fathomapi.models.dynamodb_entity import DynamodbEntity


class AccessoryData(DynamodbEntity):
    _dynamodb_table_name = Config.get('DYNAMODB_ACCESSORY_TABLE_NAME')

    def __init__(self, accessory_id):
        super().__init__({'id': accessory_id})

    @property
    def id(self):
        return self.primary_key['id']