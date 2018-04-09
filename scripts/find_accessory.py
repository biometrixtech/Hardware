#!/usr/bin/env python
import argparse
import boto3


parser = argparse.ArgumentParser(description='Find an accessory')
parser.add_argument('--region', '-r',
                    type=str,
                    help='AWS Region',
                    choices=['us-west-2'],
                    default='us-west-2')
parser.add_argument('--environment', '-e',
                    type=str,
                    help='Environment',
                    choices=['dev', 'qa', 'production'],
                    default='production')
parser.add_argument('--owner_id',
                    type=str,
                    help='Accessory owner id',
                    required=True)

args = parser.parse_args()

cognito_client = boto3.client('cognito-idp', region_name=args.region)


def get_cognito_user_pool_id():
    res = cognito_client.list_user_pools(MaxResults=60)
    pools = {pool['Name']: pool['Id'] for pool in res['UserPools']}
    pool_name = 'hardware-{}-accessories'.format(args.environment)
    return pools.get(pool_name, None)


def get_accessories(pool_id):
    res = cognito_client.list_users(
        UserPoolId=pool_id,
    )
    return [get_accessory_from_record(record) for record in res['Users']]


def get_accessory_from_record(record):
    ret = {'id': record['Username'], 'owner_id': None}
    for attribute in record['Attributes']:
        if attribute['Name'] == 'custom:owner_id':
            ret['owner_id'] = attribute['Value']
    return ret


def print_accessory(accessory):
    print("""
Accessory:
        Id: {id}
  Owner Id: {owner_id}
""".format(**accessory))


def main():
    accessories = get_accessories(get_cognito_user_pool_id())
    for accessory in accessories:
        if accessory['owner_id'] == args.owner_id:
            print_accessory(accessory)
            exit(0)
    print('No accessory with that owner id')
    exit(1)


if __name__ == '__main__':
    main()
