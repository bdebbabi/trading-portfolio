import pandas as pd
import numpy as np 
import datetime
from datetime import date, timedelta
from urllib.request import urlopen, Request
import requests
from io import StringIO
import plotly.graph_objects as go
import os.path 

from datetime import datetime as dt
import re
import plotly.express as px
import dash_table
from tqdm import tqdm 

from parser import *

CREATION_DATE = date(2020, 1, 9)
def add_sign(item):
    return str(item) if item <=0 else '+' + str(item)

def color_formatting(value):
    return {'if': {'filter_query': f'{{value}} contains "-"','column_id': value},'color': 'red'},\
    {'if': {'filter_query': f'{{value}} contains "+"','column_id': value},'color': 'green'}
    
def get_day_portfolio(portfolio, day):
    day_portfolio = portfolio[portfolio['Date']==day]
    return day_portfolio

def summary(portfolio, day=date.today(), live_data=None):
    def get_cash(portfolio):
        return portfolio[portfolio['Produit']== 'CASH & CASH FUND (EUR)']['Amount'].values[0]
        
    def get_total(portfolio, cash):
        return portfolio[portfolio['Produit']== 'Total']['Amount'].values[0] + cash


    if portfolio['Date'].isin([pd.to_datetime(day, format='%Y-%m-%d')]).any():
        day = pd.to_datetime(day, format='%Y-%m-%d')
    else:
        day = pd.to_datetime(portfolio['Date'].iloc[-1], format='%d-%m-%Y')

    account = pd.read_csv('account.csv', index_col=0)
    # portfolio = pd.read_csv('portfolio_records.csv', index_col=0)

    account['Date'] = pd.to_datetime(account['Date'], format='%d-%m-%Y')
    portfolio['Date'] = pd.to_datetime(portfolio['Date'], format='%d-%m-%Y')

    account = account[account['Date'] <= day ]
    portfolio = portfolio[portfolio['Date'] <= day]

    #original_dividend =  account[account['Description']=='Dividende']['Mouvements'].sum()
    converted_dividend =  account[(account['Description']=='Opération de change - Débit') & (account['Mouvements']>0)]['Mouvements'].sum()
    FM =  account[account['Description']=='Variation Fonds Monétaires (EUR)']['Mouvements'].sum()
    achats = account[account['Description'].str[0:5]=='Achat']['Mouvements'].sum()
    total_non_product_fees = account[account['Description'].str[0:40]=='Frais de connexion aux places boursières']['Mouvements'].sum()
    brokerage_fees = account[account['Description']=='Frais de courtage']['Mouvements'].sum()
    deposit = account[account['Description']=='Versement de fonds']['Mouvements'].sum()
    
    # last_date = portfolio.iloc[-1,]['Date']
    
    cash_fund_compensation = -FM
    previous_last_portfolio = get_day_portfolio(portfolio, day - timedelta(days=1))
    if day == pd.to_datetime(date.today(), format='%Y-%m-%d') and live_data:
        total, portfolio_without_cash, cash_fund_compensation, cash, gains, total_non_product_fees = live_data
    else:
        last_portfolio = get_day_portfolio(portfolio, day)
        cash = get_cash(last_portfolio)
        total = get_total(last_portfolio, cash)
        portfolio_without_cash = last_portfolio[~last_portfolio['Produit'].isin(['CASH & CASH FUND (EUR)', 'Total', 'CASH & CASH FUND (USD)'])]['Amount'].sum() + cash_fund_compensation
        gains = total - deposit
    
    previous_total = get_total(previous_last_portfolio, get_cash(previous_last_portfolio))
    previous_account = account[account['Date'] <= day - timedelta(days=1) ]
    previous_deposit = previous_account[previous_account['Description']=='Versement de fonds']['Mouvements'].sum()
    previous_gains = previous_total - previous_deposit
    daily_gains = gains - previous_gains     
    
    gains_p = add_sign(round(100*gains/(-achats),2))
    daily_gains_p = add_sign(round(100*daily_gains/previous_gains,2))

    gains = '€ ' + str(round(gains,2)) + ' (' + gains_p + ' %)'
    daily_gains = '€ ' + str(round(daily_gains,2)) + ' (' + daily_gains_p + ' %)'

    values = [portfolio_without_cash, gains,daily_gains,converted_dividend, cash,achats,brokerage_fees,total_non_product_fees,cash_fund_compensation]
    for i, value in enumerate(values):
        if not isinstance(value, str):
            values[i] ='€ ' + str(round(value, 2))
    names = ['Portfolio', 'Total gains','Daily gains','Dividend', 'Cash', 'Buy','Brokerage fees' ,'Total non product fees', 'Monetary funds refund']
    
    
    table_content = [{'name': name,'value': value} for name, value in zip(names, values)]

    table = dash_table.DataTable(data=table_content, 
                               id = 'summary_table',
                               columns=[{'name':'name', 'id':'name'}, {'name':'value', 'id':'value'}], 
                               style_cell={'textAlign': 'left', 'maxWidth': 20}, 
                               style_as_list_view=True,
                               style_data_conditional=[{'if': {'row_index': [1,2,3,5,6]},'border-bottom': '3px'},
                                                        {'if': {'filter_query': '{value} contains "-" && {value} contains "("','column_id': 'value'},
                                                        'color': 'red'},
                                                        {'if': {'filter_query': '{value} contains "+" && {value} contains "("','column_id': 'value'},
                                                        'color': 'green'}],
                                style_cell_conditional=[{'if': {'column_id': 'value'},'width': '20%'},],
                                style_header={'display':'none'}
                                )
    return table, table.data, table.columns

def positions_summary(live_stock_info):
    def cell_color(column, condition, color):
        return {'if': {'filter_query': f'{{{column}}} contains "{condition}"','column_id': column},'color': color}
    
    for stock in live_stock_info:
        for key, value in stock.items():
            if key not in ['Size', 'Position', 'Gains']:
                stock[key] = round(value*stock['Size'],2)
        variation_p = add_sign(round((100*stock['absDiff'] / stock['previousClosePrice']),2))  
        variation = add_sign(stock['absDiff'])  
        stock['Daily gains'] = variation + ' ('+ variation_p + ' %)' 

    table = dash_table.DataTable(data=live_stock_info, 
                               id = 'positions_summary_table',
                               columns=[{'name':'Postion', 'id':'Position'},
                                        {'name':'Last', 'id':'lastPrice'}, 
                                        {'name':'Daily gains', 'id':'Daily gains'}, 
                                        {'name':'Total gains', 'id':'Gains'}, 
                                        {'name':'Low', 'id':'lowPrice'},
                                        {'name':'High', 'id':'highPrice'}, 
                                        {'name':'1 year low', 'id':'lowPriceP1Y'}, 
                                        {'name':'1 year high', 'id':'highPriceP1Y'}, 
                                        {'name':'Quantity', 'id':'Size'}, 
                                    ], 
                               style_cell={'textAlign': 'left'}, 
                               style_as_list_view=True,
                               style_data_conditional=[cell_color('Gains', '-', 'red'),
                                                        cell_color('Gains', '+', 'green'),
                                                        cell_color('Daily gains', '-', 'red'),
                                                        cell_color('Daily gains', '+', 'green')],
                               
                                )
    return table, table.data, table.columns

def retrieve_portfolio_record(sessionID, start_date=CREATION_DATE, end_date=date.today()):
    delta = end_date - start_date
    days = [start_date + timedelta(days=i) for i in range(delta.days + 1)]
    columns = ['Produit', 'Ticker/ISIN', 'Quantité', 'Clôture', 'Devise', 'Montant en EUR']

    portfolio = pd.DataFrame()
    for day in tqdm(days):
        link = f"""https://trader.degiro.nl/reporting/secure/v3/positionReport/csv
                ?intAccount=11034964
                &sessionId={sessionID}
                &country=FR
                &lang=fr
                &toDate={day.strftime('%d')}%2F{day.strftime('%m')}%2F{day.strftime('%Y')}
                """

        link = ''.join(link.split())
        record = StringIO(urlopen(Request(link)).read().decode('utf-8'))

        df = pd.read_csv(record, sep=',', names=columns)
        df['Date'] = day.strftime('%d-%m-%Y')
        portfolio = portfolio.append(df.iloc[1:,])

    portfolio = portfolio.reset_index(drop=True)
    
    portfolio['Devise'] = portfolio['Devise'].str[4:].astype(float)
    portfolio['Montant en EUR'] = portfolio['Montant en EUR'].str.replace(',','.').astype(float)

    portfolio['Produit'] = portfolio['Produit'].str.replace('\s+', ' ')

    return portfolio


def update_portfolio_record(sessionID, start_date='last', end_date=date.today()+timedelta(days=-1)):
    
    if os.path.isfile('portfolio_records.csv'):
        portfolio = pd.read_csv('portfolio_records.csv', index_col=0)
    else:
        columns = ['Produit', 'Ticker/ISIN', 'Quantité', 'Clôture', 'Devise', 'Montant en EUR','Date']
        portfolio = pd.DataFrame(columns=columns)
        start_date=CREATION_DATE

    if start_date == 'last':
        start_date = datetime.strptime(portfolio.iloc[-1,]['Date'], '%d-%m-%Y') 
        start_date = date(start_date.year, start_date.month, start_date.day)
    
    if start_date <= end_date:
        new_portfolio = retrieve_portfolio_record(sessionID, start_date, end_date)
    
        delta = end_date - start_date
        days = [(start_date + timedelta(days=i)).strftime('%d-%m-%Y') for i in range(delta.days + 1)]

        portfolio = portfolio.drop(portfolio[portfolio['Date'].isin(days)].index, axis=0)
        portfolio = portfolio.append(new_portfolio)   
        portfolio = portfolio.reset_index(drop=True)
        portfolio.to_csv('portfolio_records.csv')

        print(f'retrieved from start date: {start_date} to end date: {end_date}')

    elif start_date > end_date:
        print(f'start date: {start_date} bigger than end date: {end_date}')


def retrieve_account_records(sessionID, start_date=CREATION_DATE, end_date=date.today()):
    link = f"""https://trader.degiro.nl/reporting/secure/v3/cashAccountReport/csv
            ?intAccount=11034964
            &sessionId={sessionID}
            &country=FR
            &lang=fr
            &fromDate={start_date.strftime('%d')}%2F{start_date.strftime('%m')}%2F{start_date.strftime('%Y')}
            &toDate={end_date.strftime('%d')}%2F{end_date.strftime('%m')}%2F{end_date.strftime('%Y')}
            """
    link = ''.join(link.split())
    record = StringIO(urlopen(Request(link)).read().decode('utf-8'))

    account = pd.read_csv(record, sep=',')

    account = account.drop(['Mouvements', 'FX', 'Solde','ID Ordre'], axis=1)
    account = account.rename(columns={'Unnamed: 8': 'Mouvements', 'Unnamed: 10': 'Solde'})
    account = account.drop(account[account['Mouvements'].isin(['-0,00','0,00',np.NaN])].index, axis=0)
    account['Mouvements'] = account['Mouvements'].str.replace(',','.').astype(float)
    account['Solde'] = account['Solde'].str.replace(',','.').astype(float)

    account.to_csv('account.csv')


def add_gains_and_total():
    portfolio = pd.read_csv('portfolio_records.csv', index_col=0)
    portfolio['Date'] = pd.to_datetime(portfolio['Date'], format='%d-%m-%Y')
    cash = portfolio[portfolio['Produit'].isin(['CASH & CASH FUND (EUR)','CASH & CASH FUND (USD)'])]
    portfolio = portfolio.drop(portfolio[portfolio['Produit'].isin(['CASH & CASH FUND (EUR)','CASH & CASH FUND (USD)'])].index, axis=0)

    account = pd.read_csv('account.csv', index_col=0)
    account['Date'] = pd.to_datetime(account['Date'], format='%d-%m-%Y')

    expenses=[]
    buys=[]

    for _, p in portfolio.iterrows():
            expenses.append(account[(account['Date'] <= pd.to_datetime(p['Date'], format='%d-%m-%Y')) 
                    & (account['Code ISIN']==p['Ticker/ISIN'])]['Mouvements'].sum())

            buys.append(account[(account['Date'] <= pd.to_datetime(p['Date'], format='%d-%m-%Y')) 
                    & (account['Code ISIN']==p['Ticker/ISIN'])
                    & (account['Description'].str[0:5]=='Achat')]['Mouvements'].sum())
    
    portfolio['Gains'] = expenses + portfolio['Montant en EUR']
    portfolio['Gains without fees'] = buys + portfolio['Montant en EUR']


    gains = []
    gains_without_fees = []
    portfolio_amount = []

    for day in portfolio['Date'].unique():
            gains.append(portfolio[portfolio['Date'] == day ]['Gains'].sum())
            gains_without_fees.append(portfolio[portfolio['Date'] == day]['Gains without fees'].sum())
            portfolio_amount.append(portfolio[portfolio['Date'] == day]['Montant en EUR'].sum())

    total_gains = pd.DataFrame([['Total',d,g,gf,a] for d,g,gf,a in zip(portfolio['Date'].dt.strftime('%Y-%m-%d').unique().tolist(), 
                                                                    gains, 
                                                                    gains_without_fees,
                                                                    portfolio_amount)], 
                                columns=['Produit','Date','Gains', 'Gains without fees', 'Montant en EUR'])
    
    total_gains['Date'] = pd.to_datetime(total_gains['Date'], format='%Y-%m-%d')
    portfolio = pd.concat([total_gains, portfolio])

    portfolio['Gains'] = portfolio['Gains'].round(2) 
    portfolio['Gains without fees'] = portfolio['Gains without fees'].round(2) 

    portfolio['Gains (%)'] = (portfolio['Gains']/(portfolio['Montant en EUR'] - portfolio['Gains'])).round(2)
    portfolio['Gains without fees (%)'] = (portfolio['Gains without fees']/(portfolio['Montant en EUR'] - portfolio['Gains without fees']) * 100).round(2)

    portfolio['Complete gains'] = portfolio['Gains'].astype(str) + ' € (' + portfolio['Gains (%)'].astype(str) + ' %)'
    portfolio['Complete gains without fees'] = portfolio['Gains without fees'].astype(str) + ' € (' + portfolio['Gains without fees (%)'].astype(str) + ' %)'
    
    portfolio = pd.concat((portfolio, cash))

    portfolio = portfolio.rename(columns={'Montant en EUR':'Amount'})
    portfolio = portfolio.reset_index()

    return portfolio

def add_gains_variation(portfolio):
    portfolio['Gains variation'] = 0
    for product in portfolio['Produit'].unique():
        if product not in ['CASH & CASH FUND (EUR)','CASH & CASH FUND (USD)']:
            p = portfolio[portfolio['Produit'] == product]
            portfolio.loc[p.index,'Gains variation'] = np.array(p['Gains'] - p.shift(periods=1, fill_value=0)['Gains']).round(2)

    return portfolio

def portfolio_variation(metric, portfolio):

    if metric == 'Gains':
        hover_data = ['Gains without fees', 'Gains variation'] 
        title = 'Gains (without connexion fees)'
        tickformat = '€'


    elif metric == 'Gains (%)':
        hover_data = ['Gains without fees (%)', 'Gains variation'] 
        title = 'Gains % (without connexion fees)'
        tickformat = '%'
    else:
        hover_data = [] 
        title = metric 
        tickformat = '€'
    portfolio = portfolio.reset_index(drop=True)

    fig = px.line(portfolio.drop(portfolio[portfolio['Produit'].isin(['CASH & CASH FUND (EUR)','CASH & CASH FUND (USD)'])].index, axis=0),
                    x='Date', y=metric, color='Produit', color_discrete_map={'Total':'black'}, hover_data=hover_data,
                    labels={'Produit':'Product'}, title=title, height=700 )

    fig.update_layout(
            yaxis_tickformat = tickformat,
            xaxis=dict(
                rangeselector=dict(
                    buttons=list([
                        dict(count=1,
                            label="1m",
                            step="month",
                            stepmode="backward"),
                        dict(count=3,
                            label="3m",
                            step="month",
                            stepmode="backward"),
                        dict(count=6,
                            label="6m",
                            step="month",
                            stepmode="backward"),
                        dict(count=1,
                            label="YTD",
                            step="year",
                            stepmode="todate"),
                        dict(count=1,
                            label="1y",
                            step="year",
                            stepmode="backward"),
                        dict(step="all")
                    ])
                ),
                rangeslider=dict(
                    visible=True
                ),
                type="date"
            )
        )

    return fig

def portfolio_composition(portfolio, day=date.today()):
    # portfolio = portfolio[(portfolio['Date'] == day.strftime('%d-%m-%Y')) & (portfolio['Produit'] != 'CASH & CASH FUND (EUR)')]

    if portfolio['Date'].isin([pd.to_datetime(day, format='%Y-%m-%d')]).any():
        day = pd.to_datetime(day, format='%Y-%m-%d')
    else:
        day = pd.to_datetime(portfolio['Date'].iloc[-1], format='%d-%m-%Y')

    portfolio = get_day_portfolio(portfolio, day)

    fig = px.pie(portfolio.drop(portfolio[portfolio['Produit'].isin(['CASH & CASH FUND (EUR)','CASH & CASH FUND (USD)', 'Total'])].index, axis=0),
                values='Amount', names='Produit', 
                title=f'Portfolio composition {day.strftime("%d-%m-%Y")}',
                hover_data=['Gains variation'],
                labels={'Produit':'Product'})
    # fig.update_layout(showlegend=False)
    # fig.show()
    return fig
    
def update(sessionID):
    if sessionID:
        retrieve_account_records(sessionID=sessionID)
        update_portfolio_record(sessionID=sessionID)
