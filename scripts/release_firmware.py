#!/usr/bin/env python3
#
# Example:
#
#   release_firmware.py \
#       --region us-west-2 \
#       --environment dev \
#       --devicetype accessory \
#       --version 1.42 \
#       --notes "This version fixes a bug where the accessory sometimes explodes" \
#       /full/path/to/firmware/binary.bin
#
import argparse
import datetime
import re
import os

try:
    import builtins
except ImportError:
    import __builtin__ as builtins

try:
    import boto3
    from boto3.dynamodb.conditions import Key, Attr
    from colorama import Fore, Style
except ImportError:
    print('You must install the `boto3` and `colorama` pip modules')
    exit(1)
    raise Exception()  # Just for static code analysis


def print(*args, **kwargs):
    if 'colour' in kwargs:
        builtins.print(kwargs['colour'], end="")
        del kwargs['colour']

        end = kwargs.get('end', '\n')
        kwargs['end'] = ''
        builtins.print(*args, **kwargs)

        builtins.print(Style.RESET_ALL, end=end)

    else:
        builtins.print(*args, **kwargs)

class DynamodbUpdate:
    def __init__(self):
        self._add = []
        self._set = []
        self._parameters = {}

    def set(self, field, value):
        self._set.append("{field} = :{field}".format(field=field))
        self._parameters[':' + field] = value

    def add(self, field, value):
        self._add.append("{field} :{field}".format(field=field))
        self._parameters[':' + field] = value

    @property
    def update_expression(self):
        return 'SET {} '.format(', '.join(self._set)) + (
            'ADD {}'.format(', '.join(self._add)) if len(self._add) else '')

    @property
    def parameters(self):
        return self._parameters


if __name__ == '__main__':
    def version_number(x):
        if not re.match('\d+\.\d+(\.\d+)?', x):
            raise argparse.ArgumentTypeError('Version number must be in the format NN.NN(.NN)')
        return x

    parser = argparse.ArgumentParser(description='Invoke a test file')
    parser.add_argument('filepath',
                        type=str,
                        help='The new firmware file')
    parser.add_argument('--region', '-r',
                        type=str,
                        help='AWS Region',
                        choices=['us-west-2'],
                        default='us-west-2')
    parser.add_argument('--environment', '-e',
                        type=str,
                        help='Environment',
                        default='dev')
    parser.add_argument('--devicetype',
                        type=str,
                        help='Device type',
                        choices=['accessory', 'sensor'],
                        required=True)
    parser.add_argument('--version',
                        help='Version number',
                        type=version_number,
                        required=True)
    parser.add_argument('--notes',
                        help='Version release notes',
                        type=version_number,
                        default='')

    args = parser.parse_args()

    filepath = os.path.realpath(args.filepath)

    if not os.path.exists(filepath):
        print('File {} does not exist'.format(filepath), colour=Fore.RED)
        exit(1)

    s3_bucket = boto3.resource('s3', region_name=args.region).Bucket('biometrix-hardware-{}-{}'.format(args.environment, args.region))
    ddb_table = boto3.resource('dynamodb', region_name=args.region).Table('hardware-{}-firmware'.format(args.environment))

    # Check that this version doesn't already exist
    res = ddb_table.query(KeyConditionExpression=Key('device_type').eq(args.devicetype) & Key('version').eq(args.version))
    if len(res['Items']):
        print('Version {} has already been released in {} environment'.format(args.version, args.environment), colour=Fore.RED)
        exit(1)

    # Upload the firmware file
    s3_key = '{}/{}'.format(args.devicetype, args.version)
    s3_bucket.put_object(Key=s3_key, Body=open(filepath, 'rb'))
    print('Uploaded template from {} to s3://{}/{}'.format(filepath, s3_bucket.name, s3_key), colour=Fore.GREEN)

    # Create the DDB record
    insert = DynamodbUpdate()
    insert.set('created_date', datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"))
    insert.set('notes', args.notes)
    ddb_table.update_item(
        Key={'device_type': args.devicetype, 'version': args.version},
        ConditionExpression=Attr('id').not_exists(),
        UpdateExpression=insert.update_expression,
        ExpressionAttributeValues=insert.parameters,
    )
    print('Created DynamoDB record', colour=Fore.GREEN)

