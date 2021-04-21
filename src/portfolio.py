from components import Transaction, Asset, Record
from utils import get_transactions, get_dates
from datetime import datetime, timedelta
from parser import webparser
from tqdm import tqdm
import pandas as pd
import numpy as np
import json
import re

class Portfolio:
    def __init__(self, settings):
        self.creation_date = datetime.strptime(settings['CREATION_DATE'],
                                               '%Y-%m-%d').date()
        self.settings = settings
        self.assets = {}
        self.types = {}
        self.dates = get_dates(self.creation_date)

    def get_eur_usd(self):
        name = 'EUR/USD'
        eur_usd = Asset(name, 'Forex', name, 'Degiro', name, self.webparser)
        self.webparser.get_asset_data(set([tuple([name, 'EURO', name])]))
        eur_to_usd = eur_usd.get_historic_prices(self.creation_date)

        last_price = eur_to_usd[self.creation_date]
        for day in range((datetime.today().date() - self.creation_date).days+1):
            date = self.creation_date + timedelta(day)
            if date not in eur_to_usd:
                eur_to_usd[date] = last_price
            else:
                last_price = eur_to_usd[date]
        self.eur_to_usd = eur_to_usd

    def add_transactions(self, update_transactions=True):
        self.webparser = webparser(self.settings['AUTHENTIFICATION'])
        missing = []
        if update_transactions:
            self.webparser.login()
            transactions, missing = get_transactions(
                self.creation_date, self.webparser)
        else:
            transactions = pd.read_csv('data/transactions.csv')
            transactions['date'] = pd.to_datetime(
                transactions['date'], format='%Y-%m-%d %H:%M:%S')
        self.get_eur_usd()
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
                                        line['symbol'],
                                        self.webparser,
                                        self.eur_to_usd)
            self.assets[id].add_transaction(transaction)
            typ, asset = line['type'], line['asset']
            self.types[typ] = [asset] if typ not in self.types else list(set([
                *self.types[typ], asset]))
            self.types.pop(np.NaN, None)
        assets = {'assets': [
            asset.name for asset in self.assets.values()], 'types': self.types}
        with open('data/assets.json', 'w') as f:
            json.dump(assets, f, indent=4)

        return missing

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
            initial = {'Total': 0, **
                       {typ: 0 for typ in list(self.types.keys())}}
            gain, gain_p, value, buy, price = initial.copy(), initial.copy(
            ), initial.copy(), initial.copy(), initial.copy()
            for asset in self.assets.values():
                if date in asset.gains:
                    gain = update_data(gain, asset.gains[date])
                    value = update_data(value, asset.values[date])
                    buy = update_data(buy, asset.buys[date])
                    price[asset.name] = asset.prices[date]
                    gain_p[asset.name] = -100 * gain[asset.name] / \
                        buy[asset.name] if buy[asset.name] != 0 else gain[asset.name]

            for key in ['Total', *[key for key in list(self.types.keys())]]:
                gain_p[key] = 100 * gain[key] / - \
                    buy[key] if buy[key] != 0 else gain[key]

            data = [gain, gain_p, value, price]
            for i in range(len(data)):
                data[i] = {key: np.round(value, 2)
                           for key, value in data[i].items()}
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
        self.holdings = {}
        holdings = {key: [] for key in self.dates.keys()}
        items = ['name', 'symbol', 'type', 'quantity',
                 'fee', 'buy', 'dividend', 'gain', 'price']
        for key, date in self.dates.items():
            total = {key: {**{'name': key, 'symbol': key}, **{item: 0 for item in items[3:-1]+['gain_p', 'value']}}
                     for key in ['Total']+list(self.types.keys())}
            holding = {}
            for asset in self.assets.values():
                if not asset.gain:
                    continue
                holding = {k: v for k, v in vars(asset).items() if k in items}
                holding['value'] = asset.price * asset.quantity
                if date >= asset.start_date:
                    holding['fee'] -= asset.fees[date]
                    holding['dividend'] -= asset.dividends[date]
                    holding['gain'] -= asset.gains[date]
                holding['gain_p'] = 100 * holding['gain'] / - \
                    holding['buy'] if holding['buy'] != 0 else holding['gain']
                for typ in ['Total', asset.type]:
                    for item in ['value']+items[3:-1]:
                        total[typ][item] += holding[item]
                    total[typ]['gain_p'] = 100 * total[typ]['gain'] / - \
                        total[typ]['buy'] if total[typ]['buy'] != 0 else total[typ]['gain']
                holdings[key].append(holding)
            for holding in total.values():
                holdings[key].append(holding)
            for holding in holdings[key]:
                for item, value in holding.items():
                    if item in ['value', 'gain_p']+items[4:]:
                        holding[item] = np.round(value, 2)
                if holding.get('type') == 'Crypto' or holding['name'] in ['Crypto', 'Total']:
                    holding['quantity'] = np.round(holding['quantity'], 3)
                else:
                    holding['quantity'] = int(holding['quantity'])
            self.holdings[key] = pd.DataFrame(
                holdings[key]).sort_values('value', ascending=False)
            self.holdings[key].to_csv(f'data/holdings_{key}.csv', index=False)
    
    def get_composition(self):
        assets_total = {'countries':{}, 'regions':{}, 'sectors':{}, 'holdings':{}, 'holdings_types':{}}
        for asset in self.assets.values():
            if asset.type == 'Funds':
                compositions = asset.get_composition()
                for composition, values in compositions.items():
                    for key, value in values.items():
                        if composition != 'holdings_types':
                            assets_total[composition][key] = assets_total[composition].get(key, 0) + value
                        else:
                            assets_total[composition][key] =  value
 
        for key, values in assets_total.items():
            if key != 'holdings_types':
                total = np.round(np.sum(list(values.values())),2)
                value = {}
                for k,v in values.items():
                    if key not in ['holdings', 'holdings_types']:
                        k = k[0].upper() + k[1:]
                        k = ' '.join(re.findall('[A-Z][^A-Z]*', k))
                    value[k] = np.round(100*v/total,2)
                assets_total[key] = dict(sorted(value.items(), key=lambda item: item[1], reverse=True))
                first = list(assets_total[key].keys())[0]
                assets_total[key][first] = np.round(assets_total[key][first] + 100 - np.sum(list(assets_total[key].values())),2)

        self.composition = assets_total
        with open('data/composition.json', 'w') as f:
            json.dump(assets_total, f, indent=4)

        return assets_total
