from urllib.request import Request, urlopen
from datetime import date, datetime, timedelta
from pathlib import Path
from io import StringIO
import base64
import json

from investpy.utils.search_obj import SearchObj, random_user_agent
from Historic_Crypto import HistoricalData, LiveCryptoData
from coinbase.wallet.client import Client
from pyotp import TOTP
from lxml import html
import pandas as pd
import investpy
import requests


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
            start_date = start_date-timedelta(1)
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
        data = pd.read_csv('assets/exchanges.csv',index_col='exchange')
        data.fillna('', inplace=True)
        
        exchanges = data.to_dict()['name'] 
        countries = data.to_dict()['country']

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
        missing = []
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
                missing.append(asset)     
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

        
        return types, symbols, missing

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

    def get_asset_composition(self, id, asset_type, name):

        def get_exposure(id, comp_type, component):
            url=f'https://api-global.morningstar.com/sal-service/v1/etf/{comp_type}/{id}/data?languageId=en&locale=en&clientId=MDC&benchmarkId=category&component={component}&version=3.31.0'
            headers = {'ApiKey': 'lstzFDEOhfFNMLikKa0am9mgEKLBl49T'}
            req = requests.get(url, headers=headers)
            return json.loads(req.text) 

        def get_tick_ex(id):
            req = requests.get(f'https://www.morningstar.com/search?query={id}')
            page = html.fromstring(req.content)
            exchange = page.xpath("//span[@class='mdc-security-module__exchange']/text()")[0]
            ticker = page.xpath("//span[@class='mdc-security-module__ticker']/text()")[0]

            return exchange, ticker

        def get_parser_site_id(id):
            exchange, ticker = get_tick_ex(id)
            url = f'https://www.morningstar.com/etfs/{exchange}/{ticker}/portfolio'
            req = requests.get(url)
            pos = req.text.find('byId')
            pos = pos+21 if req.text[pos+20] == ',' else pos+7
            site_id = req.text[pos:pos+10]
            
            return site_id, url

        def get_site_id(id):
            path = 'data/composition_ids.json'
            composition_ids = {}
            if Path(path).is_file():
                with open(path, 'r') as f:
                    composition_ids = json.load(f)
            if id in composition_ids:
                site_id, url, _ = composition_ids[id]
            else:
                if asset_type == 'Funds':
                    site_id, url = get_parser_site_id(id)
                else:
                    exchange, ticker = get_tick_ex(id)
                    site_id = exchange+'/'+ticker
                    url = None
                composition_ids[id] = [site_id, url, name]
                
                with open(path, 'w') as f:
                    json.dump(composition_ids, f, indent=4)
            return site_id
        
        if asset_type == 'Funds':
            site_id = get_site_id(id)
            composition_component = 'sal-components-mip-country-exposure'
            req = get_exposure(site_id, 'portfolio/regionalSectorIncludeCountries', composition_component)
            countries = {country['name']:country['percent'] for country in req['fundPortfolio']['countries'] if country.get('percent',0)!=0}
            regions = {region['name']:region['percent'] for region in req['fundPortfolio']['regions'] if region.get('percent',0)!=0}

            req = get_exposure(site_id, 'portfolio/v2/sector', composition_component)
            sectors = {k:v for k,v in list(req['EQUITY']['fundPortfolio'].items())[1:] if v is not None}

            req = get_exposure(site_id, 'portfolio/holding', composition_component)
            if req['holdingSummary']['topHoldingWeighting'] == 100 and req['numberOfHolding'] == 1:
                site_id = get_site_id(req['holdingActiveShare']['etfBenchmarkProxyName'])
                req = get_exposure(site_id, 'portfolio/holding', composition_component)
            holdings, holdings_types = {}, {}
            for holding_type in ['equityHoldingPage', 'boldHoldingPage', 'otherHoldingPage']:
                for holding in req[holding_type]['holdingList']:
                    securityName = holding['securityName'].rsplit(' ', 1)[0] if holding['securityName'][-1]=='%' else holding['securityName'] 
                    holdings.update({securityName:holdings.get(securityName, 0) + holding['weighting']})
                    sector = holding['sector'] if holding['sector'] else holding['secondarySectorName'] 
                    holdings_types.update({securityName:{'sector':sector, 'country':holding['country']}})
            holdings =  dict(sorted(holdings.items(), key=lambda item: item[1], reverse=True))

            req = get_exposure(site_id, 'process/weighting', 'sal-components-mip-style-weight')
            if req['largeValue']:
                style = {stock_style: float(req[stock_style]) for stock_style in list(req.keys())[2:]}
            else:
                style = {}
        elif asset_type == 'Stock':
            site_id = get_site_id(id)
            url = f'https://www.morningstar.com/stocks/{site_id}/quote'
            req = requests.get(url)
            
            page = html.fromstring(req.content)
            data = page.xpath("//script/text()")[0]
            pos = data.find('sector:{value')
            sector = data[pos:pos+40].split('"')[1]
            pos = data.find('headquarterCountry:{value')
            country = data[pos:pos+100].split('"')[1]
            name = page.xpath("//span[@itemprop='name']/text()")[0]
            
            countries = {country[0].lower()+ country[1:].replace(' ',''): 100}
            regions = {}
            sectors = {sector[0].lower()+ sector[1:].replace(' ',''): 100}
            holdings = {name: 100}
            holdings_types = {name: {'sector': sector, 'country':country}}

            style = {}

        composition = {'countries':countries, 'regions':regions, 'sectors':sectors, 'holdings':holdings, 'holdings_types':holdings_types, 'styles':style}
        
        return composition