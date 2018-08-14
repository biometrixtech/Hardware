from flask import request
from functools import wraps
import boto3
import json
import jwt
import os
import re
from exceptions import UnauthorizedException


def authentication_required(decorated_function):
    """Decorator to require a JWT token to be passed."""
    @wraps(decorated_function)
    def wrapper(*args, **kwargs):
        if 'Authorization' in request.headers:
            raw_token = request.headers['Authorization']
        elif 'jwt' in request.headers:
            # Legacy 10.1 firmware
            raw_token = request.headers['jwt']
        else:
            raise UnauthorizedException("Must submit a JWT in 'Authorization' header")

        if not raw_token:
            raise UnauthorizedException('No Authorization token provided')
        try:
            token = jwt.decode(raw_token, verify=False)
        except Exception:
            raise UnauthorizedException('Token not a valid JWT')

        try:
            authenticate_hardware_jwt(raw_token)
            # A hardware client
            return decorated_function(*args, **kwargs)
        except UnauthorizedException:
            try:
                # A dashboard client
                authenticate_user_jwt(raw_token)
                return decorated_function(*args, **kwargs)
            except UnauthorizedException:
                raise
    return wrapper


def authenticate_user_jwt(token):
    res = json.loads(boto3.client('lambda').invoke(
        FunctionName='users-{ENVIRONMENT}-apigateway-validateauth'.format(**os.environ),
        Payload=json.dumps({"authorizationToken": token}),
    )['Payload'].read())
    print(res)

    if 'principalId' in res:
        # Success
        return res['principalId']
    elif 'errorMessage' in res:
        # Some failure
        raise UnauthorizedException(res['errorMessage'])


def authenticate_hardware_jwt(token):
    res = json.loads(boto3.client('lambda').invoke(
        FunctionName='hardware-{ENVIRONMENT}-apigateway-validateauth'.format(**os.environ),
        Payload=json.dumps({"authorizationToken": token}),
    )['Payload'].read())
    print(res)

    if 'principalId' in res:
        # Success
        return res['principalId']
    elif 'errorMessage' in res:
        # Some failure
        raise UnauthorizedException(res['errorMessage'])


def validate_mac_address(string):
    return re.match('^[0-9A-Z]{2}:[0-9A-Z]{2}:[0-9A-Z]{2}:[0-9A-Z]{2}:[0-9A-Z]{2}', string.upper())
