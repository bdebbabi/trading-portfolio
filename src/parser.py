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
import investpy
from pathlib import Path
from investpy.utils.search_obj import SearchObj, random_user_agent
from lxml import html

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
            stock_info = HistoricalData(asset_id+'-USD',
                                        86400,
                                        start_date.strftime('%Y-%m-%d-%H-%M'), 
                                        verbose=False).retrieve_data()
            prices = {time.to_pydatetime().date(): value 
                        for time, value in stock_info.to_dict()['close'].items()}
            currency = 'USD'
        
        else:
            if asset_id not in self.assets_data:
                return [], None
            data = self.assets_data[asset_id]
            data = SearchObj(**data)
            if data.pair_type=='currencies':
                currency = data.symbol.split('/')[1]
            else:
                url = f"https://www.investing.com{data.tag}"
                headers = {
                    "User-Agent": random_user_agent(),
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "text/html",
                    "Accept-Encoding": "gzip, deflate",
                    "Connection": "keep-alive",
                }

                req = requests.get(url, headers=headers)
                page = html.fromstring(req.content)
                if data.pair_type=='stocks':
                    # price = float(page.xpath("//span[@class='instrument-price_last__KQzyA']/text()")[0])
                    currency = page.xpath("//span[@class='instrument-metadata_text__2iS5i font-bold']/text()")[0]
                elif data.pair_type=='etfs':
                    # price = float(page.xpath("//span[@id='last_last']/text()")[0])
                    pos = req.text.find('Currency in')
                    currency = req.text[pos+31 : pos+34]
            
            today = datetime.today().date()
            prices = data.retrieve_historical_data(from_date=start_date.strftime('%d/%m/%Y'), to_date=today.strftime('%d/%m/%Y'))
            prices.index = prices.index.date
            prices = prices.to_dict()['Close'] 
            
        return prices, currency


    def get_asset_data(self, transactions):
        exchanges = {
            'MIL':'Milan',
            'XET':'Xetra',
            'FRA':'Frankfurt',
            'EPA':'Paris',
            'EAM':'Amsterdam',
            'NDQ':'NASDAQ',
            'NSY':'NYSE',
            'EURO':''
        }

        countries = {
            'MIL':'italy',
            'XET':'germany',
            'FRA':'germany',
            'EPA':'france',
            'EAM':'netherlands',
            'NDQ':'united states',
            'NSY':'united states',
            'EURO':'euro zone'
        }

        path = 'data/assets_data.csv'
        types, symbols = {}, {}
        new_assets_data = []
        type_map = {'stocks': 'Stock', 'etfs': 'Funds', 'currencies':'Currencies'}
        if Path(path).is_file():
            assets_data = pd.read_csv(path)
            assets_dict = assets_data.to_dict('list')
            types = {id: type_map[value] for id, value in zip(assets_dict['ID'], assets_dict['pair_type'])}
            symbols = {id: value for id, value in zip(assets_dict['ID'], assets_dict['symbol'])}
            assets = set(assets_data.groupby(['ID', 'EXCHANGE', 'ASSET']).groups.keys())

            transactions = transactions - assets

        for id, exchange, asset in transactions:
            country = countries[exchange]
            parser_exchange = exchanges[exchange]
            try:
                results =  investpy.search_quotes(text=id, 
                                                products=['stocks', 'etfs','currencies'], 
                                                countries=[country], 
                                                n_results=5)
                for result in results:
                    if result.exchange == parser_exchange:
                        types[id] = type_map[result.pair_type]
                        symbols[id] = result.symbol
                        new_asset = vars(result)
                        new_asset.update({'ID':id, 'EXCHANGE':exchange, 'ASSET':asset})
                        new_assets_data.append(new_asset)
            except:
                print(f'Missing data for {asset}')        
        new_assets_data = pd.DataFrame(new_assets_data)
        if Path(path).is_file():
            assets_data = pd.concat([assets_data, new_assets_data], ignore_index=True)
        else:
            assets_data = new_assets_data
        
        assets_data.to_csv(path, index=False)
        ids = assets_data.to_dict()['ID'].values()
        assets_data.drop(['ID', 'EXCHANGE', 'ASSET'], axis=1, inplace=True)
        self.assets_data = {id: data for id, data in zip(
                                    ids,
                                    assets_data.to_dict('index').values())}

        
        return types, symbols

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
