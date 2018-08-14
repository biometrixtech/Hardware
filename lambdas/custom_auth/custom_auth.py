import datetime
import jwt
import os
import re


def validate_handler(event, _):
    print(event)

    raw_token = event.get('authorizationToken', None)
    if not raw_token:
        raise Exception('No raw token')

    user_id = get_mac_address_from_jwt(raw_token)

    return {"principalId": user_id}


def get_mac_address_from_jwt(raw_token):

    try:
        token = jwt.decode(raw_token, verify=False)  # TODO verify
    except Exception:
        raise

    print({'jwt_token': token})
    if 'username' in token:
        principal = token['username']
    else:
        raise Exception('No username in token')

    if not validate_mac_address(principal):
        raise Exception('Username is not a valid MAC address')

    if 'exp' not in token:
        raise Exception('No expiry time in token')
    expiry_date = datetime.datetime.fromtimestamp(token['exp'])
    now = datetime.datetime.utcnow()
    if expiry_date < now:
        raise Exception(f'Token has expired: {expiry_date.isoformat()} < {now.isoformat()}')

    return principal.upper()


def validate_mac_address(string):
    return re.match('^[0-9A-Z]{2}:[0-9A-Z]{2}:[0-9A-Z]{2}:[0-9A-Z]{2}:[0-9A-Z]{2}', string.upper())
