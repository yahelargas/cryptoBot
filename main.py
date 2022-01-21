import pandas as pd
import schedule
import time
import config
import asyncio
import ccxt
from binance.client import Client
from binance.enums import *


TIMEFRAME = '15m'
pd.set_option("display.max_rows", None, "display.max_columns", None)


class CryptoBot:
    def __init__(self):
        self.exchange = ccxt.binance({
            'apiKey': config.API_KEY,
            'secret': config.SECRET_KEY,
        })
        self.in_position = False

        # initialise the client
        self.client = Client(config.API_KEY, config.SECRET_KEY)


    def true_range(self):
        self.add_true_range_to_data_frame(self.calculate_true_range())

    def calculate_true_range(self):

        self.df['previous_close'] = self.df['close'].shift(1)
        self.df['high-low'] = self.df['high'] - self.df['low']
        self.df['high-pc'] = self.df['high'] - self.df['previous_close']
        self.df['low-pc'] = self.df['low'] - self.df['previous_close']

        tr = self.df[['high-low', 'high-pc', 'low-pc']].max(axis=1)

        return tr

    def add_true_range_to_data_frame(self, tr):
        self.df['true_range'] = tr

    def average_true_range(self, trend_type, period=14):
        self.add_first_average_true_range(trend_type, period)
        self.calculate_average_true_range(trend_type, period)

    def add_first_average_true_range(self, trend_type, period):
        self.df.at[period - 1, 'average_true_range' + trend_type] = self.df['true_range'][:period - 1].sum() / period

    def calculate_average_true_range(self, trend_type, period):
        for current in range(period, len(self.df.index)):
            previous = current - 1

            self.df.at[current, 'average_true_range' + trend_type] = (self.df['average_true_range' + trend_type][previous] * (period - 1) + self.df['true_range'][current]) / period

    def supertrend(self, trend_type, period=10, multiplier=3):
        self.average_true_range(trend_type, period)
        self.df['upperband' + trend_type] = ((self.df['high'] + self.df['low']) / 2) + (multiplier * self.df['average_true_range' + trend_type])
        self.df['lowerband' + trend_type] = ((self.df['high'] + self.df['low']) / 2) - (multiplier * self.df['average_true_range' + trend_type])

        self.df[trend_type] = True

        for current in range(1, len(self.df.index)):
            previous = current - 1

            if self.df['close'][current] >= self.df['upperband' + trend_type][previous]:
                self.df.at[current, trend_type] = True
            elif self.df['close'][current] <= self.df['lowerband' + trend_type][previous]:
                self.df.at[current, trend_type] = False
            else:
                self.df.at[current, trend_type] = self.df[trend_type][previous]

                if self.df[trend_type][current] and self.df['lowerband' + trend_type][current] < self.df['lowerband' + trend_type][previous]:
                    self.df.at[current, 'lowerband' + trend_type] = self.df['lowerband' + trend_type][previous]

                if not self.df[trend_type][current] and self.df['upperband' + trend_type][current] > self.df['upperband' + trend_type][previous]:
                    self.df.at[current, 'upperband' + trend_type] = self.df['upperband' + trend_type][previous]

    def run_bot(self):
        bars = self.exchange.fetch_ohlcv('ETH/USDT', timeframe=TIMEFRAME, limit=100)
        self.df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', ' volume'])
        self.df['timestamp'] = pd.to_datetime(self.df['timestamp'], unit='ms')
        self.true_range()

        self.supertrend('_short_trend')
        self.supertrend('_long_trend', 20, 5)

        self.check_buy_sell_signals()

    def check_buy_sell_signals(self):
        last_row_index = len(self.df.index) - 1
        previous_last_row_index = last_row_index - 1
        if (self.df['_short_trend'][last_row_index] and not self.df['_short_trend'][previous_last_row_index] and self.df['_long_trend'][last_row_index] and not self.in_position ) or ( self.df['_long_trend'][last_row_index] and not self.df['_long_trend'][previous_last_row_index] and self.df['_short_trend'][last_row_index] and not self.in_position):
            print('buy order')
            print(self.df.tail(4))
            self.in_position = True

        if (not self.df['_short_trend'][last_row_index] and self.df['_short_trend'][previous_last_row_index] and not self.df['_long_trend'][last_row_index] and not self.in_position) or (not self.df['_long_trend'][last_row_index] and self.df['_long_trend'][previous_last_row_index] and not self.df['_short_trend'][last_row_index] and not self.in_position):
            print('sell order')
            print(self.df.tail(4))
            self.in_position = False

    async def create_order(self, symbol,  side, amount):
        await self.client.create_order(symbol=symbol, side=side, amount=amount)

    async def create_margin_order(self, symbol,  side, amount):
        await self.exchange.create_order(symbol, side, amount, {
            'type': 'margin',
        })



def searching():
    print("searching...")


async def main(asyncio_loop):
    try:

        bot = CryptoBot()
        schedule.every(10).seconds.do(bot.run_bot)
        schedule.every(1).hours.do(searching)

        while True:
            schedule.run_pending()
            time.sleep(1)
    except Exception as e:
        print(f'error: {e}')


if __name__ == '__main__':
    asyncio_loop = asyncio.get_event_loop()
    asyncio_loop.run_until_complete(main(asyncio_loop))
