import json
from settings import r, LOCAL, CELERY_BROKER_URL
from taskBlocks import addBlock, getPVAstatus


from celery import Celery
from celery.utils.log import get_task_logger
logger = get_task_logger(__name__)

celery = Celery('taskLogs', broker=CELERY_BROKER_URL, backend='rpc://')

print('CELERY LOGS', celery, CELERY_BROKER_URL)


@celery.task(name='logTimeUnit')
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


@celery.task(name='logVolumeUnit')
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

