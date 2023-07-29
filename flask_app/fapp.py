from flask import Flask, flash, render_template, redirect, request, jsonify, url_for, make_response
from time import sleep
import json
import requests
from analysis import getBlocks, getVWAP, getImbalances
from settings import SECRET_KEY, DEBUG, r, auth_required
import datetime as dt

import logging
wlog = logging.getLogger('werkzeug')
wlog.setLevel(logging.ERROR)

app = Flask(__name__)
app.config['DEBUG'] = DEBUG
app.config['SECRET_KEY'] = SECRET_KEY

# logging.debug("A debug message")
# logging.info("An info message")
# logging.warning("A warning message")
# logging.error("An error message")
# logging.critical("A critical message")
## logging level set to warning and above logging.basicConfig(level=logging.INFO)

@app.route('/')
@auth_required
def home():

    return render_template('orderflow.html')

@app.route('/setPrices', methods=['POST'])
def setPrices():

    coinDict = json.loads(request.form['coinOBJ'])
    reset = request.form['reset']


    print(reset, coinDict, type(coinDict))

    if reset == 'true':
        coinDict['BTC']['deltaswitch']['Sell']['active'] = False
        coinDict['BTC']['deltaswitch']['Sell']['swing'] = False
        coinDict['BTC']['deltaswitch']['Sell']['price'] = 0

        coinDict['BTC']['deltaswitch']['Buy']['active'] = False
        coinDict['BTC']['deltaswitch']['Buy']['swing'] = False
        coinDict['BTC']['deltaswitch']['Buy']['price'] = 0

        r.set('coinDict', json.dumps(coinDict))
        r.set('discord_' + 'BTC', 'coinDict Reset')
    else:
        r.set('coinDict', json.dumps(coinDict))

    return jsonify({'coinDict' : coinDict})


@app.route('/getOF', methods=['POST'])
def getOF():
    timeBlockSize = int(request.form ['timeBlockSize'])
    coin = request.form ['coin']

    # print('BLOCK SIZES', coin, volumeBlockSize, timeBlockSize)

    coinDict = r.get('coinDict')
    coinInfo = json.loads(coinDict)[coin]
    size = coinInfo['volume'][1]

    stream = r.get('stream_' + coin)

    timeBlocks = json.loads(r.get('timeblocks_' + coin))
    #timeFlow = r.get('timeflow_' + coin)

    timeBlocks = getVWAP(timeBlocks, coin)

    # deltaBlocks = r.get('deltablocks_' + coin)
    # deltaFlow = r.get('deltaflow_' + coin)

    lastHistory = {}

    try:
        historyBlocks = json.loads(r.get('history_' + coin))
        if len(historyBlocks) > 0:
            lastHistory = historyBlocks[-1]
            # print(lastHistory.keys())
    except:
        print('NO HISTORY')

    if 'timeblocks_' + coin in lastHistory:
        ## combine History and current
        timeBlocks = lastHistory['timeblocks_' + coin] + timeBlocks

    if timeBlockSize > 5:
        timeBlocks = getBlocks(timeBlockSize/5, timeBlocks)

    deltaBlocks = []

    checkDelta = r.get('deltablocks_' + coin)

    if checkDelta:
        deltaBlocks = json.loads(checkDelta)

    # print('DELTA', deltaBlocks)
    # print('TIME', timeBlocks)

    # if 'deltablocks_' + coin in lastHistory:
    #     ## combine History and current
    #     deltaBlocks = lastHistory['deltablocks_' + coin] + deltaBlocks

    volumeBlocks = {}
    # volumeFlow = {}

    volumeCheck = r.get('volumeblocks_' + coin + str(size))
        # volumeFlow[size] = json.loads(r.get('volumeflow_' + coin + str(size)))

    if volumeCheck:
        volumeBlocks = json.loads(volumeCheck)


    if 'volumeblocks_' + coin + str(size) in lastHistory:
        ## combine History and current
        volumeBlocks = lastHistory['volumeblocks_' + coin + str(size)] + volumeBlocks



    for tb in timeBlocks:
        tb['tickList'] = getImbalances(tb['tickList'])
    for vb in volumeBlocks:
        vb['tickList'] = getImbalances(vb['tickList'])



    jDict = {
        'stream' : stream,
        'volumeBlocks' : json.dumps(volumeBlocks),
        'timeBlocks' : json.dumps(timeBlocks),
        'deltaBlocks' : json.dumps(deltaBlocks),
        'coin' : coin,
        'coinDict' : coinDict
    }

    jx = jsonify(jDict)

    # print('JSONIFY X', jDict)

    return jx



@app.route("/tradingview", methods=['POST'])
def tradingview_webhook():
    print('TRADING VIEW ACTION: ')
    data = json.loads(request.data)

    if data['code'] != SECRET_KEY:
        return False


    return redirect('/')


from routesJournal import *
from routesTrade import *


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
