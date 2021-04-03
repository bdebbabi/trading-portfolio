from datetime import datetime, timedelta
import numpy as np
import textwrap

class Transaction:
    def __init__(self, datetime, id, value, quantity, fee, description, via):
        self.datetime  = datetime 
        self.id = id  
        self.value = value  
        self.quantity = quantity  
        self.fee = fee  
        self.description = description  
        self.via = via  
    
    def __repr__(self):
        return f'Transaction(datetime={self.datetime}, value={self.value:.2f}, quantity={self.quantity}, fee={self.fee:.2f})'

            

class Asset:
    def __init__(self, name, typ, id, via, parser_id, web_parser, eur_to_usd=None):
        self.name = name
        self.short_name = self.clean_name(name)
        self.type = typ
        self.id = id
        self.quantity = 0
        self.transactions = []
        self.records = []
        self.buy = 0
        self.sell = 0
        self.fee = 0
        self.dividend = 0
        self.last_dividend = None
        self.via = via
        self.parser_id = parser_id
        self.web_parser = web_parser
        self.eur_to_usd = eur_to_usd
        self.gains = {}

    def add_transaction(self, transaction):
        self.transactions.append(transaction)

        if transaction.description == 'dividend':
            self.dividend += transaction.value 
            self.last_dividend = transaction.datetime
        else:
            self.quantity += transaction.quantity
            if transaction.value<0:
                self.buy += transaction.value
            else:
                self.sell += transaction.value
            self.fee += transaction.fee
            
        if self.records != []:
            self.records[-1].end_datetime = transaction.datetime

        self.records.append(Record(transaction.datetime, 
                                   self.quantity, 
                                   self.buy, 
                                   self.sell,
                                   self.fee, 
                                   self.dividend))

    def get_historic_data(self, incl_fees=True, incl_dividends=True):
        current_date = self.records[0].start_datetime.date()
        gains, values, buys = {}, {}, {}
        if self.parser_id is np.NaN:
            self.gains = self.value = {}
            self.last_gain = None
            return
        prices, last_price, _ = self.get_historic_prices(current_date)
        for record in self.records:
            while record.start_datetime.date()<=current_date<record.end_datetime.date():
                if current_date in prices:
                    gain = prices[current_date] * record.quantity + record.sell + record.buy
                    buy = record.buy
                    if incl_fees:
                        gain += record.fee
                        buy += record.fee
                    if incl_dividends:
                        gain += record.dividend
                    gains[current_date] = gain 
                    values[current_date] = prices[current_date] * record.quantity
                    buys[current_date] = buy
                current_date += timedelta(1)
        last_gain = last_price * self.quantity + self.sell + self.buy
        if incl_fees:
            last_gain += self.fee
        if incl_dividends:
            last_gain += self.dividend

        temp_gains, temp_values, temp_buys = {}, {}, {}
        first_date = list(gains.keys())[0] 
        current_gain = gains[first_date]
        current_value = values[first_date]
        current_buy = buys[first_date]

        for day in range((datetime.today().date() - first_date).days+1):
            date = first_date + timedelta(day)
            if date not in gains:
                temp_gains[date] = current_gain
                temp_values[date] = current_value
                temp_buys[date] = current_buy
            else:
                temp_gains[date] = gains[date]
                temp_values[date] = values[date]
                temp_buys[date] = buys[date]
                current_gain, current_buy, current_value = gains[date], buys[date], values[date]
        
        self.gains = temp_gains
        self.values = temp_values
        self.buys = temp_buys
        self.last_gain = last_gain
        self.last_price = last_price

    def get_asset_record(self, datetime):
        for record in self.records:
            if record.start_datetime <= datetime <= record.end_datetime:
                return record
    
    def get_transactions(self):
        for transaction in self.transactions:
            print(transaction)

    def get_records(self):
        for record in self.records:
            print(record) 
    
    def get_historic_prices(self, start_date, resolution='P1D', local_currency=False):
        prices, last_price, currency = self.web_parser.get_new_stock_info(self.parser_id, self.via, start_date, resolution)
        
        if currency == 'USD' and not local_currency and self.id != 'EURUSD':
            eur_usd, last_eur_usd  = self.eur_to_usd
            for date, price in prices.items():
                prices[date] = price / eur_usd[date]
            last_price = last_price / last_eur_usd

        return prices, last_price, currency

    def clean_name(self, name):
        for start in ['ISHARES ', 'VANGUARD ', 'LYXOR ']:
            name = name.replace(start, '')
        if len(name)>7:
            name = name[:7] + '...'
        return name

    def __repr__(self):
        rep = textwrap.dedent(
            f'''Asset(name:{self.name}, 
                id: {self.id}, 
                buy: {self.buy:.2f}, 
                quantity: {self.quantity}, 
                fee: {self.fee:.2f}, 
                dividend: {self.dividend:.2f})
            '''
        ) 
        return rep

class Record:
    def __init__(self, start_datetime, quantity, buy, sell, fee, dividend):
        self.start_datetime = start_datetime
        self.quantity = quantity 
        self.buy = buy 
        self.sell = sell
        self.fee = fee 
        self.dividend = dividend
        self.end_datetime = datetime.now()
    
    def __repr__(self):
        return f'start time: {self.start_datetime}, end time: {self.end_datetime},quantity: {self.quantity}, buy: {self.buy:.2f}, sell: {self.sell:.2f}, fee: {self.fee:.2f}, dividend: {self.dividend:.2f})'