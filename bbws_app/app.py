import json, math, time

from time import sleep
import datetime as dt
from datetime import datetime

from pybit import inverse_perpetual, usdt_perpetual

from settings import r, session, LOCAL, AUX_ACTIVE, CELERY_BROKER_URL

from taskBot import  setCoinDict, startDiscord, sendMessage

from celery import Celery
from celery.utils.log import get_task_logger

celeryapp = Celery('celery_worker', broker=CELERY_BROKER_URL, backend='rpc://')

## configure the routes of tasks to different workers noted as exchanges and marked in the celery command as -Q (queue)
celeryapp.config_from_object('celeryconfig')


print('CELERY APP', celeryapp, CELERY_BROKER_URL)
logger = get_task_logger(__name__)


def manageStream(pair, coin):

    stream = json.loads(r.get('stream_' + coin))


    ### to speed up processing latest information is called only 30% of the time
    t = dt.datetime.today()
    if t.microsecond < 300000:
        sess = session.latest_information_for_symbol(symbol=pair)
        streamOI = sess['result'][0]['open_interest']
        streamTime = round(float(sess['time_now']), 1)
        streamPrice = float(sess['result'][0]['last_price'])
    else:
        streamOI = stream['lastOI']
        streamPrice = stream['lastPrice']
        streamTime =  stream['lastTime']


    stream['lastTime'] = streamTime
    stream['lastPrice'] = streamPrice
    stream['lastOI'] = streamOI
    # print(stream)

    timeblocks = json.loads(r.get('timeblocks_' + coin))
    currentBuys = 0
    currentSells = 0
    if len(timeblocks) > 1:
        currentBuys = timeblocks[-1]['buys']
        currentSells = timeblocks[-1]['sells']
        currentBuys += timeblocks[-2]['buys']
        currentSells += timeblocks[-2]['sells']




    if len(stream['1mOI']) < 2:
        print('INITIAL')
        stream['1mOI'] = [streamTime, streamOI]
    elif streamTime - stream['1mOI'][0] >= 90:

        deltaOI =  streamOI - stream['1mOI'][1]
        deltaOIstr = str(round(deltaOI/100_000)/10) + 'm '
        deltaBuyStr = str(round(currentBuys/100_000)/10) + 'm '
        deltaSellStr = str(round(currentSells/100_000)/10) + 'm '

        if stream['oiMarkers'][0] > 0 and deltaOI > stream['oiMarkers'][0]:
            message = 'OI INC: ' + deltaOIstr + ' Buys:' + deltaBuyStr + ' Sells: ' + deltaSellStr + ' Price: ' + str(stream['lastPrice'])
            sendMessage(coin, message, '', 'blue')

        if stream['oiMarkers'][1] > 0 and deltaOI < - stream['oiMarkers'][1]:
            message = 'OI DEC: ' + deltaOIstr + ' Buys: ' + deltaBuyStr + ' Sells: ' + deltaSellStr  + ' Price: ' + str(stream['lastPrice'])
            sendMessage(coin, message, '', 'pink')


        stream['1mOI'] = [streamTime, streamOI]

    else:
        stream['oi delta'] = [round(streamTime - stream['1mOI'][0]), streamOI - stream['1mOI'][1], '(secs/oi)' ]

    # print(stream)
    r.set('stream_' + coin, json.dumps(stream) )

    return stream


def getPreviousDay(blocks):

    try:
        dailyOpen = blocks[0]['open']
        dailyClose = blocks[-1]['close']
        dailyPriceDelta = dailyClose - dailyOpen
        dailyCVD = blocks[-1]['delta_cumulative']
        dailyDIV = False

        if dailyPriceDelta < 0 and dailyCVD > 0:
            dailyDIV = True
        elif dailyPriceDelta > 0 and dailyCVD < 0:
            dailyDIV = True

        dailyVolume = 0

        for b in blocks:
            dailyVolume += b['total']

        return json.dumps({
            'VOL: ' : round(dailyVolume/100_000)/10,
            'CVD:' : round(dailyCVD/100_000)/10,
            'Price:' : dailyPriceDelta,
            'DIV' : dailyDIV
            })

    except:
        return 'getPreviousDay() fail'


def historyReset(coin):
    # print('HISTORY RESET ' + coin)

    if r.get('history_' + coin) == None:
        r.set('history_' + coin, json.dumps([]))

    current_time = dt.datetime.utcnow()

    dt_string = current_time.strftime("%d/%m/%Y")

    if current_time.hour == 23 and current_time.minute == 59:
        print('History Reset Current Time UTC : ' + str(current_time))
        history = json.loads(r.get('history_' + coin))

        pdDict = {
                    'date' : dt_string,
                }

        for k in r.keys():
            if 'blocks' in k and coin in k:
                pdDict[k] = json.loads(r.get(k))
                print('History Loads ' + k)

        if len(history) > 0:
            lastHistory = json.loads(r.get('history_' + coin))[len(history)-1]

            if lastHistory['date'] != dt_string:
                print('REDIS STORE', dt_string)

                history.append(pdDict)

                r.set('history_' + coin, json.dumps(history))

                if coin == 'BTC':
                    tb = json.loads(r.get('timeblocks_BTC'))
                    pd = getPreviousDay(tb)
                    r.set('discord_' + coin, 'history log: ' + pd)
        else:
            print('REDIS STORE INITIAL')

            history.append(pdDict)
            r.set('history_' + coin, json.dumps(history))

            if coin == 'BTC':
                    tb = json.loads(r.get('timeblocks_BTC'))
                    pd = getPreviousDay(tb)
                    r.set('discord_' + coin, 'history log: ' + pd)

    if current_time.hour == 0 and current_time.minute == 0:
        print('REDIS RESET', current_time)
        if r.get('newDay_' + coin) != dt_string:
            print('REDIS RESET')

            for k in r.keys():
                if k[0] == 'v':
                    r.delete(k)
                print(k)


            r.set('timeflow_' + coin, json.dumps([]) )  # this is the flow of message data to create next candle
            r.set('timeblocks_' + coin, json.dumps([]) ) # this is the store of new time based candles
            r.set('newDay_' + coin, dt_string)

            r.set('discord_' + coin, coin + ' new day')

    return True


def compiler(message, pair, coin):

    timestamp = message[0]['timestamp']
    ts = str(datetime.strptime(timestamp.split('.')[0], "%Y-%m-%dT%H:%M:%S"))
    trade_time_ms = int(message[0]['trade_time_ms'])


    stream = manageStream(pair, coin)
    streamOI = stream['lastOI']
    streamTime = stream['lastTime']
    streamPrice = stream['lastPrice']


    buyUnit = {
                    'side' : 'Buy',
                    'size' : 0,
                    'trade_time_ms' : trade_time_ms,
                    'timestamp' : ts,
                    'streamTime' : streamTime,
                    'streamPrice' : streamPrice,
                    'streamOI' : streamOI,
                    'tradecount' : 0,
                    'spread' : {}
                }

    sellUnit = {
                    'side' : 'Sell',
                    'size' : 0,
                    'trade_time_ms' : trade_time_ms,
                    'timestamp' : ts,
                    'streamTime' : streamTime,
                    'streamPrice' : streamPrice,
                    'streamOI' : streamOI,
                    'tradecount' : 0,
                    'spread' : {}
    }

    for x in message:

        size = x['size']

        if coin == 'BTC':
            #  21010.51 -->  42020.2 --> 42020 --> 21010.5
            priceString = str(  round  ( float(x['price'])  *2 )/2)
        elif coin == 'ETH':
            # 1510.21 -->  30204.2 --> 30204 --> 15102 --> 1510.2
            priceString = str(  round  ( float(x['price'])  *100 )/100)
        elif coin == 'SOL':
            # 23.645  -->  23.645 --> 30204 --> 15102 --> 1510.2
            priceString = str(  round  ( float(x['price'])  *100 )/100)
            size = round ( x['size']*10  )  / 10
        elif coin == 'GALA':
            # 0.04848 -- >
            priceString = str(  round  ( float(x['price'])  *100000 )/100000)
            size = round ( x['size']*10  )  / 10
        elif coin == 'BIT':
            # 0.5774
            priceString = str(  round  ( float(x['price'])  *10000 )/10000)
            size = round ( x['size']*10  )  / 10

        if x['side'] == 'Buy':
            spread = buyUnit['spread']
            if priceString not in spread:
                spread[priceString] = size
            else:
                spread[priceString] += size

            buyUnit['size'] += size
            buyUnit['tradecount'] += 1

        if x['side'] == 'Sell':
            spread = sellUnit['spread']
            if priceString not in spread:
                spread[priceString] = size
            else:
                spread[priceString] += size

            sellUnit['size'] += x['size']
            sellUnit['tradecount'] += 1

    # print(coin + ' COMPILER RECORD:  Buys - ' + str(buyUnit['size']) + ' Sells - ' + str(sellUnit['size']) )

    return [buyUnit, sellUnit]


def handle_trade_message(msg):

    pair = msg['topic'].split('.')[1]
    coin = pair.split('USD')[0]

    coinDict = json.loads(r.get('coinDict'))

    # print(coinDict)

    if not coinDict[coin] or not coinDict[coin]['active']:
        ## print('not active ' + coin)
        return False

    if coinDict[coin] and coinDict[coin]['purge']:
        print('purge ' + coin)
        for k in r.keys():
            if coin in k:
                r.delete(k)

    ### check time and reset
    historyReset(coin)

    # print(coin + ' handle_trade_message: ' + str(len(msg['data'])))
    # print(msg['data'])

    # print( 'Start: ' + str(len(msg['data'])))
    compiledMessage = compiler(msg['data'], pair, coin)


    # print('COMPILER DONE')

    buyUnit = compiledMessage[0]
    sellUnit = compiledMessage[1]
    if LOCAL:
        print('Compiled B:' + str(buyUnit['size']) + ' S:' + str(sellUnit['size']))

    if buyUnit['size'] + sellUnit['size'] <= 2:
        return False

    volControl = coinDict[coin]['volume']
    deltaControl = coinDict[coin]['deltaswitch']
    pause = coinDict[coin]['pause']


    print('LOG TIME')
    celeryapp.send_task('logTimeUnit', kwargs={'buyUnit': buyUnit, 'sellUnit' : sellUnit, 'coin' : coin})



    if volControl[0]: # ignore small size trades
        celeryapp.send_task('logVolumeUnit', kwargs={'buyUnit': buyUnit, 'sellUnit' : sellUnit, 'coin' : coin, 'size' : int(volControl[1])} )

    print('LOG VOLUME')


    if deltaControl['fcCheck'] > 0:
        deltaCount = deltaControl['block']
        if LOCAL:
            deltaCount = 10000
        celeryapp.send_task('logDeltaUnit', kwargs={'buyUnit': buyUnit, 'sellUnit' : sellUnit, 'coin' : coin, 'deltaCount' : deltaCount} )

    print('LOG DELTA')


def runStream():
    ## delay start until time ready
    block = True

    if int(AUX_ACTIVE) != 1:
        block = False

    while block:
        t = dt.datetime.today()
        print(t.minute, t.minute%5)
        if t.minute%5 == 0:
            ## multiple of 5 mins
            block = False
        else:
            time.sleep(5)


    print('RUN_STREAM')    # rK = json.loads(r.keys())


    for k in r.keys():
        if k[0] != '_' and k != 'coinDict' and k != 'channelDict' and k != 'task_id':
            r.delete(k)

    if not r.get('coinDict'):
        setCoinDict()

    coinDict = json.loads(r.get('coinDict'))


    for c in coinDict:
        rDict = {
            'lastPrice' : 0,
            'lastTime' : 0,
            'lastOI' : 0,
            '1mOI' : [],
            'oiMarkers' : coinDict[c]['oicheck'],
            'Divs' : {},
            'alerts' : []
        }
        r.set('stream_' + c, json.dumps(rDict) )
        r.set('timeflow_' + c, json.dumps([]) )  # this the flow of message data to create next candle
        r.set('timeblocks_' + c, json.dumps([]) ) # this is the store of new time based candles


    print('WEB_SOCKETS')

    ws_inverseP = inverse_perpetual.WebSocket(
        test=False,
        ping_interval=30,  # the default is 30
        ping_timeout=None,  # the default is 10 # set to None and it will never timeout?
        domain="bybit"  # the default is "bybit"
    )

    coins = ["BTCUSD"] #"BITUSD"
    if LOCAL:
        coins = ["BTCUSD"]

    ws_inverseP.trade_stream(
        handle_trade_message, coins
    )

    # ws_usdtP = usdt_perpetual.WebSocket(
    #     test=False,
    #     ping_interval=30,  # the default is 30
    #     ping_timeout=None,  # the default is 10 # set to None and it will never timeout?
    #     domain="bybit"  # the default is "bybit"
    # )

    # ws_usdtP.trade_stream(
    #     handle_trade_message, ["GALAUSDT"]
    # )


    # ws_inverseP.instrument_info_stream(
    #     handle_info_message, "BTCUSD"
    # )


    startDiscord()

    while True:
        sleep(0.1)

    return print('Task Closed')


if __name__ == '__main__':
    runStream()










