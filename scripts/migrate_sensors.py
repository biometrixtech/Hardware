#!/usr/bin/env python3
# Migrate sensors from postgres to dynamodb

import argparse
import boto3
import json
import requests

aws_account_id = '887689817172'

jwt = 'ADDME'


def query_postgres(query, parameters):
    lambda_client = boto3.client('lambda', region_name=args.region)
    res = json.loads(lambda_client.invoke(
        FunctionName=f'arn:aws:lambda:{args.region}:{aws_account_id}:function:infrastructure-{args.environment}-querypostgres',
        Payload=json.dumps({
            "Queries": [{"Query": query, "Parameters": parameters}],
            "Config": {"ENVIRONMENT": args.environment}
        }),
    )['Payload'].read().decode('utf-8'))
    result, error = res['Results'][0], res['Errors'][0]
    if error is not None:
        raise Exception(error)
    elif isinstance(result, list):
        return result
    else:
        return []


def make_request(url, payload):
    headers = {'Authorization': jwt, 'Accept': 'application/json'}
    res = requests.put(url, json=payload, headers=headers)
    return res.status_code


def main():
    sensors = query_postgres("SELECT * FROM sensors", None)
    print('{} sensors to migrate'.format(len(sensors)))

    for i, sensor in enumerate(sensors):
        url = f"https://apis.{args.environment}.fathomai.com/hardware/latest/sensor/{sensor['id']}"
        payload = {
            "mac_address": sensor['id'],
            "battery_level": None,
            "memory_level": str(sensor['memory_level']),
            "firmware_version": sensor['firmware_version'] or '0.0.0',
            "hardware_model": sensor['hw_model'],
            "created_date": sensor['created_at'],
            "updated_date": sensor['updated_at'],
            "last_user_id": sensor['last_user_id'],
        }
        status = make_request(url, {k: v for k, v in payload.items() if v is not None})
        print(f'{url} --> {status}')


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Migrate sensor records from postgres to dynamodb')
    parser.add_argument('environment',
                        type=str,
                        choices=['dev', 'test', 'production'],
                        help='The environment to migrate')
    parser.add_argument('--region', '-r',
                        type=str,
                        help='AWS Region',
                        choices=['us-west-2'],
                        default='us-west-2')

    args = parser.parse_args()

    main()
