import pandas as pd
import schedule
import time
import config
import asyncio
import ccxt
from binance.client import Client
from binance.enums import *


TIMEFRAME = '15m'
STOP_LOSS_PERCENTAGE = 0.005
TAKE_PROFIT_PERCENTAGE = 0.01
SYMBOL = 'ETH/USDT'

pd.set_option("display.max_rows", None, "display.max_columns", None)


class CryptoBot:
    def __init__(self):
        self.stop_loss_take_profit_of_trade = None
        self.exchange = ccxt.binance({
            'apiKey': config.API_KEY,
            'secret': config.SECRET_KEY,
        })

        # Init defaults
        self.in_position = False
        self.in_margin_short_trade = False

        # initialise the client
        self.client = Client(config.API_KEY, config.SECRET_KEY)
        self.USDT_balance = self.client.get_max_margin_transfer(asset='USDT')['amount']

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

    def fetch_candles(self):
        return self.exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=100)

    def check_get_into_trade_opportunities(self):

        # long
        if self.get_into_long_position():
            self.handle_order()

        # short
        if self.get_into_short_position():
            self.in_margin_short_trade = True
            self.handle_order()

    def stop_loss_take_profit_of_trade(self):
        if self.in_position:
            last_row_index = len(self.df.index) - 1
            curr_price = self.df['close'][last_row_index]
            # long
            if self.side == SIDE_BUY:
                if curr_price >= (self.entry_price * (1 + TAKE_PROFIT_PERCENTAGE)) or curr_price <= (self.entry_price * (1 - STOP_LOSS_PERCENTAGE)):
                    self.in_position = False
                    self.client.create_margin_order('ETHUSDT', SIDE_SELL, self.amount)
                    self.stop_loss_take_profit_of_trade = self.df[''][last_row_index]

            # short
            elif self.side == SIDE_SELL and self.in_margin_short_trade:
                print('short stop loss take profit')

    def create_margin_order(self, symbol,  side, amount):
        return self.client.create_margin_order(symbol=symbol, side=side, type=ORDER_TYPE_MARKET, quantity=0.01)

    def handle_order(self):
        if self.in_margin_short_trade:
            self.short_handler()
        else:
             self.long_handler()

    def short_handler(self):
        print('margin')
        # enter order
        # self.set_free_USDT_balance_on_account()
        # amount_ETH_to_buy = format(self.calculate_max_amount_of_ETH_USDT(), ".8f")
        # self.client.create_margin_loan()
        '''

        1. fetch balance
        2. calc amount of USDT/ETH
        3. make loan of amount
        4. check res fees 
        5. sell order 
        6. save amount - fees
        
        '''

    def long_handler(self):
        if not self.in_position:
            # enter order
            last_row_index = len(self.df.index) - 1

            self.set_free_USDT_balance_on_account()
            amount_ETH_to_buy = format(self.calculate_max_amount_of_ETH_USDT(), ".8f")

            print(amount_ETH_to_buy)
            # print min amount to buy of ETH/USDT
            #info = self.client.get_symbol_info('ETHUSDT')
            #print(info)

            response = self.create_margin_order('ETHUSDT', SIDE_BUY, amount_ETH_to_buy)
            self.entry_price = float(response['fills'][0]['price'])
            self.amount = float(response['fills'][0]['qty']) - float(response['fills'][0]['commission'])
            self.side = response['side']
            self.candle_of_entring_to_trade = self.df['timestamp'][last_row_index]

            self.in_position = True

            self.stop_loss_take_profit_of_trade()

            print(response)

        '''
        1. fetch balance
        2. calc amount of USDT/ETH
        3. make order
        4. from response save (the amount - fees )   
        '''

    def set_free_USDT_balance_on_account(self):
        self.USDT_balance = self.client.get_max_margin_transfer(asset='USDT')['amount']

    def calculate_max_amount_of_ETH_USDT(self):
        last_row_index = len(self.df.index) - 1
        return float(self.USDT_balance) / float(self.df['close'][last_row_index].astype('float'))

    def get_into_long_position(self):
        last_row_index = len(self.df.index) - 2
        previous_last_row_index = last_row_index - 1

        return (not self.df['_short_trend'][last_row_index] and self.df['_short_trend'][previous_last_row_index] and not self.df['_long_trend'][last_row_index] and not self.in_position) or (not self.df['_long_trend'][last_row_index] and self.df['_long_trend'][previous_last_row_index] and not self.df['_short_trend'][last_row_index] and not self.in_position)

    def get_into_short_position(self):
        last_row_index = len(self.df.index) - 2
        previous_last_row_index = last_row_index - 1

        return (not self.df['_short_trend'][last_row_index] and self.df['_short_trend'][previous_last_row_index] and not self.df['_long_trend'][last_row_index] and not self.in_position) or (not self.df['_long_trend'][last_row_index] and self.df['_long_trend'][previous_last_row_index] and not self.df['_short_trend'][last_row_index] and not self.in_position)

    def run_bot(self):
        self.df = pd.DataFrame(self.fetch_candles(), columns=['timestamp', 'open', 'high', 'low', 'close', ' volume'])
        self.df['timestamp'] = pd.to_datetime(self.df['timestamp'], unit='ms')
        self.true_range()

        self.supertrend('_short_trend')
        self.supertrend('_long_trend', 20, 5)

        self.check_get_into_trade_opportunities()
        self.stop_loss_take_profit_of_trade()

        print('long')
        self.long_handler()



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
