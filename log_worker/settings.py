
import redis
from pybit import inverse_perpetual, usdt_perpetual
import os

print('RUN BBWS SETTINGS')

API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')
REDIS_PASS = os.getenv('REDIS_PASS')
REDIS_IP = os.getenv('REDIS_IP')
AUX_ACTIVE = os.getenv('AUX_ACTIVE')
DISCORD_WEBHOOK = os.getenv('DISCORD_WEBHOOK')
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL')

LOCAL = False

if int(AUX_ACTIVE) != 1:
    LOCAL = True


r = redis.Redis(
    host=REDIS_IP,
    port=6379,
    password=REDIS_PASS,
    decode_responses=True
    )

session = inverse_perpetual.HTTP(
    endpoint='https://api.bybit.com',
    api_key=API_KEY,
    api_secret=API_SECRET
)


print('REDIS', r, REDIS_IP, REDIS_PASS)
print('API', session, str(session.get_wallet_balance()['result']['BTC']['equity']))
