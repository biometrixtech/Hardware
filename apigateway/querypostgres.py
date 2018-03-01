import boto3
import json
import os

from aws_xray_sdk.core import xray_recorder


@xray_recorder.capture('querypostgres.query_postgres')
def query_postgres(query, parameters):
    lambda_client = boto3.client('lambda', region_name=os.environ['AWS_REGION'])
    res = json.loads(lambda_client.invoke(
        FunctionName='arn:aws:lambda:{AWS_REGION}:{AWS_ACCOUNT_ID}:function:infrastructure-{ENVIRONMENT}-querypostgres'.format(**os.environ),
        Payload=json.dumps({
            "Queries": [{"Query": query, "Parameters": parameters}],
            "Config": {"ENVIRONMENT": os.environ['ENVIRONMENT']}
        }),
    )['Payload'].read().decode('utf-8'))
    result, error = res['Results'][0], res['Errors'][0]
    if error is not None:
        raise Exception(error)
    elif isinstance(result, list):
        return result
    else:
        return []
