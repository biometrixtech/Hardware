#!/usr/bin/env python3
# Migrate sensors from postgres to dynamodb

from colorama import Style, Fore
import argparse
import boto3
import json
import requests

aws_account_id = '887689817172'

jwt = None


def cprint(*pargs, **kwargs):
    """
    Print a string to the terminal with colour

    :param pargs: args to print()
    :param kwargs: kwargs to print()
    """
    if 'colour' in kwargs:
        print(kwargs['colour'], end="")
        del kwargs['colour']

        end = kwargs.get('end', '\n')
        kwargs['end'] = ''
        print(*pargs, **kwargs)

        print(Style.RESET_ALL, end=end)

    else:
        print(*pargs, **kwargs)


def _get_service_token():
    global jwt
    if jwt is None:
        res = invoke_lambda(f'users-{args.environment}-apigateway-serviceauth')
        jwt = res['token']
    return jwt


def invoke_lambda(function_name, payload=None):
    lambda_client = boto3.client('lambda', region_name=args.region)
    return json.loads(lambda_client.invoke(
        FunctionName=f'arn:aws:lambda:{args.region}:{aws_account_id}:function:{function_name}',
        Payload=json.dumps(payload),
    )['Payload'].read().decode('utf-8'))


def query_postgres(query, parameters):
    res = invoke_lambda(
        f'infrastructure-{args.environment}-querypostgres',
        {"Queries": [{"Query": query, "Parameters": parameters}], "Config": {"ENVIRONMENT": args.environment}}
    )
    result, error = res['Results'][0], res['Errors'][0]
    if error is not None:
        raise Exception(error)
    elif isinstance(result, list):
        return result
    else:
        return []


def make_request(url, payload):
    return res.status_code


def main():
    sensors = query_postgres("SELECT * FROM sensors", None)
    print('{} sensors to migrate'.format(len(sensors)))

    for i, sensor in enumerate(sensors):
        url = f"https://apis.{args.environment}.fathomai.com/hardware/latest/sensor/{sensor['id']}"
        payload = {
            "mac_address": sensor['id'],
            "battery_level": None,
            "memory_level": str(sensor['memory_level'] or 0),
            "firmware_version": sensor['firmware_version'] or '0.0.0',
            "hardware_model": sensor['hw_model'],
            "created_date": sensor['created_at'],
            "updated_date": sensor['updated_at'],
            "last_user_id": sensor['last_user_id'],
        }
        headers = {'Authorization': _get_service_token(), 'Accept': 'application/json'}
        res = requests.put(url, json={k: v for k, v in payload.items() if v is not None}, headers=headers)
        if res.status_code == 200:
            cprint(f'{url} --> {res.status_code}', colour=Fore.GREEN)
        else:
            cprint(f'{url} --> {res.status_code}', colour=Fore.RED)
            cprint(json.dumps(payload, indent=4), colour=Fore.LIGHTRED_EX)
            cprint(res.json(), colour=Fore.RED)
            break


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
