import os
import json
import discord
from discord.ext import tasks, commands
from discord import SyncWebhook
from datetime import datetime
from settings import r, session, AUX_ACTIVE, DISCORD_CHANNEL, DISCORD_TOKEN, DISCORD_USER, DISCORD_WEBHOOK


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

def startDiscord():
    if int(AUX_ACTIVE) != 1:
        return False

    ## intents controls what the bot can do; in this case read message content
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    bot = commands.Bot(command_prefix="!", intents=discord.Intents().all())

    @bot.event
    async def on_ready():
        print(f'{bot.user} is now running!')
        user = bot.get_user(int(DISCORD_USER))
        print('DISCORD_GET USER', DISCORD_USER, 'user=', user)
        setCoinDict()
        await user.send('Running')
        checkRedis.start(user)

    @tasks.loop(seconds=3)
    async def checkRedis(user):
        #print('DISCORD REDIS CHECK')

        if not r.get('channelDict'):
            r.set('channelDict', DISCORD_CHANNEL)

        channelDict = json.loads(r.get('channelDict'))

        if not r.get('monitor'):
            r.set('monitor', 'on')

        if r.get('monitor') == 'on':
            try:
                monitorLimits()
            except Exception as e:
                print('MONITOR ERROR', e)
                channel = bot.get_channel(int(channelDict['BTC']))
                await channel.send('MONITOR ERROR: ' + e)

        for coin in channelDict:
            ## need incase redis gets wiped
            if not r.get('discord_' + coin):
                r.set('discord_' + coin, 'discord set')
            if not r.get('discord_' + coin + '_holder'):
                r.set('discord_' + coin + '_holder', 'discord set')

            channel = bot.get_channel(int(channelDict[coin]))

            # print(channel, int(channelDict[coin]))
            msg = r.get('discord_' + coin)
            msg_h = r.get('discord_' + coin + '_holder')

            if msg != 'blank':
                await channel.send(msg)
                r.set('discord_' + coin, 'blank')
            elif msg_h != 'blank':
                await channel.send(msg_h)
                r.set('discord_' + coin + '_holder', 'blank')


    @bot.event
    async def on_message(msg):
        user = bot.get_user(int(DISCORD_USER))
        # print('MESSAGE DDDDDDDDD', msg.content)
        replyText = 'ho'

        deltaSet = {
            'db' : ['deltaswitch', 'Buy'],
            'ds' : ['deltaswitch', 'Sell'],
            'vb' : ['volswitch', 'Buy'],
            'vs' : ['volswitch', 'Sell']
        }

        if len(msg.content) > 20:
            ## ignore long messages
            return False

        print(msg.content)

        if msg.content == 'B':
            lastCandle = json.loads(r.get('timeblocks_BTC'))[-2]
            print(lastCandle)
            oi = round(lastCandle['oi_delta']/1000)
            b = round(lastCandle['buys']/1000)
            s = round(lastCandle['sells']/1000)
            replyText = str(lastCandle['total']) + ' OI: ' + str(oi) + 'k Buys: ' + str(b) + 'k Sells: ' + str(s) + 'k'
        elif 'check' in msg.content:
            checkRedis.start(user)
            replyText = 'check'
        elif 'try' in msg.content:
            try:
                webhook = SyncWebhook.from_url(DISCORD_WEBHOOK)
                webhook.send("check")
            except Exception as e:
                print('DISCORD WEBHOOK EXCEPION ' + e)

        elif 'elta purge' in msg.content:
            coin = 'BTC'
            dFlow = 'deltaflow_' + coin
            dBlocks = 'deltablocks_' + coin
            replyText = 'delta purge action'
            r.set(dFlow, json.dumps([]))
            r.set(dBlocks, json.dumps([]))
        elif 'olume purge' in msg.content:
            coin = 'BTC'
            vFlow = 'volumeflow_' + coin
            vBlocks = 'volumeblocks_' + coin
            replyText = 'volume purge action'
            r.set(vFlow, json.dumps([]))
            r.set(vBlocks, json.dumps([]))


        elif 'nsi' in msg.content and r.get('ansi') == 'on':
            r.set('ansi', 'off')
            replyText = 'Ansi ' + r.get('ansi')
        elif 'nsi' in msg.content and r.get('ansi') == 'off':
            r.set('ansi', 'on')
            replyText = 'Ansi ' + r.get('ansi')

        elif 'tack' in msg.content and r.get('stack') == 'on':
            r.set('stack', 'off')
            replyText = 'Stacks ' + r.get('stack')
        elif 'tack' in msg.content and r.get('stack') == 'off':
            r.set('stack', 'on')
            replyText = 'Stacks ' + r.get('stack')

        elif 'onitor off' in msg.content:
            r.set('monitor', 'off')
            replyText = 'Set Monitor ' + r.get('monitor')
        elif 'onitor on' in msg.content:
            r.set('monitor', 'on')
            replyText = 'Set Monitor ' + r.get('monitor')
        elif 'onitor check' in msg.content:
            replyText = 'Monitor is set to' + r.get('monitor')


        elif msg.content == 'Dict' or msg.content == 'dict':
            setCoinDict()
            replyText = 'Coin Dict Set'

        elif msg.content.split(' ')[0] in deltaSet:
            latestprice = float(session.latest_information_for_symbol(symbol='BTCUSD')['result'][0]['last_price'])
            coinDict = json.loads(r.get('coinDict'))
            code = msg.content.split(' ')[0]

            if len(msg.content.split(' ')) == 1:
                ## just checking order
                switch = deltaSet[code][0]
                side = deltaSet[code][1]
                price = coinDict['BTC'][switch][side]['price']
                replyText = 'Check: ' + side + ' ' + str(price) + ' ' + str(coinDict['BTC'][switch][side]['fraction']) + ' ' + str(coinDict['BTC'][switch][side]['stop'])
            else:
                ## new order being set
                price = int(msg.content.split(' ')[1])

            if price == 0:
                ### reset order
                coinDict['BTC'][switch][side]['price'] = 0
                coinDict['BTC'][switch][side]['swing'] = False
                coinDict['BTC'][switch][side]['active'] = False
                r.set('coinDict', json.dumps(coinDict))
                replyText = 'Resest: ' + side + ' ' + str(price) + ' ' + str(coinDict['BTC'][switch][side]['active']) + ' ' + str(coinDict['BTC'][switch][side]['switch'])

            elif price > 100_000:
                replyText = 'Price out of range'
            elif price < 10_000 and price != 0:
                replyText = 'Price out of range'
            elif 's' in code and price < latestprice and price != 0:
                replyText = 'Price too low'
            elif 'b' in code and price > latestprice and price != 0:
                replyText = 'Price too high'
            else:
                try:
                    switch = deltaSet[code][0]
                    side = deltaSet[code][1]
                    coinDict['BTC'][switch][side]['price'] = price
                    if len(msg.content.split(' ')) > 3:
                        ## db 30000 0.5 100
                        fraction = msg.content.split(' ')[2]
                        stop = msg.content.split(' ')[3]
                        coinDict['BTC'][switch][side]['fraction'] = float(fraction)
                        coinDict['BTC'][switch][side]['stop'] = int(stop)
                    elif len(msg.content.split(' ')) > 2:
                        tag = msg.content.split(' ')[2]
                        if '.' in tag:
                            coinDict['BTC'][switch][side]['fraction'] = float(tag)
                        else:
                            coinDict['BTC'][switch][side]['stop'] = int(tag)

                    r.set('coinDict', json.dumps(coinDict))
                    replyText = 'Set: ' + side + ' ' + str(price) + ' ' + str(coinDict['BTC'][switch][side]['fraction']) + ' ' + str(coinDict['BTC'][switch][side]['stop'])
                except Exception as e:
                    print('DELTA SET ERROR', e)
                    replyText = 'DELTA SET ERROR'
        elif 'rade' in msg.content:
            replyText = tradeManagement(msg.content.split('rade ')[1])

        else:
            return False

        if msg.author == user:
            await user.send(replyText)
            # ping('rekt-app.onrender.com', verbose=True)


    bot.run(DISCORD_TOKEN)


def monitorLimits():
    pair = "BTCUSD"

    position = session.my_position(symbol=pair)['result']

    positionSize = int(position['size'])

    if positionSize == 0:
        ### Trade exited so delete left limit order
        recentOrders = session.get_active_order(symbol=pair)['result']['data']
        orderID = 0
        for ro in recentOrders:
            if ro['order_status'] == 'New':
                orderID = ro['order_id']
                result = session.cancel_all_active_orders(symbol="BTCUSD")['ret_msg']
                print('CANCEL', result)
                break

def placeOrder(side, price, stop_loss, qty, take_profit):

    order = session.place_active_order(
    symbol="BTCUSD",
    side=side,
    order_type='Limit',
    price=price,
    stop_loss = stop_loss,
    take_profit = take_profit,
    qty=qty,
    time_in_force="GoodTillCancel"
    )


    message = order['ret_msg']
    data = json.dumps(order['result'])

    print('ORDER', order)
    print('MESSAGE', message)
    print('DATA', data)

    return data


def tradeManagement(msg):

    info = msg.split(' ')

    mode = info[0]


    pair = 'BTCUSD'

    print('MANAGE MODE:', mode)


    BTCprice = float(session.latest_information_for_symbol(symbol="BTCUSD")['result'][0]['last_price'])

    position = session.my_position(symbol=pair)['result']

    positionSide = position['side']
    positionSize = int(position['size'])
    positionEntry = round(float(position['entry_price']))
    positionStop = round(float(position['stop_loss']))

    if mode == 'codes':
        return 'cancel  / size  / breakeven  / limitexit (fraction)  / fullexit / vwapget / vwapset (fraction)  '
    if mode == 'cancel':
        result = session.cancel_all_active_orders(symbol=pair)['ret_msg']
        print('cancel', result)
        return result
    elif mode == 'size':
        return str(positionSize)
    elif mode == 'breakeven':
        BEprices = {
            'Buy' : positionEntry - 10,
            'Sell' : positionEntry + 10
        }
        responseDict = session.set_trading_stop(symbol=pair, stop_loss=BEprices[positionSide])
        print(responseDict)
        try:
            return str(responseDict['result']['stop_loss'])
        except:
            return 'error'

    elif mode == 'limitexit':
        r.set('monitor', 'on')

        limitexit = float(info[1])

        if limitexit < 0.1 or limitexit > 1:
            response = 'error ' + str(limitexit)

        try:
            ### place limit TP
            session.cancel_all_active_orders(symbol=pair)['ret_msg']

            LMprices = {
                'Buy' : BTCprice + 0.5,
                'Sell' : BTCprice -0.5
            }
            sideRev = {
                'Buy' : 'Sell',
                'Sell' : 'Buy'
            }

            placeOrder(sideRev[positionSide], LMprices[positionSide], 0, positionSize*limitexit, 0)

        except Exception as e:
            print('LIMIT ERROR', e)
            response = 'limit error'
        else:
            print('LIMIT SUCCESS')

        return response

    elif mode == 'fullexit':

        ### set stop loss

        BEprices = {
            'Buy' : BTCprice - 10,
            'Sell' : BTCprice + 10
        }
        try:
            responseDict = session.set_trading_stop(symbol=pair, stop_loss=BEprices[positionSide])
            print(responseDict)
        except Exception as e:
            print('STOP LOSS ERROR', e)

        ## set limit out
        r.set('monitor', 'on')
        session.cancel_all_active_orders(symbol=pair)['ret_msg']
        response = 'success'
        try:
            ### place limit TP
            LMprices = {
                'Buy' : BTCprice + 0.5,
                'Sell' : BTCprice - 0.5
            }
            sideRev = {
                'Buy' : 'Sell',
                'Sell' : 'Buy'
            }

            placeOrder(sideRev[positionSide], LMprices[positionSide], 0, positionSize, 0)


        except Exception as e:
            print('LIMIT ERROR', e)
            response = 'full exit error'
        else:
            print('LIMIT SUCCESS')

        return response

    # elif mode == 'limitset':
    #     r.set('monitor', 'on')
    #     response = 'limitset'

    #     LMprices = {
    #             'Buy' : positionEntry + limitprice,
    #             'Sell' : BTCprice - limitprice
    #         }

    #     sideRev = {
    #         'Buy' : 'Sell',
    #         'Sell' : 'Buy'
    #     }

    #     if limitprice > 1000:
    #         LMprices = {
    #             'Buy' : limitprice,
    #             'Sell' : limitprice
    #         }

    #     try:
    #         placeOrder(sideRev[positionSide], LMprices[positionSide], 0, positionSize*limitfraction, 0)
    #     except Exception as e:
    #         print('LIMIT ERROR', e)
    #         response = 'limitset error'
    #     else:
    #         print('LIMIT SUCCESS')

    #     return jsonify({'result' : response, 'mode' : mode})


    elif mode == 'vwapget' or mode == 'vwapset':
        ##r.set('monitor', 'on')
        response = 'vwapprice'

        if mode == 'vwapset':
            vwapfraction = float(info[1])
            if vwapfraction < 0.1 or vwapfraction > 1:
                response = 'error ' + str(vwapfraction)

        timeblocks = json.loads(r.get('timeblocks_BTC'))
        vwap = timeblocks[-2]['vwap_task']

        VSprices = {
                'Buy' : round(float(vwap)) - 20,
                'Sell' : round(float(vwap)) + 20
            }
        sideRev = {
            'Buy' : 'Sell',
            'Sell' : 'Buy'
        }

        if mode == 'vwapset':
            r.set('monitor', 'on')
            try:
                session.cancel_all_active_orders(symbol=pair)['ret_msg']
                response = placeOrder(sideRev[positionSide], VSprices[positionSide], 0, positionSize*vwapfraction, 0)
            except Exception as e:
                print('VWAP ERROR', e)
                response = 'vwapset error'
            else:
                print('VWAP SUCCESS')
        else:
            response = str(vwap)

        return response



def setCoinDict():
    deltaDict = {
                'fcCheck': 7,
                'block' : 100_000,
                'Sell' : {
                    'price' : 0,
                    'swing' : False,
                    'active' : False,
                    'fraction' : 0.6,
                    'stop' : 100,
                    'profit' : 300,
                    'backup' : 0
                },
                'Buy' : {
                    'price' : 0,
                    'swing' : False,
                    'active' : False,
                    'fraction' : 0.6,
                    'stop' : 100,
                    'profit' : 300,
                    'backup' : 0
                }
            }

    volDict = {
                    'Sell' : {
                        'price' : 0,
                        'swing' : False,
                        'fraction' : 0.6,
                        'stop' : 100,
                        'profit' : 300,
                        'backup' : 0
                    },
                    'Buy' : {
                        'price' : 0,
                        'swing' : False,
                        'fraction' : 0.6,
                        'stop' : 100,
                        'profit' : 300,
                        'backup' : 0
                    }
                }

    coinDict = {
            'BTC' : {
                'oicheck' : [1_500_000, 2_000_000],
                'volume' : [True, 3],
                'active' : True,
                'imbalances' : False,
                'pause' : False,
                'purge' : False,
                'deltaswitch' : deltaDict,
                'volswitch' : volDict
            }
            # 'ETH' : {
            #     'oicheck' : [800_000, 800_000],
            #     'volume' : [True, 1],
            #     'active' : False,
            #     'imbalances' : False,
            #     'pause' : False,
            #     'purge' : False,
            # },
    }

    r.set('coinDict', json.dumps(coinDict))
