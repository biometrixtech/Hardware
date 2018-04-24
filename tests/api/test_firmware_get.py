from base_test import BaseTest


class TestFirmwareGetInvalidVersion(BaseTest):
    endpoint = 'firmware/accessory/fourtytwo'
    method = 'GET'
    expected_status = 404


class TestFirmwareGet10(BaseTest):
    endpoint = 'firmware/accessory/1.0'
    method = 'GET'
    expected_status = 200

    def validate_response(self, body, headers, status):
        self.assertIn('firmware', body)
        self.assertIn('device_type', body['firmware'])
        self.assertEqual('accessory', body['firmware']['device_type'])
        self.assertIn('version', body['firmware'])
        self.assertEqual('1.0', body['firmware']['version'])


class TestFirmwareGetLatest(BaseTest):
    endpoint = 'firmware/accessory/latest'
    method = 'GET'
    expected_status = 200

    def validate_response(self, body, headers, status):
        self.assertIn('firmware', body)
        self.assertIn('device_type', body['firmware'])
        self.assertEqual('accessory', body['firmware']['device_type'])
        self.assertIn('version', body['firmware'])
        self.assertNotEqual('latest', body['firmware']['version'])
        self.assertNotEqual('1.0', body['firmware']['version'])

