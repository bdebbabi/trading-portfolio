from pyotp import TOTP
import base64
import json
import requests
from datetime import date, datetime, timedelta
from Historic_Crypto import HistoricalData, LiveCryptoData
from coinbase.wallet.client import Client
from urllib.request import urlopen, Request
from io import StringIO
import pandas as pd
import yfinance as yf

class webparser:

    def __init__(self,authentification):
        def dec(param):
            if self.hashed:
                return base64.b64decode(param).decode("utf-8")
            else:
                return param
        
        self.hashed = authentification['HASHED']
        
        self.degiro_username = dec(authentification['DEGIRO']['USERNAME'])
        self.degiro_password = dec(authentification['DEGIRO']['PASSWORD'])
        self.degiro_key = dec(authentification['DEGIRO']['KEY'])
        
        self.coinbase_key = dec(authentification['COINBASE']['API_KEY'])
        self.coinbase_secret = dec(authentification['COINBASE']['API_SECRET'])

        self.headers = {'Content-Type': 'application/json'}
        self.login()

    def login(self):
        self.coinbase_login()
        self.degiro_login()

    def coinbase_login(self):
        self.client = Client(self.coinbase_key, self.coinbase_secret)

    def degiro_login(self):
        if self.degiro_key:
            totp = TOTP(self.degiro_key)
            token = totp.now()

            data = json.dumps({"username":self.degiro_username,"password":self.degiro_password,"oneTimePassword":token})
            url = 'https://trader.degiro.nl/login/secure/login/totp'

        else:
            data = json.dumps({"username":self.degiro_username,"password":self.degiro_password})
            url = 'https://trader.degiro.nl/login/secure/login'

        self.session = requests.Session()
        response = self.session.post(url,headers=self.headers,data=data)
        self.sessionID = response.cookies["JSESSIONID"]
        
        url = f'https://trader.degiro.nl/pa/secure/client?sessionId={self.sessionID}'
        client_info = self.session.get(url)
        self.userToken = json.loads(client_info.text)['data']['id']
        self.accountID = json.loads(client_info.text)['data']['intAccount']

    def get_asset_prices(self, asset_id, asset_type, start_date):
        if asset_type == 'Crypto':
            stock_info = HistoricalData(asset_id,
                                        86400,
                                        start_date.strftime('%Y-%m-%d-%H-%M'), 
                                        verbose=False).retrieve_data()
            prices = {time.to_pydatetime().date(): value 
                        for time, value in stock_info.to_dict()['close'].items()}
            currency = 'USD'
        
        else:
            today = datetime.today().date()
            last_year = today - timedelta(days=365)
            today = today.strftime('%Y-%m-%d')

            ticker = yf.Ticker(asset_id)
            day_history = ticker.history(start=start_date, end=today, interval='1d')
            if day_history.empty:
                return [], None
            hour_history = ticker.history(start=max([start_date,last_year]).strftime('%Y-%m-%d'), end=today, interval='1h')

            hour_history.index = hour_history.index.date
            day_history.index = day_history.index.date
            hour_history = hour_history[~hour_history.index.duplicated(keep='last')]
            day_history = pd.concat([day_history, hour_history[~hour_history.index.isin(day_history.index)]]).sort_index()
            day_history.loc[datetime.today().date()] = pd.Series({'Close':ticker.info['regularMarketPrice']})

            prices = day_history.to_dict()['Close']
            currency = ticker.info['currency']

        return prices, currency

    def get_stock_data(self, via):
        ids, types, symbols = {}, {}, {}
        if via == 'Degiro':
            url = f'https://trader.degiro.nl/trading/secure/v5/update/{self.accountID};jsessionid={self.sessionID}'
            portfolio_query = self.session.get(url,params={'portfolio':0})
            portfolio = json.loads(portfolio_query.text)['portfolio']['value']
            type_map = {'ETF':'Funds', 'STOCK':'Stock'}
            for product in portfolio:
                url = f'https://trader.degiro.nl/product_search/secure/v5/products/info?intAccount={self.accountID}&sessionId={self.sessionID}'
                res = self.session.post(url,headers=self.headers,data='["'+product["id"]+'"]')
                data = json.loads(res.text)['data'][product["id"]]
                if 'vwdIdentifierType' in data.keys():
                    stock_id = data['vwdId'] if data['vwdIdentifierType'] == 'issueid' else data['vwdIdSecondary']
                    isin = data.get('isin') 
                    ids[isin] = stock_id
                    types[isin] = type_map[data['productType']]
                    symbols[isin] = data['symbol']

        return ids, types, symbols
    
    def get_degiro_data(self, start_date):
        types, symbols = {}, {}
        url = f'https://trader.degiro.nl/trading/secure/v5/update/{self.accountID};jsessionid={self.sessionID}'
        portfolio_query = self.session.get(url,params={'portfolio':0})
        portfolio = json.loads(portfolio_query.text)['portfolio']['value']
        type_map = {'ETF':'Funds', 'STOCK':'Stock'}
        for product in portfolio:
            url = f'https://trader.degiro.nl/product_search/secure/v5/products/info?intAccount={self.accountID}&sessionId={self.sessionID}'
            res = self.session.post(url,headers=self.headers,data='["'+product["id"]+'"]')
            data = json.loads(res.text)['data'][product["id"]]
            if data.get('productType') in ['ETF', 'STOCK']:
                isin = data.get('isin') 
                types[isin] = type_map[data['productType']]
                symbols[isin] = data['symbol']

        end_date = datetime.now().date()
        data = []
        for report_type in ['cashAccountReport', 'transactionReport']:
            link = f"""https://trader.degiro.nl/reporting/secure/v3/{report_type}/csv
                    ?intAccount={self.accountID}
                    &sessionId={self.sessionID}
                    &country=FR
                    &lang=fr
                    &fromDate={start_date.strftime('%d')}%2F{start_date.strftime('%m')}%2F{start_date.strftime('%Y')}
                    &toDate={end_date.strftime('%d')}%2F{end_date.strftime('%m')}%2F{end_date.strftime('%Y')}
                    """
            link = ''.join(link.split())
            record = StringIO(urlopen(Request(link)).read().decode('utf-8'))
            data.append(pd.read_csv(record))

        return data + [types, symbols]