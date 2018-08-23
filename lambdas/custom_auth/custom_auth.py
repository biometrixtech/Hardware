from jose import jwk, jwt
from jose.utils import base64url_decode
import datetime
import json
import os
import re
import urllib.request


def validate_handler(event, _):
    print(event)

    raw_token = event.get('authorizationToken', None)
    if not raw_token:
        raise Exception('No raw token')

    user_id = get_mac_address_from_jwt(raw_token)

    return {"principalId": user_id}


def get_mac_address_from_jwt(raw_token):

    try:
        token = jwt.get_unverified_claims(raw_token)
        validate_rs256_signature(raw_token)
    except Exception:
        raise Exception('Not a valid JWT')

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


def validate_rs256_signature(raw_token):
    public_key = get_rs256_public_key(raw_token)

    message, encoded_signature = str(raw_token).rsplit('.', 1)
    print(encoded_signature)
    decoded_signature = base64url_decode(encoded_signature.encode('utf-8'))
    print(decoded_signature)

    if not public_key.verify(message.encode("utf8"), decoded_signature):
        raise Exception('Signature verification failed')


cognito_keys_cache = {}


def get_rs256_public_key(raw_token):
    key_id = jwt.get_unverified_header(raw_token)['kid']

    if key_id not in cognito_keys_cache:
        token = jwt.get_unverified_claims(raw_token)
        cognito_userpool_id = token['iss'].split('/')[-1]
        cognito_keys_url = f'https://cognito-idp.{os.environ["AWS_DEFAULT_REGION"]}.amazonaws.com/{cognito_userpool_id}/.well-known/jwks.json'
        print(f'Loading new keys from {cognito_keys_url}')
        keys = json.loads(urllib.request.urlopen(cognito_keys_url).read())
        cognito_keys_cache.update({k['kid']: k for k in keys['keys']})

    if key_id not in cognito_keys_cache:
        raise Exception('Unknown signing key')

    return jwk.construct(cognito_keys_cache[key_id])


def validate_mac_address(string):
    return re.match('^[0-9A-Z]{2}:[0-9A-Z]{2}:[0-9A-Z]{2}:[0-9A-Z]{2}:[0-9A-Z]{2}', string.upper())
