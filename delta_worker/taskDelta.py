import json
from settings import r, LOCAL, CELERY_BROKER_URL, session
from taskAux import actionDELTA


from celery import Celery
from celery.utils.log import get_task_logger
logger = get_task_logger(__name__)

celery = Celery('taskDelta', broker=CELERY_BROKER_URL, backend='rpc://')

print('CELERY LOGS', celery, CELERY_BROKER_URL)


@celery.task(name='logDeltaUnit')
def logDeltaUnit(buyUnit, sellUnit, coin, deltaCount):

    # add a new unit which is msg from handle_message

    dFlow = 'deltaflow_' + coin
    dBlocks = 'deltablocks_' + coin

    if not r.get(dFlow):
        r.set(dFlow, json.dumps([]))
        r.set(dBlocks, json.dumps([]))

    deltaflow =  json.loads(r.get('deltaflow_' + coin)) # []
    deltablocks = json.loads(r.get('deltablocks_' + coin)) # []

    if len(deltaflow) == 0:
        print('DELTA 0')

        ## start the initial delta flow and initial current candle
        if buyUnit['size'] > 1:
            deltaflow.append(buyUnit)
        if sellUnit['size'] > 1:
            deltaflow.append(sellUnit)

        currentCandle = addDeltaBlock(deltaflow, deltablocks, deltaCount, coin)
        deltablocks.append(currentCandle)

        r.set('deltablocks_' + coin, json.dumps(deltablocks))
        r.set('deltaflow_' + coin, json.dumps(deltaflow))
    else:
        if buyUnit['size'] > 1:
            deltaflow.append(buyUnit)
        if sellUnit['size'] > 1:
            deltaflow.append(sellUnit)

        deltaStatus = getDeltaStatus(deltaflow, deltaCount)


        if LOCAL:
            print('DELTA STATUS' + str(len(deltaStatus)))

        if deltaStatus['blockfill']:
            # store current candle and start a new Candle

            # replace current candle with completed candle
            dcount = 0
            for flow in deltaStatus['deltaflowList']:
                # for f in flow:
                #     print('DeltaFlowList ' + str(dcount) + ' ' + f['side'] + ' ' + str(f['size']))

                zero = deltaStatus['deltaflowList'].index(flow)
                if zero == 0:

                    print('ADD BLOCK ZERO')

                    newCandle = addDeltaBlock(flow, deltablocks, deltaCount, coin)
                    ### replace last block (unfillled becomes filled)
                    deltablocks[-1] = newCandle

                else:

                    currentCandle = addDeltaBlock(flow, deltablocks, deltaCount, coin)
                    deltablocks.append(currentCandle)
                    if deltaStatus['deltaflowList'].index(flow) == len(deltaStatus['deltaflowList']) - 1:
                        # reset deltaflow - the last delta block
                        deltaflow = flow

                dcount += 1


            r.set('deltablocks_' + coin, json.dumps(deltablocks))
            r.set('deltaflow_' + coin, json.dumps(deltaflow))

        else: # add the unit to the delta flow

            # print('ADD DELTA UNIT') # len(deltablocks), len(deltaflow)

            # update current candle with new unit data
            currentCandle = addDeltaBlock(deltaflow, deltablocks, deltaCount, coin)
            deltablocks[-1] = currentCandle
            r.set('deltablocks_' + coin, json.dumps(deltablocks))
            r.set('deltaflow_' + coin, json.dumps(deltaflow))


def addDeltaBlock(units, blocks, deltaCount, coin):

    # units == flow

    coinDict = json.loads(r.get('coinDict'))


    ''' BLOCK DATA '''

    #  print('BLOCK DATA: ' + mode + ' -- ' + coin)

    previousTime = units[0]['trade_time_ms']
    newOpen = units[0]['streamPrice']
    price = units[-1]['streamPrice']

    ## if just one block than that is the current candle
    ## if last candle is not filled then get previous candle

    lastCandleisBlock = True
    lastOI = 0

    if len(blocks) > 1:
        lastCandle = blocks[-1]
        lastCandleisBlock = lastCandle['delta'] == deltaCount or lastCandle['delta'] == -deltaCount
        lastOI = lastCandle['oi_close']

        if not lastCandleisBlock:
            lastCandle = blocks[-2] # ignore last unit which is the current one
            lastOI = lastCandle['oi_close']

        previousTime = lastCandle['trade_time_ms']
        newOpen = lastCandle['close']


    newStart  = units[0]['trade_time_ms']
    newClose = units[-1]['trade_time_ms']

    # if LOCAL:
    #     print('TIME CHECK', previousTime, newClose, newStart, type(newClose), type(newStart))

    timeDelta = newClose - newStart

    buyCount = 0
    sellCount = 0
    highPrice = 0
    lowPrice = 0

    priceList = []

    tradecount = 0

    for d in units:
        # print('BLOCK LOOP', d)

        tradecount += d['tradecount']

        if d['side'] == 'Buy':
            buyCount += d['size']
        else:
            sellCount += d['size']

        for price in d['spread']:

            price = float(price)
            priceList.append(price)


    highPrice = max(priceList)
    lowPrice = min(priceList)

    delta = buyCount - sellCount
    priceDelta = price - newOpen

    switch = False

    streamOI = lastOI

    deltaOI = streamOI - lastOI



    newDeltaCandle = {
        'trade_time_ms' : newClose,
        'timestamp' : str(units[0]['timestamp']),
        'time_delta' : timeDelta,
        'close' : price,
        'open' : newOpen,
        'price_delta' : priceDelta,
        'high' : highPrice,
        'low' : lowPrice,
        'buys' : buyCount,
        'sells' : sellCount,
        'delta' : delta,
        'total' : buyCount + sellCount,
        'switch' : switch,
        'tradecount' : tradecount,
        'oi_delta': deltaOI,
        'oi_close': streamOI,
    }

    newCandleisBlock = delta == deltaCount or delta == -deltaCount

    if coin == 'BTC' and newCandleisBlock:
        newDeltaCandle['switch'] = actionDELTA(blocks, newDeltaCandle, coin, coinDict, lastCandleisBlock)
        ### require code to record OI on delta candles; although this session api may cause a delay
        if timeDelta > 5000:
            try:
                sess = session.latest_information_for_symbol(symbol='BTCUSD')
                streamOI = sess['result'][0]['open_interest']
                newDeltaCandle['oi_close'] = streamOI
                newDeltaCandle['oi_delta'] = streamOI - lastOI

            except Exception as e:
                print('STREAM EXCEPTION', e)

    return newDeltaCandle

def getDeltaStatus(deltaflow, deltaCount):

    # if LOCAL:
    #     print('GET DELTA STATUS', len(deltaflow))

    newDeltaflowList = []

    totalBuys = 0
    totalSells = 0

    blockfill = False
    fillMarker = False # toggle when unfilled block is added at the end


    deltaflowList = [[]]

    for d in deltaflow:

        size = d['size']

        if d['side'] == 'Buy':
            totalBuys += size

        elif d['side'] == 'Sell':
            totalSells += size

        ## 4k Buys
        ## 13K Sells
        ## delta -9K

        # newDeltaflowList.append([
        #     {
        #         "side": d['side'],
        #         "size": d['size'],
        #         'totalBS_ABS' : [str(totalBuys) , str(totalSells), str(abs((totalBuys - totalSells)))]
        #     }
        # ])

        excess = 0

        if totalBuys - totalSells <  - deltaCount or totalBuys - totalSells > deltaCount:
            blockfill = True
            fillMarker = True
            excess = abs(totalBuys - totalSells) - deltaCount


        if blockfill and fillMarker: #posDelta or negDelta:
            ## complete delta flow

            completeUnit = d.copy()

            completeUnit['size'] -= excess
            deltaflowList[-1].append(completeUnit)

            # Excess UNIT SIZE 1084 10352 0 10352 352
            # Excess UNIT SIZE 2 10352 2 10350 350

            while excess >= deltaCount:
                adjustUnit = d.copy()
                adjustUnit['size'] = deltaCount
                excess -= deltaCount
                deltaflowList.append([adjustUnit])
                # print('excess unit added ' + str(excess))


            if excess == 0:
                excess = 1


            finalUnit = d.copy()
            finalUnit['size'] = excess
            deltaflowList.append([finalUnit])
            # print('surplus unit added ' + str(excess))


            # printDict = {
            #     'UNIT SIZE': completeUnit['size'],
            #     'SIDE' : completeUnit['side'],
            #     'LENGTH' : len(deltaflow),
            #     'totalBS' : [totalBuys , totalSells],
            #     'abs' : abs((totalBuys - totalSells)),
            #     'excess' : excess,
            #     'counted unit' : newDeltaflowList,
            #     'currentnewList' : deltaflowList
            # }
            # print('EXCESS ' + json.dumps(printDict))

            fillMarker = False
            totalBuys = 0
            totalSells = 0

        else:
            deltaflowList[-1].append(d)


    return {
            'flowdelta' : totalBuys - totalSells,
            'blockfill' : blockfill,
            'deltaflowList' : deltaflowList
    }


