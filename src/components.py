from datetime import datetime, timedelta
import textwrap
import os.path
import json

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
    def __init__(self, name, typ, id, via, symbol, web_parser, eur_to_usd=None):
        self.name = name
        self.symbol = symbol
        self.type = typ
        self.id = self.check_id(id)
        self.quantity = 0
        self.transactions = []
        self.records = []
        self.buy = 0
        self.sell = 0
        self.fee = 0
        self.dividend = 0
        self.last_dividend = None
        self.via = via
        self.web_parser = web_parser
        self.eur_to_usd = eur_to_usd
        self.gains = {}

    def check_id(self,id):
        ids_path = 'assets/ids.json'
        if os.path.isfile(ids_path):
            with open(ids_path, 'r') as f:
                ids = json.load(f)
            id = ids.get(id, id)
        return id

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
        else:
            self.start_date = transaction.datetime.date()
        self.records.append(Record(transaction.datetime, 
                                   self.quantity, 
                                   self.buy, 
                                   self.sell,
                                   self.fee, 
                                   self.dividend))

    def get_historic_data(self, incl_fees=True, incl_dividends=True):
        current_date = self.records[0].start_datetime.date()
        gains, values, buys, quantities, fees, dividends, prices = {}, {}, {}, {}, {}, {}, {}
        prices = self.get_historic_prices(current_date)
        if prices == [] or current_date not in prices.keys():
            self.gains = self.value = {}
            self.gain = None
            return
        last_price = prices[current_date]
        for record in self.records:
            last = 1 if record.end_datetime.date() == datetime.today().date() else 0
            while record.start_datetime.date()<=current_date<record.end_datetime.date()+timedelta(last):
                if current_date in prices:
                    last_price = prices[current_date]
                gain = last_price * record.quantity + record.sell + record.buy
                buy = record.buy
                if incl_fees:
                    gain += record.fee
                    buy += record.fee
                if incl_dividends:
                    gain += record.dividend

                gains[current_date] = gain 
                values[current_date] = last_price * record.quantity
                buys[current_date] = buy
                quantities[current_date] = record.quantity
                fees[current_date] = record.fee
                dividends[current_date] = record.dividend
                prices[current_date] = last_price
                current_date += timedelta(1)

        last_gain = last_price * self.quantity + self.sell + self.buy
        if incl_fees:
            last_gain += self.fee
        if incl_dividends:
            last_gain += self.dividend

        self.gains = gains
        self.values = values
        self.buys = buys
        self.quantities = quantities
        self.fees = fees
        self.dividends = dividends
        self.prices = prices
        self.gain = last_gain
        self.price = last_price

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
    
    def get_historic_prices(self, start_date, local_currency=False):
        prices, currency = self.web_parser.get_asset_prices(self.id, self.type, start_date)

        if currency == 'USD' and not local_currency and self.id != 'EUR/USD':
            for date, price in prices.items():
                prices[date] = price / self.eur_to_usd[date]

        return prices

    def get_composition(self):
        compositions =  self.web_parser.get_asset_composition(self.id, self.type, self.name)
        self.composition = compositions
        last_value = self.values[list(self.values.keys())[-1]]
        for composition, values in compositions.items():
            if composition != 'holdings_types':
                compositions[composition] = {key: [last_value*ratio/100, f'{ratio:.2f}%'] for key, ratio in values.items()}
        return compositions

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