import json

import datetime

from querypostgres import query_postgres
from entity import Entity
from exceptions import NoSuchEntityException


class Sensor(Entity):

    def __init__(self, mac_address):
        super().__init__({'mac_address': mac_address})

    @property
    def mac_address(self):
        return self.primary_key['mac_address']

    @staticmethod
    def schema():
        with open('schemas/sensor.json', 'r') as f:
            return json.load(f)

    def get(self):
        res = query_postgres(
            """SELECT
              NULL AS battery_level,
              created_at AS created_date,
              firmware_version AS firmware_version,
              hw_model AS hardware_model,
              last_user_id AS last_user_id,
              id AS mac_address,
              memory_level AS memory_level,
              updated_at AS updated_date
            FROM sensors
            WHERE sensors.id = %s""",
            [self.mac_address]
        )

        if len(res) == 0:
            raise NoSuchEntityException()
        return res[0]

    def create(self, body):
        self.validate('PUT', body)
        raise NotImplementedError()

    def patch(self, body):
        self.validate('PATCH', body)
        res = query_postgres(
            """UPDATE sensors SET
              firmware_version = %s,
              last_user_id = %s,
              memory_level = %s,
              updated_at = %s
            WHERE sensors.id = %s""",
            [
                body['firmware_version'],
                body['last_user_id'],
                body['memory_level'],
                datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                self.mac_address
            ]
        )
        print(res)
        return self.get()