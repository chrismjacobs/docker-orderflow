import json
from settings import r, LOCAL, CELERY_BROKER_URL
from taskBlocks import addBlock, getPVAstatus
from taskAux import actionDELTA


from celery import Celery
#from celery.utils.log import get_task_logger

# REDIS_URL = 'redis://:' + REDIS_PASS + '@' + REDIS_IP + ':6379'

celery = Celery('taskLogs', broker=CELERY_BROKER_URL, backend='rpc://')

print('CELERY LOGS', celery, CELERY_BROKER_URL)
#logger = get_task_logger(__name__)




@celery.task()
def logTimeUnit(buyUnit, sellUnit, coin):

    # if not r.get('timeflow_' + coin):
    #     r.set('timeflow_' + coin, json.dumps([]))
    #     r.set('timeblocks_' + coin, json.dumps([]))

    timeflow =  json.loads(r.get('timeflow_' + coin)) # []
    timeblocks = json.loads(r.get('timeblocks_' + coin)) # []

    # print('TIME REDIS', len(timeflow), len(timeblocks))

    if len(timeflow) == 0:
        print('TIME 0 ' + coin)

        ## start the initial time flow and initial current candle
        if buyUnit['size'] > 0:
            timeflow.append(buyUnit)
        if sellUnit['size'] > 0:
            timeflow.append(sellUnit)

        currentCandle = addBlock(timeflow, timeblocks, 'timemode', coin)
        timeblocks.append(currentCandle)

        r.set('timeblocks_' + coin, json.dumps(timeblocks))
        r.set('timeflow_' + coin, json.dumps(timeflow))
    else:
        blockStart = timeflow[0]['trade_time_ms']
        if LOCAL:
            interval = (60000*1) # 1Min
        else:
            interval = (60000*5) # 5Min
        blockFinish = blockStart + interval


        # print('TIME 1')
        if buyUnit['trade_time_ms'] >= blockFinish: # store current candle and start a new Candle
            # print('ADD TIME CANDLE ' + coin)

            # replace current candle with completed candle
            newCandle = addBlock(timeflow, timeblocks, 'timeblock', coin)
            LastIndex = len(timeblocks) - 1
            timeblocks[LastIndex] = newCandle

            timeblocks[LastIndex]['pva_status'] = getPVAstatus(timeblocks, coin)

            # reset timeflow and add new unit
            timeflow = []
            buyUnit['trade_time_ms'] = blockFinish
            sellUnit['trade_time_ms'] = blockFinish
            if buyUnit['size'] > 1:
                timeflow.append(buyUnit)
            if sellUnit['size'] > 1:
                timeflow.append(sellUnit)

            # add fresh current candle to timeblock
            currentCandle = addBlock(timeflow, timeblocks, 'timemode', coin)
            timeblocks.append(currentCandle)
            # print('TIME FLOW RESET: ' + str(len(timeflow)) + ' ' + str(len(timeblocks)))
            r.set('timeblocks_' + coin, json.dumps(timeblocks))
            r.set('timeflow_' + coin, json.dumps(timeflow))

        else: # add the unit to the time flow

            # print('ADD TIME UNIT')
            if buyUnit['size'] > 1:
                timeflow.append(buyUnit)
            if sellUnit['size'] > 1:
                timeflow.append(sellUnit)

            # update current candle with new unit data
            currentCandle = addBlock(timeflow, timeblocks, 'timemode', coin)
            LastIndex = len(timeblocks) - 1
            timeblocks[LastIndex] = currentCandle
            r.set('timeblocks_' + coin, json.dumps(timeblocks))
            r.set('timeflow_' + coin, json.dumps(timeflow))


@celery.task()
def logVolumeUnit(buyUnit, sellUnit, coin, size):    ## load vol flow

    vFlow = 'volumeflow_' + coin + str(size)
    vBlocks = 'volumeblocks_' + coin + str(size)

    if not r.get(vFlow):
        r.set(vFlow, json.dumps([]))
        r.set(vBlocks, json.dumps([]))

    # if LOCAL:
    #     print('LOG VOLUME UNIT SKIP')
    #     return False

    if LOCAL:
        block = size * 100_000
    else:
        block = size * 1_000_000


    volumeflow = json.loads(r.get(vFlow))

    totalMsgSize = buyUnit['size'] + sellUnit['size']

    # if LOCAL:
    #     print(coin + ' LOG VOLUME UNIT ' + str(totalMsgSize))

    ## calculate current candle size
    volumeflowTotal = 0
    for t in volumeflow:
        volumeflowTotal += t['size']

    if volumeflowTotal > block:
        ### Deal with the uncomman event where the last function left an excess on volume flow
        print('VOL FLOW EXCESS ' + str(volumeflowTotal))
        volumeblocks = json.loads(r.get(vBlocks))
        currentCandle = addBlock(volumeflow, volumeblocks, 'volblock_' + str(size), coin)

        volumeblocks[-1] = currentCandle

        volumeflow = []

        if buyUnit['size'] > 1:
            volumeflow.append(buyUnit)
        if sellUnit['size'] > 1:
            volumeflow.append(sellUnit)

        currentCandle = addBlock(volumeflow, volumeblocks, 'vol_' + str(size), coin)

        volumeblocks.append(currentCandle)

        r.set(vBlocks, json.dumps(volumeblocks))
        r.set(vFlow, json.dumps(volumeflow))


    elif volumeflowTotal + totalMsgSize <= block:  # Normal addition of trade to volume flow
        # print(volumeflowTotal, '< Block')

        if buyUnit['size'] > 1:
            volumeflow.append(buyUnit)
        if sellUnit['size'] > 1:
            volumeflow.append(sellUnit)


        volumeblocks = json.loads(r.get(vBlocks))
        currentCandle = addBlock(volumeflow, volumeblocks, 'vol_' + str(size), coin)

        LastIndex = len(volumeblocks) - 1
        if LastIndex < 0:
            volumeblocks.append(currentCandle)
        else:
            volumeblocks[LastIndex] = currentCandle

        r.set(vBlocks, json.dumps(volumeblocks))
        r.set(vFlow, json.dumps(volumeflow))

    else: # Need to add a new block

        # print('carryOver')
        # print('new blockkkkk --  Total msg size: ' + str(totalMsgSize) + ' Vol flow total: ' + str(volumeflowTotal))
        lefttoFill = block - volumeflowTotal

        ## split buys and sells evenly
        if totalMsgSize == 0:
            totalMsgSize = 1

        proportion = lefttoFill/totalMsgSize

        ## left to fill 100_000  totalmsg size 1_300_000  (1_000_000 buys   300_000 sells)
        ## proportion = 0.076

        buyFill = buyUnit['size'] * proportion
        sellFill = sellUnit['size'] * proportion

        buyCopy = buyUnit.copy()
        sellCopy = sellUnit.copy()

        buyCopy['size'] = int(buyFill)
        sellCopy['size'] = int(sellFill)

        if buyCopy['size'] > 0:
            volumeflow.append(buyCopy)
            buyUnit['size'] -= int(buyFill)
        if sellCopy['size'] > 0:
            volumeflow.append(sellCopy)
            sellUnit['size'] -= int(sellFill)

        volumeblocks = json.loads(r.get(vBlocks))
        LastIndex = len(volumeblocks) - 1
        # print('VOL BLOCK BREAK')
        newCandle = addBlock(volumeflow, volumeblocks, 'volblock_' + str(size), coin)
        volumeblocks[LastIndex] = newCandle  # replace last candle (current) with completed

        r.set(vBlocks, json.dumps(volumeblocks))

        ## volume flow has been added as full candle and should be reset
        volumeflow = []

        while buyUnit['size'] > block:
            ## keep appending large blocks
            # r.set('discord_' + coin, 'Carry Over: ' + str(buyUnit['size']) + ' -- ' + str(sellUnit['size']))
            volumeblocks = json.loads(r.get(vBlocks))
            newUnit = buyUnit.copy()
            newUnit['size'] = block
            buyUnit['size'] = buyUnit['size'] - block
            newCandle = addBlock([newUnit], volumeblocks, 'carry_' + str(size), coin)
            volumeblocks.append(newCandle)
            r.set(vBlocks, json.dumps(volumeblocks))

        while sellUnit['size'] > block:
            ## keep appending large blocks
            # r.set('discord_' + coin, 'Carry Over: ' + str(buyUnit['size']) + ' -- ' + str(sellUnit['size']))
            volumeblocks = json.loads(r.get(vBlocks))
            newUnit = sellUnit.copy()
            newUnit['size'] = block
            sellUnit['size'] = sellUnit['size'] - block
            newCandle = addBlock([newUnit], volumeblocks, 'carry_' + str(size), coin)
            volumeblocks.append(newCandle)
            r.set(vBlocks, json.dumps(volumeblocks))

        if buyUnit['size'] + sellUnit['size']  >  block:
            ## This is very unlikley so just set an alert
            r.set('discord_' + coin, 'Unlikley Carry: ' + str(buyUnit['size']) + ' -- ' + str(sellUnit['size']))


        # Create new flow block with left over contracts
        if buyUnit['size'] > 1:
            volumeflow.append(buyUnit)
        if sellUnit['size'] > 1:
            volumeflow.append(sellUnit)

        volumeblocks = json.loads(r.get(vBlocks))
        currentCandle = addBlock(volumeflow, volumeblocks, 'vol_' + str(size), coin)
        volumeblocks.append(currentCandle)
        r.set(vBlocks, json.dumps(volumeblocks))
        r.set(vFlow, json.dumps(volumeflow))


@celery.task()
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
            print('DELTA STATUS', len(deltablocks), len(deltaflow), len(deltaStatus['deltaflowList']))

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
    # try:
    #     sess = session.latest_information_for_symbol(symbol='BTCUSD')
    #     streamOI = sess['result'][0]['open_interest']
    # except Exception as e:
    #     print('STREAM EXCEPTION', e)
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


