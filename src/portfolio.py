from components import Transaction, Asset, Record
from utils import get_transactions
from tqdm import tqdm
from parser import webparser
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

class Portfolio:
    def __init__(self, settings):
        self.creation_date = datetime.strptime(settings['CREATION_DATE'], 
                                               '%Y-%m-%d').date()
        self.webparser = webparser(settings['AUTHENTIFICATION'])
        self.assets = {}
        self.types = {}
        self.get_eur_usd()

    def get_eur_usd(self):
        eur_usd = Asset('EUR/USD', 'Forex', 'EURUSD', 'Degiro', '190143785', 'EUR/USD', self.webparser)
        eur_to_usd, last_eur_to_usd , _ = eur_usd.get_historic_prices(self.creation_date)

        last_price = eur_to_usd[self.creation_date]
        for day in range((datetime.today().date() - self.creation_date).days+1):
            date = self.creation_date + timedelta(day)
            if date not in eur_to_usd:
                eur_to_usd[date] = last_price
            else:
                last_price = eur_to_usd[date]
        self.eur_to_usd = eur_to_usd, last_eur_to_usd

    def add_transactions(self):
        transactions = get_transactions(self.creation_date, self.webparser)
        self.transactions = transactions
        for line in transactions.iterrows():
            line = line[1]
            id = line['id']
            transaction = Transaction(
                line['date'],
                line['id'],
                line['value'],
                line['quantity'],
                line['fees'],
                line['description'],
                line['via']
            )
            if id not in self.assets:
                self.assets[id] = Asset(line['asset'], 
                                        line['type'], 
                                        line['id'], 
                                        line['via'], 
                                        line['webparser_id'], 
                                        line['symbol'], 
                                        self.webparser,
                                        self.eur_to_usd)
            self.assets[id].add_transaction(transaction)
            typ, asset = line['type'], line['asset']
            self.types[typ] = [asset] if typ not in self.types else set([*self.types[typ], asset])  
            self.types.pop(np.NaN, None)

    def get_historic_data(self, incl_fees=True, incl_dividends=True):
        for asset in tqdm(self.assets.values()):
            asset.get_historic_data(incl_fees, incl_dividends)

    def get_data(self, incl_fees=True, incl_dividends=True):
        def update_data(data, asset_data):
            data['Total'] += asset_data
            data[asset.type] += asset_data
            data[asset.name] = asset_data
            return data

        gains, gains_p, values, prices = [], [], [], []
        
        for day in range((datetime.today().date() - self.creation_date).days+1):
            date = self.creation_date + timedelta(day)
            initial = {'Total':0, **{typ:0 for typ in list(self.types.keys())}}
            gain, gain_p, value, buy, price = initial.copy(), initial.copy(), initial.copy(), initial.copy(), initial.copy()
            for asset in self.assets.values():
                if date in asset.gains:
                    gain = update_data(gain, asset.gains[date])
                    value = update_data(value, asset.values[date])
                    buy = update_data(buy, asset.buys[date])
                    price = update_data(price, asset.prices[date])
                    gain_p[asset.name] = -100 * gain[asset.name] / buy[asset.name] if buy[asset.name]!=0 else gain[asset.name]
                      
            for key in ['Total', *[key for key in list(self.types.keys())]]:
                gain_p[key] = 100 * gain[key] / -buy[key] if buy[key] != 0 else gain[key]
            
            data = [gain, gain_p, value, price]
            for i in range(len(data)):
                data[i] = {key: np.round(value, 2) for key, value in data[i].items()}
                data[i]['date'] = date

            gain, gain_p, value, price = data 
            gains.append(gain)                    
            gains_p.append(gain_p)                    
            values.append(value)                    
            prices.append(price)                    

        self.gains = pd.DataFrame(gains)
        self.gains.to_csv('data/gains.csv')
        
        self.gains_p = pd.DataFrame(gains_p)
        self.gains_p.to_csv('data/gains_p.csv')
        
        self.values = pd.DataFrame(values)
        self.values.to_csv('data/values.csv')

        self.prices = pd.DataFrame(prices)
        self.prices.to_csv('data/prices.csv')

    def get_holdings(self):
        today = datetime.today().date()
        self.holdings = {}
        self.dates = {
            'All': self.creation_date, 
            '1Y': today-timedelta(365),
            'YTD': datetime(today.year, 1,1).date(),
            '1M': today-timedelta(30),
            '1W': today-timedelta(7),
            '1D': today-timedelta(1)
            }
        holdings = {key:[] for key in self.dates.keys()}
        items = ['name', 'symbol', 'type', 'quantity', 'fee', 'buy', 'dividend', 'gain', 'price']
        for key, date in self.dates.items():
            total = {key: {**{'name':key, 'symbol':key}, **{item:0 for item in items[3:]+['gain_p', 'value']}} 
                    for key in ['Total']+list(self.types.keys())}
            holding = {}
            for asset in self.assets.values():
                if not asset.gain:
                    continue
                holding = {k:v for k,v in vars(asset).items() if k in items}
                holding['value'] = asset.price * asset.quantity
                if date >= asset.start_date:
                    # holding['value'] -= asset.values[date]
                    # holding['quantity'] -= asset.quantities[date]
                    holding['fee'] -= asset.fees[date]
                    holding['dividend'] -= asset.dividends[date]
                    holding['gain'] -= asset.gains[date]
                holding['gain_p'] = 100 * holding['gain'] / - holding['buy'] if holding['buy'] != 0 else holding['gain']   
                for typ in ['Total', asset.type]:
                    for item in ['value']+items[3:]: 
                        total[typ][item] += holding[item]
                    total[typ]['gain_p'] = 100 * total[typ]['gain'] / -total[typ]['buy'] if  total[typ]['buy'] != 0 else total[typ]['gain']
                holdings[key].append(holding)
            for holding in total.values():
                holdings[key].append(holding)
            for holding in holdings[key]:
                for item, value in holding.items():
                    if item in ['value', 'gain_p']+items[4:]:
                        holding[item] = np.round(value, 2)
                if holding.get('type') == 'Crypto' or holding['name'] in ['Crypto', 'Total']:
                    holding['quantity'] = np.round(holding['quantity'],3)
                else:    
                    holding['quantity'] = int(holding['quantity']) 
            self.holdings[key] = pd.DataFrame(holdings[key]).sort_values('value', ascending=False)
            self.holdings[key].to_csv(f'data/holdings_{key}.csv', index=False)
