## Full-stack Orderflow Application

# This orderflow application was designed to emulate services that provide orderflow data for markets.

It is a containerized application that contains several components.

* The main worker recieves and processes an appi data stream from the Bybit echange.
* This data is further processed through other celery workers that store the processed data in a Redis database.
* Stored data can be received by the front-end flask application which presents the data in various formats.
* As orderflow data is processed it is monitored for conditions that triggers alerts or allows a trading bot to take action.
* All operations can be monitored and changed through an active Discord Bot
* There are other features that allow for a trader to set, alter, or record trading actions.

