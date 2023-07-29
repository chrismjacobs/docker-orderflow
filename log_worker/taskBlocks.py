import datetime as dt
import json
from datetime import datetime
from settings import r, LOCAL
from taskAux import sendMessage, actionVOLUME
from math import trunc

## addBlock
## getHiLo
## getHistory
## getImbalances
## get vWAP
## getPVA

def addBlock(units, blocks, mode, coin):

    TIME = False
    VOLUME = False
    BLOCK = False

    coinDict = json.loads(r.get('coinDict'))

    pause = coinDict[coin]['pause']
    getTickImbs = coinDict[coin]['imbalances']

    modeSplit = mode.split('_')
    mode = modeSplit[0]

    if 'time' in mode:
        TIME = True
    elif 'vol' in mode:
        VOLUME = True

    if 'block' in mode:
        BLOCK = True


    CVDdivergence = {}

    if TIME and BLOCK and pause == False:
        CVDdivergence = getHiLow(blocks, coin)
        stream = json.loads(r.get('stream_' + coin))
        stream['Divs'] = CVDdivergence
        r.set('stream_' + coin, json.dumps(stream) )


    ''' BLOCK DATA '''

    # print('BLOCK DATA: ' + mode + ' -- ' + coin)
    previousOICum = units[0]['streamOI']
    previousTime = units[0]['trade_time_ms']
    vwap_task = 0
    newOpen = units[0]['streamPrice']
    price = units[-1]['streamPrice']
    previousDeltaCum = 0

    ## if just one block than that is the current candle
    ## last block is the previous one
    ## but if its the start of the day then we need to get Historical last block

    if len(blocks) > 1:
        if mode == 'carry':
            lastCandle = blocks[-1] # when carrying a volume block there is no current candle
        else:
            lastCandle = blocks[-2] # ignore last unit which is the current one
        previousDeltaCum = lastCandle['delta_cumulative']
        vwap_task = lastCandle['vwap_task']
        previousOICum = lastCandle['oi_cumulative']
        previousTime = lastCandle['trade_time_ms']
        newOpen = lastCandle['close']
    elif TIME:
        h = getHistory(coin)
        if h:
            lastCandle = h['timeblocks_' + coin][-1]
            previousDeltaCum = lastCandle['delta_cumulative']
            previousOICum = lastCandle['oi_cumulative']
            if lastCandle['vwap_task']:
                vwap_task = lastCandle['vwap_task']


    newStart  = units[0]['trade_time_ms']
    newClose = units[-1]['trade_time_ms']

    # if LOCAL:
    #     print('TIME CHECK', previousTime, newClose, newStart, type(newClose), type(newStart))

    timeDelta = newClose - newStart
    timeDelta2 = newClose - previousTime

    buyCount = 0
    sellCount = 0
    highPrice = 0
    lowPrice = 0

    OIclose = 0
    OIhigh = 0
    OIlow = 0

    tradecount = 0

    tickDict = {}

    oiList = []

    priceList = []

    tickCoins = ['BTC']


    for d in units:
        # print('BLOCK LOOP', d)

        if d['side'] == 'Buy':
            buyCount += d['size']
        else:
            sellCount += d['size']

        for price in d['spread']:

            oiList.append(d['streamOI'])
            OIclose = d['streamOI']

            price = float(price)
            priceList.append(price)

            # print('CHECK SPREAD TICKS', price, type(price) )

            if coin in tickCoins:
                # print('TICKES', tickDict, tickPrice)
                if coin == 'BTC':
                    tickPrice = str(trunc(price/10)*10)

                elif coin == 'ETH':
                    ##  1159.56 --> 1159.25
                    tickPrice = math.floor(price)


                if tickPrice not in tickDict:

                    tickDict[tickPrice] = {
                        'tickPrice' : tickPrice,
                        'Sell'  : 0,
                        'Buy' : 0,
                        'SellPer' : 0,
                        'BuyPer' : 0
                    }

                tickDict[tickPrice][d['side']] += d['spread'][str(price)]
                ## the spread keys come back as strings

    highPrice = max(priceList)
    lowPrice = min(priceList)
    total = buyCount + sellCount

    oiList.sort()

    OIlow = oiList[0]
    OIhigh = oiList[-1]

    delta = buyCount - sellCount
    OIdelta =  OIclose - previousOICum

    priceDelta = price - newOpen

    if coin == 'ETH':
        priceDelta = round(priceDelta*100)/100
    if coin == 'GALA':
        priceDelta = round(priceDelta*10000)/10000

    tickList = []

    if coin in tickCoins:
        #print('TICKS SORT', mode, size)

        tickKeys = list(tickDict.keys())
        tickKeys.sort(reverse = True)

        # print('SORT DATA ' + str(priceList))

        for p in tickKeys:
            tickList.append(tickDict[p])

        stack = r.get('stack')
        if not stack:
            stack = 'off'
            r.set('stack', stack)

        if stack and total > 2_000_000 and OIdelta > 0:
            getIMBs = getImbalances(tickList, mode)
            tickList = getIMBs[0]
            stackBuys = getIMBs[1]
            stackSells = getIMBs[2]

            if stackBuys >= 3 and 'time' in mode:
                sendMessage(coin, 'Stack IMBS BUY', '', 'white')
            if stackSells >= 3 and 'time' in mode:
                sendMessage(coin, 'Stack IMBS SELL', '', 'white')


    if BLOCK:
        try:
            vwap_task = getVWAP(blocks, coin)
        except:
            print('vwap exception')


    newCandle = {
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
        'delta_cumulative' : int(previousDeltaCum + delta),
        'total' : total,
        'vwap_task' : vwap_task,
        'oi_delta': OIdelta,
        'oi_high': OIhigh,
        'oi_low': OIlow,
        'oi_open': previousOICum,
        'oi_range': OIhigh - OIlow,
        'oi_cumulative': OIclose,
        'divergence' : CVDdivergence,
        'tickList' : tickList,
        'pva_status': {},
        'volDiv' : False,
        'switch' : False
        #'tradecount': tradecount,
    }

    # if 'block' in mode:
    #     print('NEW CANDLE: ' + mode + ' ' + coin)

    bullDiv = False
    bearDiv = False

    volblockcandle = mode == 'volblock' or mode == 'carry'

    if coin == 'BTC' and volblockcandle:

        # print('VOL DIV CHECK')

        deltaPercent = round( (  newCandle['delta']  /  newCandle['total']  ) * 100  )

        if abs(deltaPercent) > 20:
            # print('VOL DIV CHECK 2')
            timeSecs = round(newCandle['time_delta']/1000)
            oiCheck = round(newCandle['oi_delta']/1000)
            tots = round(newCandle['total']/1_000_000)

            if newCandle['delta'] < 0 and newCandle['price_delta'] > 0 and newCandle['time_delta'] > 30000:
                newCandle['volDiv'] = True
                bullDiv = True
                msg = coin + ' BULL VOL ' + str(tots) + ' Delta ' + str(deltaPercent) + '% ' + str(newCandle['price_delta']) + '$ ' + str(timeSecs) + ' secs  OI: ' + str(oiCheck)
                if newCandle['total'] > 2_500_000:
                    sendMessage(coin, msg, '', 'green')

            # print('VOL DIV CHECK 3')
            if newCandle['delta'] > 0 and newCandle['price_delta'] < 0 and newCandle['time_delta'] > 30000:
                newCandle['volDiv'] = True
                bearDiv = True
                msg = coin + ' BEAR VOL ' + str(tots) + ' Delta ' + str(deltaPercent) + '% ' + str(newCandle['price_delta']) + '$ ' + str(timeSecs) + ' secs  OI: ' + str(oiCheck)
                if newCandle['total'] > 2_500_000:
                    sendMessage(coin, msg, '', 'red')

            # print('VOL DIV CHECK COMPLETE')

        try:
            newCandle['switch'] = actionVOLUME(blocks, coin, coinDict, bullDiv, bearDiv)
        except:
            print('ACTION VOLUME EXCEPTION')

    if TIME:
        if newCandle['total'] > 50_000_000 and pause == False:
            if coinDict['ETH']:
                coinDict['ETH']['active'] = False
            coinDict['BTC']['pause'] = True
            r.set('coinDict', json.dumps(coinDict))
        elif pause == True and newCandle['total'] < 50_000_000:
            coinDict['BTC']['pause'] = False
            r.set('coinDict', json.dumps(coinDict))

    return newCandle

def getHiLow(timeblocks, coin):

    tbRev = timeblocks[::-1] ## creates a new list  .reverse() change the original list

    ## last block is not completed but does have current HLOC

    LH2h = tbRev[0]['high']
    LL2h = tbRev[0]['low']
    LH2h_index = 0
    LL2h_index = 0
    LH2h_cvd = tbRev[0]['delta_cumulative']
    LL2h_cvd = tbRev[0]['delta_cumulative']


    '''Set locals for the last 2 Hours'''
    count = 0

    for block in tbRev:
        if count <= 23: ### looks at past two hours
            if block['high'] > LH2h:
                LH2h = block['high']
                LH2h_index = count
                LH2h_cvd = block['delta_cumulative']
            if block['low'] < LL2h:
                LL2h = block['low']
                LL2h_index = count
                LL2h_cvd = block['delta_cumulative']
        count += 1

    ''' check if previous candle has an exceeeding cvd'''
    try:
        if tbRev[LH2h_index + 1]['delta_cumulative'] > LH2h_cvd:
            LH2h_cvd = tbRev[LH2h_index + 1]['delta_cumulative']

        if tbRev[LL2h_index + 1]['delta_cumulative'] < LL2h_cvd:
            LL2h_cvd = tbRev[LL2h_index + 1]['delta_cumulative']
    except:
        print('LOCAL CVD CHECK FAIL')

    '''Look for areas where the CVD has already exceeded '''
    recount = 0

    for block in tbRev:
        if recount <= 23 and recount > 1: # discount the first two blocks
            if block['delta_cumulative'] > LH2h_cvd:
                LH2h_cvd = block['delta_cumulative']
            if block['delta_cumulative'] < LL2h_cvd:
                LL2h_cvd = block['delta_cumulative']

        recount += 1

    oih = 0
    oil = 0

    try:
        oih = tbRev[0]['oi_cumulative'] - tbRev[LH2h_index]['oi_cumulative']
        oih = tbRev[0]['oi_cumulative'] - tbRev[LL2h_index]['oi_cumulative']
    except:
        print('OI count FAIL')


    highInfo = {
        'price' : LH2h,
        'index' : LH2h_index,
        'delta' : LH2h_cvd,
        'oi' : oih,
        'div' : False
    }

    lowInfo = {
        'price' : LL2h,
        'index' : LL2h_index,
        'delta' : LL2h_cvd,
        'oi' : oil,
        'div' : False
    }

    if LH2h_index >= 2:
        # current timeblock nor the previous is not the highest/lowest
        if tbRev[0]['delta_cumulative'] > LH2h_cvd:
            # Divergence Triggered
            highInfo['div'] = True

            streamAlert('CVD Bear div: ' + json.dumps(highInfo), 'CVD Divergence', coin)
            if coin == 'BTC':
                r.set('discord_' + coin, coin + ' CVD BEAR div')  #: '  + json.dumps(highInfo))

    if LL2h_index >= 2:
        if tbRev[0]['delta_cumulative'] < LL2h_cvd:
            # Divergence Triggered
            lowInfo['div'] = True
            streamAlert('CVD Bull div: ' + json.dumps(lowInfo), 'CVD Divergence', coin)

            if coin == 'BTC':
                r.set('discord_' + coin, coin + ' CVD BULL div') # : ' + json.dumps(lowInfo))


    return {'highInfo' : highInfo , 'lowInfo' : lowInfo }

def getHistory(coin):
    # print('GET HISTORY ' + coin)

    historyBlocks = json.loads(r.get('history_' + coin))
    ## -->  each day
    ## a list of dictionaries

    if historyBlocks and len(historyBlocks) > 0:
        return historyBlocks[-1]
    else:
        return False

def getImbalances(tickList, mode):
    if LOCAL:
        print('IMBALANCES')

    ticks = len(tickList)
    # 1 2 3

    ## Buys cannot be last
    ## Sells cannot be at the top

    for i in range(ticks):  # 0 1 2
        if i + 1 < ticks:
            BIbuys = tickList[i]['Buy']
            BIsells = tickList[i + 1]['Sell']

            if BIsells == 0:
                BIsells = 1

            BIpct = round((BIbuys / BIsells) * 100)
            if BIpct > 1000:
                BIpct = 1000

            tickList[i]['BuyPer'] = BIpct

            SIbuys = tickList[i]['Buy']
            SIsells = tickList[i + 1]['Sell']

            if SIbuys == 0:
                SIbuys = 1

            SIpct = round((SIsells / SIbuys) * 100)
            if SIpct > 1000:
                SIpct = 1000

            tickList[i + 1]['SellPer'] = SIpct

    stackBuys = 0
    stackSells = 0

    if 'block' in mode:

        for t in tickList:
            if t['SellPer'] > 369:
                stackSells += 1
            if t['SellPer'] < 369 and stackSells <= 2:
                stackSells = 0
            if t['BuyPer'] > 369:
                stackBuys += 1
            if t['BuyPer'] < 369 and stackBuys <= 2:
                stackBuys = 0


    return [tickList, stackBuys, stackSells]

def getVWAP(timeblocks, coin):

    volumeCum = 0
    vwapVolumeCum = 0

    for t in timeblocks:

        volumeCum += t['total']
        t['pivot'] = (t['high'] + t['low'] + t['close'])/3
        vwapVolume = t['pivot']*t['total']
        vwapVolumeCum += vwapVolume
        vwapPrice = vwapVolumeCum/volumeCum
        t['vwap'] = vwapPrice
        # if coin == 'BTC':
        #     t['vwap_task'] = str(trunc(vwapPrice/10)*10)
        # elif coin == 'ETH':
        #     t['vwap_task']  = math.floor(vwapPrice)

    return round(timeblocks[-1]['vwap'])

def getPVAstatus(timeblocks, coin):
    if LOCAL:
        print('GET PVA')
    last11blocks = []
    if len(timeblocks) < 11:
        history = json.loads(r.get('history_' + coin))
        try:
            if len(history) > 0:
                lastHistory = history[-1]['timeblocks_' + coin]
                howManyOldTimeblocks = (11-len(timeblocks))
                last11blocks = lastHistory[-howManyOldTimeblocks:] + timeblocks
                # print('LASTBLOCKS HISTORY', last11blocks)
                ## if one time block - get last 10 from history
                ## if 4 time blocks - get last 7 from history
            else:
                return {}
        except:
            # r.set('discord_' + coin, 'History PVA error')
            print('PVA HISTORY ERROR')
            return {}
    else:
        if len(timeblocks) >= 11:
            try:
                last11blocks = timeblocks[-11:]
            except:
                return {}

        else:
            return {}

    # print('PVA Calculate')

    sumVolume = 1
    lastVolume = 1
    lastDelta = 0
    lastPriceDelta = 0
    lastOIDelta = 0
    lastOIRange = 0

    try:
        count = 1
        for x in last11blocks:
            if count < 11:
                sumVolume += x['total']
                count += 1
            else:
                lastVolume = x['total']
                lastDelta = x['delta']
                lastPriceDelta = x['price_delta']
                lastOIDelta = x['oi_delta']
                lastOIRange = round((x['oi_high'] - x['oi_low'])/100_000)/10

        pva150 = False
        pva200 = False
        divergenceBull = False
        divergenceBear = False
        flatOI = False

        percentage = round((lastVolume/(sumVolume/10)), 2)
        deltapercentage = round((lastDelta/lastVolume)*100, 2)

        if percentage > 2:
            pva200 = True
            if lastOIDelta < 100000  and lastOIDelta > - 100000:
                flatOI = True
        elif percentage > 1.5:
            pva150 = True

        if lastDelta > 0 and lastPriceDelta < 0:
            divergenceBear = True
        elif lastDelta < 0 and lastPriceDelta > 0:
            divergenceBull = True

        returnPVA = {
            'pva150' : pva150,
            'pva200' : pva200,
            'vol': lastVolume,
            'percentage' : percentage,
            'deltapercentage' : deltapercentage,
            'PVAbearDIV' : divergenceBear,
            'PVAbullDIV' : divergenceBull,
            'rangeOI' : lastOIRange,
            'flatOI' : flatOI
            }

        if LOCAL:
            print('RETURN PVA')

        volString = str(round(returnPVA['vol']/100_000)/10)

        if pva200 and flatOI and lastVolume > 10_000_000:
            msg = coin + ' PVA flatOI  Vol:' + volString  + ' ' + str(returnPVA['percentage']*100) + '%   OI Range: ' + str(returnPVA['rangeOI']) + 'm'
            sendMessage(coin, msg, '', 'yellow')
            streamAlert('PVA candle with flat OI', 'PVA', coin)
        elif pva200 and divergenceBear and lastVolume > 4_000_000:
            msg = coin + ' PVA divergence Bear: ' + volString  + ' ' + str(returnPVA['percentage'])
            sendMessage(coin, msg, '', 'red')
        elif pva200 and divergenceBull and lastVolume > 4_000_000:
            msg = coin + ' PVA divergence Bull: ' +  volString  + ' ' + str(returnPVA['percentage'])
            sendMessage(coin, msg, '', 'cyan')

        return returnPVA

    except:
        print('PVA ERROR')
        return {}


def streamAlert(message, mode, coin):
    # print('Alert Stream ' + mode + ' ' + coin)
    stream = json.loads(r.get('stream_' + coin))

    current_time = dt.datetime.utcnow()
    # print('Current Time UTC Alert : ' + str(current_time).split('.')[0])

    alertList = stream['alerts']
    alertMessage = [str(current_time), mode, message]

    alertList.insert(0, alertMessage)

    if len(alertList) > 5:
        alertList.pop()

    r.set('stream_' + coin, json.dumps(stream) )


    ''' alerts notes '''
    # sudden OI change - looks at current candle or infact previous candle if time just passed -
    # perhaps calculate the likely reason