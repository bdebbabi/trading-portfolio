from pyotp import *
import base64
import re
import pandas as pd
from time import sleep 
import json
import requests
import numpy as np
from datetime import date, datetime

class webparser:

    def __init__(self,authentification):
        def dec(param):
            if self.hashed:
                return base64.b64decode(param).decode("utf-8")
            else:
                return param
        
        self.hashed = authentification['HASHED']
        self.username = dec(authentification['USERNAME'])
        self.password = dec(authentification['PASSWORD'])
        self.key = dec(authentification['KEY'])
        
        self.headers = {'Content-Type': 'application/json'}
        self.login()

    def login(self):

        if self.key:
            totp = TOTP(self.key)
            token = totp.now()

            data = json.dumps({"username":self.username,"password":self.password,"oneTimePassword":token})
            url = 'https://trader.degiro.nl/login/secure/login/totp'

        else:
            data = json.dumps({"username":self.username,"password":self.password})
            url = 'https://trader.degiro.nl/login/secure/login'

        self.session = requests.Session()
        response = self.session.post(url,headers=self.headers,data=data)
        self.sessionID = response.cookies["JSESSIONID"]
        
        url = f'https://trader.degiro.nl/pa/secure/client?sessionId={self.sessionID}'
        client_info = self.session.get(url)
        self.userToken = json.loads(client_info.text)['data']['id']
        self.account = json.loads(client_info.text)['data']['intAccount']

    def get_session_ID(self):
        return self.sessionID

    def get_account_ID(self):
        return self.account

    def get_stock_info(self,stock_id):
        session = requests.Session()
        resolution = 'PT1S' 
        period = 'P1D'
        series = ['issueid%3A' + stock_id, 'price%3Aissueid%3A' + stock_id]
        url = f'''https://charting.vwdservices.com/hchart/v1/deGiro/data.js?
                requestid=1&
                resolution={resolution}&
                culture=fr-FR&
                period={period}&
                series={series[0]}&
                series={series[1]}&
                format=json&
                callback=vwd.hchart.seriesRequestManager.sync_response&
                userToken={self.userToken}&
                tz=Europe%2FAmsterdam'''
        url = ''.join(url.split())
        stock_info = json.loads(session.get(url).text[46:-1])

        keys = ['lastPrice', 'highPrice', 'lowPrice','openPrice', 'absDiff', 'lowPriceP1Y', 'highPriceP1Y', 'previousClosePrice']
        live_stock_info = {key:stock_info['series'][0]['data'][key] for key in keys}
        
        return live_stock_info
    
    def get_last_price(self,stock_id):
        stock_info = self.get_stock_info(stock_id)
        last_price = stock_info['series'][0]['data']['lastPrice']
        
        return last_price

    def get_positions(self):

        url = f'https://trader.degiro.nl/trading/secure/v5/update/{self.account};jsessionid={self.sessionID}'
        portfolio_query = self.session.get(url,params={'portfolio':0})
        portfolio = json.loads(portfolio_query.text)['portfolio']['value']

        portfolio = self._add_positions_details(portfolio)
        positions = self._clean_positions(portfolio)
        return positions
    
    def _add_positions_details(self,portfolio):
        products = {}
        live_stock_info = []
        for product in portfolio:
            url = f'https://trader.degiro.nl/product_search/secure/v5/products/info?intAccount={self.account}&sessionId={self.sessionID}'
            res = self.session.post(url,headers=self.headers,data='["'+product["id"]+'"]')
            product_data = json.loads(res.text)['data'][product["id"]]
            product_value = {p['name']: p['value'] if 'value' in p.keys() else None for p in product['value']}
            product_value = {key:value['EUR'] if isinstance(value, dict) else value for key, value in product_value.items()}
            if product_value['positionType'] == 'PRODUCT':
                if 'vwdId' in product_data.keys():    
                    stock_info = self.get_stock_info(product_data['vwdId'])
                    last_price = stock_info['lastPrice']
                else:
                    product_data['closePrice'] = 0 if 'closePrice' not in product_data.keys() else product_data['closePrice']
                    stock_info = {}
                    last_price = 0

                product_value['price'] = last_price
                product_value['value'] = last_price * product_value['size']
                
                products[product_data['name']] = product_value
                products[product_data['name']].update(product_data)
                
                for v in ['name', 'size', 'plBase', 'value']:
                    stock_info[v] = product_value[v]
                
                live_stock_info.append(stock_info)
        self.products = products
        return products

    def _clean_positions(self, positions):
        keys = ['name', 'value','isin', 'size', 'closePrice', 'currency','plBase','realizedProductPl', 'averageFxRate']
        
        positions = pd.DataFrame([[value[k] for k in keys] for value in positions.values()], columns=keys)
        positions['value'] = positions['value'] * positions['averageFxRate']
        positions['value'] = positions['value'].round(2) 
        positions['Gains'] = (positions['value'] + positions['plBase']).round(2) 
        positions['Gains (%)'] = (positions['Gains'] / (-positions['plBase'])).round(2)
        positions['Gains without fees'] = (positions['Gains'] - positions['realizedProductPl']).round(2) 
        positions['Gains without fees (%)'] = (100*positions['Gains without fees'] / (-positions['plBase'])).round(2)
        positions['name'] = positions['name'].str.upper().str.replace(' +',' ').str[:31]
        positions.loc[positions['name'].str.len()==31, 'name'] = positions['name'].str.ljust(34,'.')
        positions['Date'] = pd.to_datetime(date.today())
        positions = positions.drop(columns=['plBase', 'realizedProductPl', 'averageFxRate'])
        
        positions = positions.rename(columns={'name':'Produit', 'value':'Amount','isin':'Ticker/ISIN', 'size':'Quantité', 'closePrice':'Clôture', 'currency':'Devise'})
        # sum = positions[positions['Amount']!=0].sum()
        sum = positions.sum()
        _, _, _, cash, _, total_non_product_fees = self.get_account_summary()
        total_row = {'Produit':'Total',
                     'Amount': round(sum['Amount'], 2), 
                     'Gains without fees': round(sum['Gains without fees']+total_non_product_fees, 2), 
                     'Gains': round(sum['Gains']+total_non_product_fees,2), 
                     'Date': positions.iloc[0]['Date'], 
                     'Gains (%)': round((sum['Gains']/(sum['Amount'] - sum['Gains'])), 2), 
                     'Gains without fees (%)': round((sum['Gains without fees']/(sum['Amount'] - sum['Gains without fees']) * 100), 2) 
                     }
        positions = positions.append(total_row, ignore_index=True)
        positions = positions.append({'Produit':'Cash', 'Amount':cash, 'Date':positions.iloc[0]['Date']}, ignore_index=True)
        return positions


    def get_account_summary(self):
        url = f'https://trader.degiro.nl/trading/secure/v5/update/{self.account};jsessionid={self.sessionID}'
        totalPortfolio = self.session.get(url, params={'totalPortfolio':0})
        totalPortfolio = {p['name']: p['value'] if 'value' in p.keys() else None \
                            for p in json.loads(totalPortfolio.text)['totalPortfolio']['value']}    
        
        cash = totalPortfolio['totalCash']
        cash_fund_compensation = totalPortfolio['cashFundCompensation']
        cash_fund_compensation_withdrawn = totalPortfolio['cashFundCompensationWithdrawn']
        cash_fund_compensation_pending = totalPortfolio['cashFundCompensationPending']
        total_non_product_fees = totalPortfolio['totalNonProductFees']
        
        buy = np.array([value['plBase'] for product, value in self.products.items()]).sum()
        portfolio_without_cash = np.array([value['value']*value['averageFxRate'] 
                                            for product, value in self.products.items()]).sum() + cash_fund_compensation
        gains = portfolio_without_cash + buy + total_non_product_fees - cash_fund_compensation
        total = portfolio_without_cash + cash
        
        return total, portfolio_without_cash, cash_fund_compensation, cash, gains, total_non_product_fees 
    
