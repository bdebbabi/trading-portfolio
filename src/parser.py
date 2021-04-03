from pyotp import *
import base64
import json
import requests
from datetime import date, datetime, timedelta
from Historic_Crypto import HistoricalData, LiveCryptoData
from coinbase.wallet.client import Client
from urllib.request import urlopen, Request
from io import StringIO
import pandas as pd

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


    def get_new_stock_info(self,stock_id, via, start_date, resolution='P1D'):
        session = requests.Session()
        if via in ['Degiro', 'Boursorama']:
            period =  (datetime.now().date() - start_date).days
            series = ['issueid%3A' + stock_id, 'price%3Aissueid%3A' + stock_id]
            url = f'''https://charting.vwdservices.com/hchart/v1/deGiro/data.js?
                    requestid=1&
                    resolution={resolution}&
                    culture=fr-FR&
                    period=P{period}D&
                    series={series[0]}&
                    series={series[1]}&
                    format=json&
                    callback=vwd.hchart.seriesRequestManager.sync_response&
                    userToken={self.userToken}&
                    tz=Europe%2FAmsterdam'''
            url = ''.join(url.split())
            stock_info = json.loads(session.get(url).text[46:-1])

            currency = stock_info['series'][0]['data']['currency']
            last_price = stock_info['series'][0]['data']['lastPrice']
            start_time = datetime.strptime(stock_info['series'][1]['times'][:10],'%Y-%m-%d').date()
            prices = {}
        
            for data in stock_info['series'][1]['data']:
                day, price = data
                prices[start_time + timedelta(day)] = price
            

        elif via == 'Coinbase':
            stock_info = HistoricalData(stock_id,
                                        86400,
                                        start_date.strftime('%Y-%m-%d-%H-%M'), 
                                        verbose=False).retrieve_data()
            prices = {time.to_pydatetime().date(): value 
                        for time, value in stock_info.to_dict()['close'].items()}
            last_price = float(LiveCryptoData(stock_id, verbose=False).return_data()['price'][0])
            currency = 'USD'
        
        return prices, last_price, currency

    def get_stock_ids_and_type(self, via):
        ids, types = {}, {}
        if via == 'Degiro':
            url = f'https://trader.degiro.nl/trading/secure/v5/update/{self.accountID};jsessionid={self.sessionID}'
            portfolio_query = self.session.get(url,params={'portfolio':0})
            portfolio = json.loads(portfolio_query.text)['portfolio']['value']

            for product in portfolio:
                url = f'https://trader.degiro.nl/product_search/secure/v5/products/info?intAccount={self.accountID}&sessionId={self.sessionID}'
                res = self.session.post(url,headers=self.headers,data='["'+product["id"]+'"]')
                data = json.loads(res.text)['data'][product["id"]]
                if 'vwdIdentifierType' in data.keys():
                    stock_id = data['vwdId'] if data['vwdIdentifierType'] == 'issueid' else data['vwdIdSecondary']
                    isin = data.get('isin') 
                    ids[isin] = stock_id
                    types[isin] = data['productType']
        return ids, types
    
    def get_degiro_data(self, start_date):
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

        return data