from components import Transaction, Asset, Record
from utils import get_transactions

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
        eur_usd = Asset('EUR/USD', 'Forex', 'EURUSD', 'Degiro', '190143785', self.webparser)
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
                                        self.webparser, 
                                        self.eur_to_usd)
            self.assets[id].add_transaction(transaction)
            typ, asset = line['type'], line['asset']
            self.types[typ] = [asset] if typ not in self.types else set([*self.types[typ], asset])  
            self.types.pop(np.NaN, None)

    def get_historic_data(self, incl_fees=True, incl_dividends=True):
        for asset in self.assets.values():
            asset.get_historic_data(incl_fees, incl_dividends)

    def get_data(self, incl_fees=True, incl_dividends=True):
        def update_data(data, asset_data):
            data['Total'] += asset_data
            data[asset.type] += asset_data
            data[asset.name] = asset_data
            return data

        gains, gains_p, values = [], [], []
        
        for day in range((datetime.today().date() - self.creation_date).days+1):
            date = self.creation_date + timedelta(day)
            initial = {'Total':0, **{typ:0 for typ in list(self.types.keys())}}
            gain, gain_p, value, buy = initial.copy(), initial.copy(), initial.copy(), initial.copy()
            for asset in self.assets.values():
                if date in asset.gains:
                    gain = update_data(gain, asset.gains[date])
                    value = update_data(value, asset.values[date])
                    buy = update_data(buy, asset.buys[date])
                    gain_p[asset.name] = -100 * gain[asset.name] / buy[asset.name] if buy[asset.name]!=0 else gain[asset.name]
                      
            for key in ['Total', *[key for key in list(self.types.keys())]]:
                gain_p[key] = 100 * gain[key] / -buy[key] if buy[key] != 0 else gain[key]
            
            data = [gain, gain_p, value]
            for i in range(len(data)):
                data[i] = {key: np.round(value, 2) for key, value in data[i].items()}
                data[i]['date'] = date

            gain, gain_p, value = data 
            gains.append(gain)                    
            gains_p.append(gain_p)                    
            values.append(value)                    

        self.gains = pd.DataFrame(gains)
        self.gains.to_csv('data/gains.csv')
        
        self.gains_p = pd.DataFrame(gains_p)
        self.gains_p.to_csv('data/gains_p.csv')
        
        self.values = pd.DataFrame(values)
        self.values.to_csv('data/values.csv')
    
    def get_holdings(self):
        holding = {}
        holdings = []
        items = ['name', 'short_name', 'type', 'quantity', 'fee', 'buy', 'dividend', 'last_gain']
        total = {key: {**{'name':key}, **{item:0 for item in items[3:]+['gains_p', 'value']}} 
                 for key in ['Total']+list(self.types.keys())}
        for asset in self.assets.values():
            if not asset.last_gain:
                continue
            holding = {k:v for k,v in vars(asset).items() if k in items}
            holding['gains_p'] = 100 * holding['last_gain'] / - holding['buy'] if holding['buy'] != 0 else holding['last_gain']   
            holding['value'] = asset.last_price * asset.quantity
            for typ in ['Total', asset.type]:
                for item in ['value']+items[3:]: 
                    total[typ][item] += holding[item]
                total[typ]['gains_p'] = 100 * total[typ]['last_gain'] / -total[typ]['buy'] if  total[typ]['buy'] != 0 else total[typ]['last_gain']
            holdings.append(holding)
        for holding in total.values():
            holdings.append(holding)
        for holding in holdings:
            for key, value in holding.items():
                if key in ['value', 'gains_p']+items[4:]:
                    holding[key] = np.round(value, 2)
            if holding.get('type') == 'crypto' or holding['name'] in ['crypto', 'Total']:
                holding['quantity'] = np.round(holding['quantity'],3)
            else:    
                holding['quantity'] = int(holding['quantity']) 
        self.holdings = pd.DataFrame(holdings)
        self.holdings.to_csv('data/holdings.csv', index=False)

