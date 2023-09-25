
import json
from datetime import datetime
from settings import r, session, LOCAL, AUX_ACTIVE, DISCORD_WEBHOOK
from discord import SyncWebhook


def sendMessage(coin, string, bg, text):
    str1 = "```ansi\n"

    escape =  "\u001b[0;"   ## 0 == normal text  1 bold

    colors = {  ### bg / text
        '': [''],
        'grey': ['44;'],
        'red' : ['45;', '31m'],
        'green' : ['43;', '32m'],
        'yellow' : ['41;', '33m'],
        'blue' : ['40;', '34m'],
        'pink' : ['45;', '35m'],
        'cyan' : ['42;', '36m'],
        'white' : ['47;', '37m']
    }
    ## bground first then color

    str2 = "\n```"

    msg = str1 + escape +  colors[bg][0] + colors[text][1] + string + str2

    ansi = r.get('ansi')
    if not ansi:
        ansi = 'on'
        r.set('ansi', ansi)

    if ansi == 'off':
        msg = string

    if not coin:
        return msg
    elif r.get('discord_' + coin) != 'blank':
        r.set('discord_' + coin, msg)
    else:
        r.set('discord_' + coin + '_holder', msg)

def getHL(side, current, stop, mode):

    now = datetime.now()
    minutes = 5
    timestamp = int(datetime.timestamp(now)) - int(minutes)*60
    data = session.query_kline(symbol="BTCUSD", interval="1", from_time=str(timestamp))['result']

    hAry = []
    lAry = []

    for i in range(0, len(data)):
        hAry.append(int(data[i]['high'].split('.')[0]))
        lAry.append(int(data[i]['low'].split('.')[0]))

    mHi = max(hAry)
    mLow = min(lAry)

    if side == 'Buy':
        distance = abs(current - mLow)
        if distance > stop:
            stop_loss = current - stop
        else:
            stop_loss = mLow - 45

    if side == 'Sell':
        distance = abs(current - mHi)
        if distance > stop:
            stop_loss = current + stop
        else:
            stop_loss = mHi + 45


    return stop_loss

def marketOrder(side, fraction, stop, profit, mode):

    pair = 'BTCUSD'

    position = session.my_position(symbol=pair)['result']

    positionSide = position['side']
    positionSize = int(position['size'])
    positionLev = float(position['leverage'])

    if positionSize > 0 or positionLev > 2:
        message = 'Position already open: ' + positionSide + ' ' + str(positionLev)
        print(message)
        sendMessage('BTC', message, '', 'red')
        return False
    # else:
    #     print('Order continue')

    price = float(session.latest_information_for_symbol(symbol=pair)['result'][0]['last_price'])
    funds = session.get_wallet_balance()['result']['BTC']['equity']
    # leverage = 2
    # session.set_leverage(symbol=pair, leverage=leverage)
    qty = (price * funds * 2) * fraction

    #stop_loss = getHL(side, price, stop, mode)

    stop_adjust = stop

    try:
        if stop_adjust < 1:
            stop_adjust = price*(stop/100)/positionLev
        if stop_adjust > 100 or stop_adjust < 30:
            stop_adjust = 70
    except:
        print('STOP LOSS Adjust failed')




    limits = {
        'Buy' : -1,
        'Sell' : 1
    }

    sideRev = None

    if side == 'Buy':
        take_profit = price + profit
        stop_loss = price - stop_adjust
        sideRev = 'Sell'
    if side == 'Sell':
        take_profit = price - profit
        stop_loss = price + stop_adjust
        sideRev = 'Buy'

    oType = 'Market'
    oPrice = None

    if mode == 'volswitch':
        oType == 'Limit'
        oPrice = price + limits[side]
        r.set('monitor', 'off')

    try:
        print('MARKET ORDER ' + str(price) + ' sl:' + str(stop_adjust) + '/' + str(stop_loss))
    except Exception as e:
        print('MARKET ORDER EXCEPTION STRING ' + e)


    order = session.place_active_order(
    symbol = pair,
    side = side,
    order_type = oType,
    price = oPrice,
    stop_loss = stop_loss,
    take_profit = take_profit,
    qty = qty,
    time_in_force = "GoodTillCancel"
    )

    message = order['ret_msg']
    return_code = order['ret_code']  # 0  = 'good'

    try:
        data = json.dumps(order['result'])
        print('ORDER DATA', data)
    except Exception as e:
        print()


    return_price = order["result"]["price"]  # float

    print('ORDER MESSAGE ' + message + ' ' + str(return_price))

    if message == 'OK' and mode == 'deltaswitch':
        try:
            webhook = SyncWebhook.from_url(DISCORD_WEBHOOK)
            webhook.send("check")
        except Exception as e:
            print('DISCORD WEBHOOK EXCEPION ' + e)
            return True

        r.set('monitor', 'on')
        position = session.my_position(symbol="BTCUSD")['result']
        positionPrice = float(position['entry_price'])

        ## Get VWAP
        timeblocks = json.loads(r.get('timeblocks_BTC'))

        limitPrice = profit / 6
        vwap = round(positionPrice + (limitPrice*limits[side]))

        try:

            if timeblocks[-2]['vwap_task']:
                vwap = round(timeblocks[-2]['vwap_task'] + (15*limits[side]))
                message = 'vwap2 ' + str(vwap)
                sendMessage('BTC', message, '', 'red')
                print(message)

            if abs(positionPrice - vwap) > 200:
                vwap = round(positionPrice + (200*limits[side]))
                message = 'vwap3 ' + str(vwap)
                sendMessage('BTC', message, '', 'red')
                print(message)
            elif abs(positionPrice - vwap) < 60:
                vwap = round(positionPrice + (60*limits[side]))
                message = 'vwap4 ' + str(vwap)
                sendMessage('BTC', message, '', 'red')
                print(message)

            print('VWAP CALCULATION ' + str(vwap))

        except:
            print('VWAP TP EXCEPTION')

        try:
        ### place limit TP
            newLimit = session.place_active_order(
            symbol = pair,
            side = sideRev,
            order_type = 'Limit',
            price =  vwap,
            qty = round(qty*0.3),
            time_in_force = "GoodTillCancel"
            )
        except Exception as e:
            print('LIMIT ERROR', e)
        else:
            print('LIMIT SUCCESS')


    return True

def getSwitchMessage(SIDE, ACTIVE, THD, PD, BT, CTD, FC):
    switchMessage = 'nothing'

    if int(AUX_ACTIVE) == 1:
        return switchMessage

    try:
        switchMessage = SIDE + ' Active: ' + str(ACTIVE) + ' Threshold: ' + str(THD) + ' PDs: ' + json.dumps(PD) + ' totals: ' +  json.dumps(BT) + ' time: ' + str(CTD) + ' fc: ' + str(FC)
    except Exception as e:
        print('SWITCH MESSAGE ' + e)

    return switchMessage

def actionDELTA(blocks, newCandle, coin, coinDict, lastCandleisBlock):
    if int(AUX_ACTIVE) != 1:
        return False

    deltaControl = coinDict[coin]['deltaswitch']

    if deltaControl['Buy']['price'] == 0 and deltaControl['Sell']['price'] == 0:
        # print('delta zero')
        return 'ZO'

    if deltaControl['Sell']['price'] > 0 and blocks[-1]['high'] > deltaControl['Sell']['price'] and deltaControl['Sell']['swing'] == False:
        deltaControl['Sell']['swing'] = True
        deltaControl['Buy']['swing'] = False

        ## remove cuurent orders
        r.set('monitor', 'on')

        print('DELTA SELL SWING TRUE')

        r.set('coinDict', json.dumps(coinDict))
        return 'SW'

    if deltaControl['Buy']['price'] > 0 and blocks[-1]['low'] < deltaControl['Buy']['price'] and deltaControl['Buy']['swing'] == False:
        deltaControl['Buy']['swing'] = True
        deltaControl['Sell']['swing'] = False
        print('DELTA BUY SWING TRUE')
        r.set('coinDict', json.dumps(coinDict))
        return 'SW'

    side = None
    if deltaControl['Sell']['swing'] == True:
        side = 'Sell'
    elif deltaControl['Buy']['swing'] == True:
        side = 'Buy'
    else:
        return 'NO SIDE'



    fcCheck = deltaControl['fcCheck']

    currentTimeDelta = newCandle['time_delta']/1000

    count = 1

    activeRecent = False

    fastCandles = 0
    posDelta = 0
    negDelta = 0

    tds = []

    blockList = blocks[-(fcCheck):]
    ### if last candle is not block then don't count it
    if not lastCandleisBlock:
        blockList = blocks[-(fcCheck +1) : -1]


    for b in blockList:  ## examine candles leading up to current
        t = b['time_delta']/1000
        tds.append(t)
        if t < 5:
            fastCandles += 1
        if b['switch'] == 'ATC' or b['switch'] == 'ATT':
            activeRecent = True
        if b['delta']/b['total'] < -0.5:
            negDelta += 1
        if b['delta']/b['total'] > 0.5:
            posDelta += 1
        count += 1

    try:
        print('ACTION DELTA CHECK: ' + side + ' SWING:' + str(deltaControl[side]['swing']) + ' ACTIVE:' + str(deltaControl[side]['active']) + ' TD:' + str(currentTimeDelta) + ' FC:' + str(fastCandles) + ' LC:' + str(lastCandleisBlock) )
    except:
        print('ACTION MESSAGE FAIL')

    percentDelta0 = newCandle['delta']/newCandle['total']  #current block

    lc1 = -1
    lc2 = -2
    lc3 = -3

    ### if last candle is not block then don't count it
    if not lastCandleisBlock:
        lc1 = -2
        lc2 = -3
        lc3 = -4

    percentDelta1 = blocks[lc1]['delta']/blocks[lc1]['total']  #last block
    percentDelta2 = blocks[lc2]['delta']/blocks[lc2]['total']  #last blocks
    percentDelta3 = blocks[lc3]['delta']/blocks[lc3]['total']  #last blocks


    pds = [round(percentDelta0, 3), round(percentDelta1, 3), round(percentDelta2, 3), round(percentDelta3, 3) ]


    thresholdMarket = percentDelta0 >= 0.99 and percentDelta1 >= 0.99
    thresholdActivate = negDelta  >= 4


    if side == 'Sell':
        thresholdMarket = percentDelta0 <= -0.99 and percentDelta1 <= -0.99
        thresholdActivate = posDelta >= 4



    stallCondition_1candle =  newCandle['total'] > 500_000 and thresholdActivate
    stallCondition_2candle =  False #blocks[-1]['total'] + newCandle['total'] > 500_000 and thresholdActivate
    stallCondition = stallCondition_1candle or stallCondition_2candle
    blockTotals = [newCandle['total'], blocks[lc1]['total'], blocks[lc2]['total']]



    if currentTimeDelta > 5 and thresholdActivate and fastCandles == fcCheck and deltaControl[side]['active'] == False:
        ## delta action has stalled: lookout is active
        deltaControl[side]['active'] = True
        r.set('coinDict', json.dumps(coinDict))
        msg = getSwitchMessage(side, deltaControl[side]['active'], thresholdMarket, pds, blockTotals, currentTimeDelta, fastCandles)
        print('DELTA STALL CONDITION ATT: ' + msg)
        return 'ATT'

    elif stallCondition and fastCandles == fcCheck and deltaControl[side]['active'] == False:
        ## delta action has stalled: lookout is active
        deltaControl[side]['active'] = True
        r.set('coinDict', json.dumps(coinDict))
        msg = getSwitchMessage(side, deltaControl[side]['active'], thresholdMarket, pds, blockTotals, currentTimeDelta, fastCandles)
        print('DELTA STALL CONDITION ATC: ' + msg)
        return 'ATC'

    elif deltaControl[side]['active'] and thresholdMarket:
        print('PLACE DELTA')
        if LOCAL:
            return 'MO'

        MO = marketOrder(side, deltaControl[side]['fraction'], deltaControl[side]['stop'], deltaControl[side]['profit'], 'deltaswitch')

        if MO:
            resetCoinDict(coinDict, side, 'deltaswitch')
            msg = getSwitchMessage(side, deltaControl[side]['active'], thresholdMarket, pds, blockTotals, currentTimeDelta, fastCandles)
            print('DELTA ORDER MESSAGE ' + msg)
            return 'MO'
        else:
            return 'MF'

    elif fastCandles == fcCheck and not activeRecent:

        deltaControl[side]['active'] = False
        msg = getSwitchMessage(side, deltaControl[side]['active'], thresholdMarket, pds, blockTotals, currentTimeDelta, fastCandles)

        print('DELTA FAST RESET: ' + msg)
        r.set('coinDict', json.dumps(coinDict))
        return 'AF'


    msg = getSwitchMessage(side, deltaControl[side]['active'], thresholdMarket, pds, blockTotals, currentTimeDelta, fastCandles)

    return msg


def resetCoinDict(coinDict, side, mode):

    coinDict['BTC'][mode][side]['swing'] = False
    coinDict['BTC'][mode][side]['price'] = 0

    if coinDict['BTC'][mode][side]['backup'] and coinDict['BTC'][mode][side]['backup'] > 0:
        coinDict['BTC'][mode][side]['price'] = int(coinDict['BTC'][mode][side]['backup'])
        coinDict['BTC'][mode][side]['backup'] = 0

    if mode == 'deltaswitch':
        coinDict['BTC'][mode][side]['active'] = False



    r.set('coinDict', json.dumps(coinDict))
    r.set('discord_' + 'BTC', 'coinDict Reset: ' + side + ' ' + mode)











