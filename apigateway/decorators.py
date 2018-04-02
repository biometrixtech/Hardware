from flask import request
from functools import wraps
import boto3
import json
import os
from exceptions import UnauthorizedException


def authentication_required(decorated_function):
    """Decorator to require a JWT token to be passed."""
    @wraps(decorated_function)
    def wrapper(*args, **kwargs):
        if 'Authorization' in request.headers and authenticate_user_jwt(request.headers['Authorization']):
            return decorated_function(*args, **kwargs)
        elif 'jwt' in request.headers and authenticate_user_jwt(request.headers['jwt']):
            # Legacy 10.1 firmware
            return decorated_function(*args, **kwargs)
        else:
            raise UnauthorizedException()
    return wrapper


def authenticate_user_jwt(jwt):
    res = json.loads(boto3.client('lambda').invoke(
        FunctionName='users-{ENVIRONMENT}-apigateway-authenticate'.format(**os.environ),
        Payload=json.dumps({"authorizationToken": jwt}),
    )['Payload'].read())
    print(res)

    if 'principalId' in res:
        # Success
        return res['principalId']
    elif 'errorMessage' in res:
        # Some failure
        raise UnauthorizedException()
