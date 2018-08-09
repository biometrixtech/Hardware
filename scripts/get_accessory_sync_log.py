#!/usr/bin/env python3
import argparse
import boto3
import pandas as pd
from boto3.dynamodb.conditions import Key
from datetime import datetime

pd.set_option('display.height', 1000)
pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)


parser = argparse.ArgumentParser(description='Get an extract from the accessory sync log')
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
parser.add_argument('accessory_id',
                    type=str,
                    help='Accessory mac address')
parser.add_argument('start',
                    type=str,
                    help='Start date')
parser.add_argument('end',
                    type=str,
                    help='End date')

args = parser.parse_args()

dynamodb_table = boto3.resource('dynamodb', region_name=args.region).Table('hardware-{}-accessorysynclog'.format(args.environment))


def query_dynamodb(key_condition_expression, limit=10000, scan_index_forward=True, exclusive_start_key=None):
    if exclusive_start_key is not None:
        ret = dynamodb_table.query(
            Select='ALL_ATTRIBUTES',
            Limit=limit,
            KeyConditionExpression=key_condition_expression,
            ExclusiveStartKey=exclusive_start_key,
            ScanIndexForward=scan_index_forward,
        )
    else:
        ret = dynamodb_table.query(
            Select='ALL_ATTRIBUTES',
            Limit=limit,
            KeyConditionExpression=key_condition_expression,
            ScanIndexForward=scan_index_forward,
        )
    if 'LastEvaluatedKey' in ret:
        # There are more records to be scanned
        return ret['Items'] + query_dynamodb(key_condition_expression, limit, scan_index_forward, ret['LastEvaluatedKey'])
    else:
        # No more items
        return ret['Items']


state_map = {
    '0x01': 'Idle',
    '0x04': 'Downloading',
    '0x05': 'Sensors logging data',  # session_event doesn't have to start. Just that sensors were removed from the kit and are recording data)
    '0x21': 'Kit management'  # This is where sensor sync etc happen. Could be automatic or manually triggered.)
}


def print_table(log_entries):
    matrix = [[
        l['accessory_mac_address'],
        datetime.strptime(l['event_date'], "%Y-%m-%dT%H:%M:%SZ").strftime('%Y-%m-%d at %H:%M:%S'),
        state_map.get(l['accessory_state'], l['accessory_state']),
        l['accessory_battery_level'],
        l['accessory_memory_level'],
    ] for l in log_entries]
    matrix_pd = pd.DataFrame(matrix)
    matrix_pd.columns = ['Mac Address', 'Event Date', 'State', 'Battery', 'Memory']
    matrix_pd.fillna(0, inplace=True)
    print(matrix_pd.round(2))


def main():
    res = query_dynamodb(
        Key('accessory_mac_address').eq(args.accessory_id) & Key('event_date').between(args.start, args.end)
    )
    print_table(res)


if __name__ == '__main__':
    main()
