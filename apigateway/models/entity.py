from abc import abstractmethod
from functools import reduce
from operator import iand

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from decimal import Decimal

from dynamodbupdate import DynamodbUpdate
from exceptions import InvalidSchemaException, NoSuchEntityException, DuplicateEntityException


class Entity:

    def __init__(self, primary_key):
        self._primary_key = primary_key

        self._primary_key_fields = list(primary_key.keys())
        self._fields = {}
        schema = self.schema()
        for field, config in schema['properties'].items():
            self._fields[field] = {
                'immutable': config.get('readonly', False),
                'required': field in schema['required'],
                'primary_key': field in self._primary_key_fields
            }

        self._exists = None

    @property
    def primary_key(self):
        return self._primary_key

    @staticmethod
    @abstractmethod
    def schema():
        raise NotImplementedError

    def get_fields(self, *, immutable=None, required=None, primary_key=None):
        return [
            k for k, v in self._fields.items()
            if (immutable is None or v['immutable'] == immutable)
            and (required is None or v['required'] == required)
            and (primary_key is None or v['primary_key'] == primary_key)
        ]

    def cast(self, field, value):
        schema = self.schema()
        if field not in schema['properties']:
            raise KeyError(field)

        field_type = schema['properties'][field]['type']
        if isinstance(field_type, dict) and '$ref' in field_type:
            field_type = field_type['$ref']

        if field_type == 'string':
            return str(value)
        elif field_type == 'number':
            return Decimal(str(value))
        elif field_type == "types.json/definitions/macaddress":
            return str(value).upper()
        else:
            raise NotImplementedError("field_type '{}' cannot be cast".format(field_type))

    def validate(self, operation, body):
        # Primary key must be complete
        if None in self.primary_key.values():
            raise InvalidSchemaException('Incomplete primary key')

        if operation == 'PATCH':
            # Not allowed to modify readonly attributes for PATCH
            for key in self.get_fields(immutable=True, primary_key=False):
                if key in body:
                    raise InvalidSchemaException('Cannot modify value of immutable parameter: {}'.format(key))

        else:
            # Required fields must be present for PUT
            for key in self.get_fields(required=True, primary_key=False):
                if key not in body and key not in self.primary_key.keys():
                    raise InvalidSchemaException('Missing required parameter: {}'.format(key))

    def exists(self):
        if self._exists is None:
            try:
                self.get()
                self._exists = True
            except NoSuchEntityException:
                self._exists = False
        return self._exists

    @abstractmethod
    def get(self):
        raise NotImplementedError()

    @abstractmethod
    def create(self, body):
        raise NotImplementedError()

    @abstractmethod
    def patch(self, body):
        raise NotImplementedError()


class DynamodbEntity(Entity):

    def get(self):
        # And together all the elements of the primary key
        kcx = reduce(iand, [Key(k).eq(v) for k, v in self.primary_key.items()])
        res = self._query_dynamodb(kcx)

        if len(res) == 0:
            raise NoSuchEntityException()
        return res[0]

    def patch(self, body, create=False):
        self.validate('PATCH', body)

        try:
            upsert = DynamodbUpdate()
            for key in self.get_fields(immutable=None if create else False, primary_key=False):
                if key in body:
                    if self.schema()['properties'][key]['type'] in ['list', 'object']:
                        upsert.add(key, set(body[key]))
                    else:
                        upsert.set(key, body[key])

            self._get_dynamodb_resource().update_item(
                Key=self.primary_key,
                UpdateExpression=upsert.update_expression,
                ExpressionAttributeValues=upsert.parameters,
            )

            return self.get()

        except ClientError as e:
            # FIXME
            if 'UsernameExistsException' in str(e):
                raise DuplicateEntityException()
            else:
                print(json.dumps({'exception': e}))
                raise

    def create(self, body):
        self.validate('PUT', body)
        return self.patch(body, True)

    @abstractmethod
    def _get_dynamodb_resource(self):
        raise NotImplementedError

    def _query_dynamodb(self, key_condition_expression, limit=10000, scan_index_forward=True, exclusive_start_key=None):
        if exclusive_start_key is not None:
            ret = self._get_dynamodb_resource().query(
                Select='ALL_ATTRIBUTES',
                Limit=limit,
                KeyConditionExpression=key_condition_expression,
                ExclusiveStartKey=exclusive_start_key,
                ScanIndexForward=scan_index_forward,
            )
        else:
            ret = self._get_dynamodb_resource().query(
                Select='ALL_ATTRIBUTES',
                Limit=limit,
                KeyConditionExpression=key_condition_expression,
                ScanIndexForward=scan_index_forward,
            )
        if 'LastEvaluatedKey' in ret:
            # There are more records to be scanned
            return ret['Items'] + self._query_dynamodb(key_condition_expression, limit, scan_index_forward, ret['LastEvaluatedKey'])
        else:
            # No more items
            return ret['Items']
