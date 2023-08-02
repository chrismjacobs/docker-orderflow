import boto3
import os
import redis
import json
from pybit import inverse_perpetual, usdt_perpetual
from functools import wraps
from flask import make_response, request

AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
SECRET_KEY = os.getenv('SECRET_KEY')
API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')
TRADE_CODE = os.getenv('TRADE_CODE')
LOCAL = False
DEBUG = False
LOGIN = os.getenv('LOGIN')
REDIS_IP = os.getenv('REDIS_IP')
REDIS_PASS = os.getenv('REDIS_PASS')

# REDIS_URL = 'redis://:' + REDIS_PASS + '@' + REDIS_IP + ':6379'
r = redis.Redis(
    host=REDIS_IP,
    port=6379,
    password=REDIS_PASS,
    decode_responses=True
    )

try:
    LOGIN_DEETS = json.loads(LOGIN)
    print('LOGIN_DEETS', LOGIN_DEETS, type(LOGIN_DEETS))
except Exception as e:
    print('DEETS EXCEPTION', e)
    LOGIN_DEETS = '{"user": "Fail", "code": "0"}'

def auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        username = LOGIN_DEETS['user']
        passcode = LOGIN_DEETS['code']

        if auth and auth.username == username and auth.password == passcode:
            return f(*args, **kwargs)
        return make_response("<h1>Access denied!</h1>", 401, {'WWW-Authenticate': 'Basic realm="Login required!"'})

    return decorated


s3_resource = boto3.resource('s3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key= AWS_SECRET_ACCESS_KEY)

session = inverse_perpetual.HTTP(
    endpoint='https://api.bybit.com',
    api_key= API_KEY,
    api_secret=API_SECRET
)

print('Settings Return', session, r, s3_resource)

# session_unauth_USD = usdt_perpetual.HTTP(
#     endpoint="https://api.bybit.com"
# )
# session_unauth_USDT = inverse_perpetual.HTTP(
#     endpoint="https://api.bybit.com"
# )