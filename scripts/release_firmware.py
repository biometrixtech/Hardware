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
    import boto3
    from boto3.dynamodb.conditions import Key, Attr
    from colorama import Fore, Style
except ImportError:
    print('You must install the `boto3` and `colorama` pip modules')
    exit(1)
    raise Exception()  # Just for static code analysis


def cprint(*pargs, **kwargs):
    if 'colour' in kwargs:
        print(kwargs['colour'], end="")
        del kwargs['colour']

        end = kwargs.get('end', '\n')
        kwargs['end'] = ''
        print(*pargs, **kwargs)

        print(Style.RESET_ALL, end=end)

    else:
        print(*pargs, **kwargs)


class DynamodbUpdate:
    def __init__(self):
        self._add = []
        self._set = []
        self._parameters = {}

    def set(self, field, value):
        self._set.append(f"{field} = :{field}")
        self._parameters[':' + field] = value

    def add(self, field, value):
        self._add.append(f"{field} :{field}")
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

    parser = argparse.ArgumentParser(description='Upload a new firmware version')
    parser.add_argument('filepath',
                        type=str,
                        help='The new firmware file')
    parser.add_argument('--region', '-r',
                        type=str,
                        help='AWS Region',
                        choices=['us-west-2'],
                        default='us-west-2')
    parser.add_argument('environment',
                        type=str,
                        help='Environment',
                        default='dev')
    parser.add_argument('devicetype',
                        type=str,
                        help='Device type',
                        choices=['accessory', 'sensor', 'ankle'])
    parser.add_argument('version',
                        help='Version number',
                        type=version_number)
    parser.add_argument('--notes',
                        help='Version release notes',
                        default='')

    args = parser.parse_args()

    filepath = os.path.realpath(args.filepath)

    if not os.path.exists(filepath):
        cprint(f'File {filepath} does not exist', colour=Fore.RED)
        exit(1)

    s3_bucket = boto3.resource('s3', region_name=args.region).Bucket(f'biometrix-hardware-{args.environment}-{args.region}')
    ddb_table = boto3.resource('dynamodb', region_name=args.region).Table(f'hardware-{args.environment}-firmware')

    # Check that this version doesn't already exist
    res = ddb_table.query(KeyConditionExpression=Key('device_type').eq(args.devicetype) & Key('version').eq(args.version))
    if len(res['Items']):
        cprint(f'Version {args.version} has already been released in {args.environment} environment', colour=Fore.RED)
        exit(1)

    # Upload the firmware file
    s3_key = f'firmware/{args.devicetype}/{args.version}'
    s3_bucket.put_object(Key=s3_key, Body=open(filepath, 'rb'))
    cprint(f'Uploaded template from {filepath} to s3://{s3_bucket.name}/{s3_key}', colour=Fore.GREEN)

    # Create the DDB record
    insert = DynamodbUpdate()
    insert.set('created_date', datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"))

    if args.notes:
        insert.set('notes', args.notes)

    ddb_table.update_item(
        Key={'device_type': args.devicetype, 'version': args.version},
        ConditionExpression=Attr('id').not_exists(),
        UpdateExpression=insert.update_expression,
        ExpressionAttributeValues=insert.parameters,
    )
    cprint('Created DynamoDB record', colour=Fore.GREEN)
