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
import dash_html_components as html
from tqdm import tqdm 
import copy 
import warnings
from parser import *

TEMPLATE = "plotly_dark"
# TEMPLATE = "plotly"
ACCOUNT_PATH = 'data/account.csv'
PORTFOLIO_PATH = 'data/portfolio_records.csv'
def add_sign(item):
    return str(item) if item <=0 else '+' + str(item)

def color_formatting(value):
    return {'if': {'filter_query': f'{{value}} contains "-"','column_id': value},'color': 'red'},\
    {'if': {'filter_query': f'{{value}} contains "+"','column_id': value},'color': 'green'}
    
def get_day_portfolio(portfolio, day):
    day_portfolio = portfolio[portfolio['Date']==day]
    return day_portfolio

def get_account_data(account):
    deposit = account[account['Description'].isin(['Versement de fonds', 'Dépôt flatex'])]['Mouvements'].sum()
    dividend =  account[(account['Description']=='Opération de change - Débit') & (account['Mouvements']>0)]['Mouvements'].sum()
    dividend = dividend + account[(account['Description']=='Dividende') & (account['Mouvements']!=account['Solde'])]['Mouvements'].sum()
    cash_fund_compensation =  -account[account['Description']=='Variation Fonds Monétaires (EUR)']['Mouvements'].sum()
    warnings.filterwarnings("ignore", 'This pattern has match groups')
    purchases = account[account['Description'].str.contains(r'^Achat ((?!USD).)*$', regex=True)
                    |((account['Description'].str.contains('Opération de change - Débit'))
                    & (account['Code ISIN']))]['Mouvements'].sum()
    flatex_interest = account[account['Description']=='Flatex Interest']['Mouvements'].sum()
    total_non_product_fees = account[account['Description'].str[0:40]=='Frais de connexion aux places boursières']['Mouvements'].sum()
    brokerage_fees = account[account['Description']=='Frais de courtage']['Mouvements'].sum()
    sales = account[account['Description'].str[0:5] == 'Vente']['Mouvements'].sum()

    return deposit, dividend, cash_fund_compensation, purchases, total_non_product_fees, brokerage_fees, sales, flatex_interest


def summary(portfolio, day=date.today(), live_data=None):

    if portfolio['Date'].isin([pd.to_datetime(day, format='%Y-%m-%d')]).any():
        day = pd.to_datetime(day, format='%Y-%m-%d')
    else:
        day = pd.to_datetime(portfolio['Date'].iloc[-1], format='%d-%m-%Y')

    account = pd.read_csv(ACCOUNT_PATH, index_col=0)

    account['Date'] = pd.to_datetime(account['Date'], format='%d-%m-%Y')
    portfolio['Date'] = pd.to_datetime(portfolio['Date'], format='%d-%m-%Y')
    portfolio = portfolio[portfolio['Produit']!='Cash']
    account = account[account['Date'] <= day ]
    portfolio = portfolio[portfolio['Date'] <= day]
    deposit, dividend, cash_fund_compensation, purchases, total_non_product_fees, brokerage_fees, sales, flatex_interest = get_account_data(account)
    if day == pd.to_datetime(date.today(), format='%Y-%m-%d') and live_data:
        total, portfolio_without_cash, cash_fund_compensation, cash, gains, total_non_product_fees = live_data
    else:
        last_portfolio = get_day_portfolio(portfolio, day)
        #Flatex interest
        cash = purchases + dividend + brokerage_fees + sales + total_non_product_fees + deposit + cash_fund_compensation + flatex_interest
        total = last_portfolio[last_portfolio['Produit']== 'Total']['Amount'].values[0] + cash
        portfolio_without_cash = last_portfolio[~last_portfolio['Produit'].isin(['CASH & CASH FUND (EUR)', 'Total', 'CASH & CASH FUND (USD)'])]['Amount'].sum() 
    
    total_portfolio = portfolio[portfolio['Produit']=='Total'].iloc[-1,:]
    portfolio_gains = portfolio[(portfolio['Date'] == day) & (portfolio['Produit']!='Total') & (portfolio['Quantité']!=0)]['Gains'].sum()
    
    total_gains = total_portfolio['Gains']

    #we remove total non product fees because they are added to the total gains 
    # total gains is portfolio gains(already include brokerage fees and dividens) + sales gains + non product fees   
    sales_gains = total_gains - portfolio_gains-total_non_product_fees

    daily_gains = total_portfolio['Gains variation']


    total_gains_p = add_sign(round(100*total_gains/(total_portfolio['Amount']),2))
    daily_gains_p = add_sign(round(100*daily_gains/(portfolio_gains),2))

    total_gains = '€ ' + str(round(total_gains,2)) + ' (' + total_gains_p + ' %)'
    daily_gains = '€ ' + str(round(daily_gains,2)) + ' (' + daily_gains_p + ' %)'

    values = [portfolio_without_cash, total_gains,daily_gains, portfolio_gains, sales_gains, dividend, sales, cash,purchases,brokerage_fees,total_non_product_fees,cash_fund_compensation, flatex_interest]
    for i, value in enumerate(values):
        if not isinstance(value, str):
            values[i] ='€ ' + str(round(value, 2))
    names = ['Portfolio', 'Total gains','Daily gains', 'Portfolio gains', 'Sales gains', 'Dividend', 'Sales', 'Cash', 'Purchases','Brokerage fees' ,'Total non product fees', 'Monetary funds refund', 'Flatex interest']
    
    
    table_content = [{'name': name,'value': value} for name, value in zip(names, values)]

    table = dash_table.DataTable(data=table_content, 
                               id = 'summary_table',
                               columns=[{'name':'name', 'id':'name'}, {'name':'value', 'id':'value'}], 
                               style_cell={'textAlign': 'left', 'backgroundColor': 'rgb(17, 17, 17)', 'color': 'white'}, 
                               style_as_list_view=True,
                               style_data_conditional=[
                                                        {'if': {'filter_query': '{value} contains "-" && {value} contains "("','column_id': 'value'},
                                                        'color': 'red'},
                                                        {'if': {'filter_query': '{value} contains "+" && {value} contains "("','column_id': 'value'},
                                                        'color': 'green'}],
                                style_cell_conditional=[{'if': {'column_id': 'value'},'width': '20%'},],
                                style_header={'display':'none'},
                                )
    return table, table.data, table.columns

def positions_summary(portfolio, day=date.today()):
    def cell_color(column, condition, color):
        return {'if': {'filter_query': f'{{{column}}} contains "{condition}"','column_id': column},'color': color}
    
    if portfolio['Date'].isin([pd.to_datetime(day, format='%Y-%m-%d')]).any():
        day = pd.to_datetime(day, format='%Y-%m-%d')
    else:
        day = pd.to_datetime(portfolio['Date'].iloc[-1], format='%d-%m-%Y')

    stock_info = []
    portfolio = portfolio[portfolio['Produit']!='Cash']

    day_portfolio = portfolio[portfolio['Date']==day].sort_values(by=['Produit'])
    for _, p in day_portfolio.iterrows():
        if p['Produit'] not in ['Total', 'CASH & CASH FUND (EUR)'] and p['Quantité'] != 0:
            stock = {}
            stock['name'] = p['Produit']
            stock['lastPrice'] = '€ ' + str(p['Amount'])
            if p['Amount'] - p['Gains variation'] != 0:
                variation_p = add_sign(round(100 * p['Gains variation'] / (p['Amount'] - p['Gains variation']),2))
            else:
                variation_p = '0.0'
            stock['Daily gains'] = '€ ' + add_sign(p['Gains variation']) + ' (' + variation_p + ' %)' 
            stock['Gains'] = '€ ' + add_sign(p['Gains']) + ' (' +  add_sign(round(100*p['Gains (%)'],2)) + ' %)'
            stock['size'] = p['Quantité']
            stock_info.append(stock)    

    table = dash_table.DataTable(data=stock_info, 
                            id = 'positions_summary_table',
                            columns=[{'name':'Position', 'id':'name'},
                                        {'name':'Price', 'id':'lastPrice'}, 
                                        {'name':'Daily gains + dividends', 'id':'Daily gains'}, 
                                        {'name':'Total gains + dividends', 'id':'Gains'}, 
                                        # {'name':'Low', 'id':'lowPrice'},
                                        # {'name':'High', 'id':'highPrice'}, 
                                        # {'name':'1 year low', 'id':'lowPriceP1Y'}, 
                                        # {'name':'1 year high', 'id':'highPriceP1Y'}, 
                                        {'name':'Quantity', 'id':'size'}, 
                                    ], 
                            style_cell={'textAlign': 'left', 'backgroundColor': 'rgb(17, 17, 17)', 'color': 'white'}, 
                            style_as_list_view=True,
                            style_data_conditional=[cell_color('Gains', '-', 'red'),
                                                        cell_color('Gains', '+', 'green'),
                                                        cell_color('Daily gains', '-', 'red'),
                                                        cell_color('Daily gains', '+', 'green')],
                            
                                )
    return table, table.data, table.columns
    
def dividends(day=date.today()):

    account = pd.read_csv(ACCOUNT_PATH, index_col=0)
    day = pd.to_datetime(day, format='%Y-%m-%d')

    account['Date'] = pd.to_datetime(account['Date'], format='%d-%m-%Y')
    account['Date de'] = pd.to_datetime(account['Date de'], format='%d-%m-%Y')
    account = account[account['Date'] <= day ]

    account['Produit'] = account['Produit'].str[:31].str.upper().str.replace(' +',' ')
    account.loc[account['Produit'].str.len()==31, 'Produit'] = account['Produit'].str.ljust(34,'.')

    change = account[(account['Description']=='Opération de change - Débit') & (account['Mouvements']>0)]

    dividends = account[(account['Description']=='Dividende') & 
            (account['Mouvements']==account['Solde']) & 
            (account['Date'] <= change['Date de'].max())]

    dividends = dividends.reset_index(drop=True)
    dividends['Mouvements US'] = dividends['Mouvements']
    dividends['Mouvements'] = list(change['Mouvements'])

    dividends = pd.concat((dividends,account[(account['Description']=='Dividende') & (account['Mouvements']!=account['Solde'])]))

    grouped_dividends = dividends.groupby(by='Produit').sum()

    numbers = dividends['Produit'].value_counts()
    grouped_dividends['Number'] = numbers

    grouped_dividends = grouped_dividends.sort_values(by='Produit')

    last_dates = dividends.drop_duplicates(subset='Produit', keep='first').sort_values(by='Produit')['Date de']
    grouped_dividends['Last date'] = list(last_dates)

    grouped_dividends = grouped_dividends.drop(columns=['Solde'])
    grouped_dividends['Mouvements US'] = grouped_dividends['Mouvements US'].round(2)

    grouped_dividends['Mouvements'] = '€ ' + grouped_dividends['Mouvements'].round(2).astype(str)
    grouped_dividends['Mouvements US'] = '$ ' + grouped_dividends['Mouvements US'].astype(str).replace('0.0', '-')

    grouped_dividends = grouped_dividends.sort_values(by='Last date', ascending=False)
    grouped_dividends['Last date'] = grouped_dividends['Last date'].astype(str)

    table = dash_table.DataTable(data=grouped_dividends.reset_index().to_dict('records'), 
                                id = 'dividends_table',
                                columns=[{'name':'Position', 'id':'Produit'},
                                        {'name':'Dividends €', 'id':'Mouvements'},
                                        {'name':'Dividends $', 'id':'Mouvements US'}, 
                                        {'name':'Quantity', 'id':'Number'}, 
                                        {'name':'Last dividend', 'id':'Last date'}
                                        ], 
                                style_cell={'textAlign': 'left', 'backgroundColor': 'rgb(17, 17, 17)', 'color': 'white'}, 
                                style_as_list_view=True
                                    )
    return table, table.data, table.columns

def closed_positions(portfolio, day=date.today()):
    def cell_color(column, condition, color):
        return {'if': {'filter_query': f'{{{column}}} contains "{condition}"','column_id': column},'color': color}
    
    if portfolio['Date'].isin([pd.to_datetime(day, format='%Y-%m-%d')]).any():
        day = pd.to_datetime(day, format='%Y-%m-%d')
    else:
        day = pd.to_datetime(portfolio['Date'].iloc[-1], format='%d-%m-%Y')

    stock_info = []
    day_portfolio = portfolio[portfolio['Date']==day].sort_values(by=['Produit'])
    for _, p in day_portfolio.iterrows():
        if p['Produit'] not in ['Total', 'CASH & CASH FUND (EUR)'] and p['Quantité'] == 0:
            stock = {}
            stock['name'] = p['Produit']
            stock['Gains'] = '€ ' + add_sign(p['Gains']) 
            stock_info.append(stock)    

    table = dash_table.DataTable(data=stock_info, 
                            id = 'closed_positions_table',
                            columns=[{'name':'Position', 'id':'name'},
                                        {'name':'Total gains', 'id':'Gains'}, 
                                    ], 
                            style_cell={'textAlign': 'left', 'backgroundColor': 'rgb(17, 17, 17)', 'color': 'white'}, 
                            style_as_list_view=True,
                            style_data_conditional=[cell_color('Gains', '-', 'red'),
                                                        cell_color('Gains', '+', 'green')],
                            
                                )
    return table, table.data, table.columns

def retrieve_portfolio_record(sessionID, accountID, start_date, end_date=date.today()):
    delta = end_date - start_date
    days = [start_date + timedelta(days=i) for i in range(delta.days + 1)]
    columns = ['Produit', 'Ticker/ISIN', 'Quantité', 'Clôture', 'Devise', 'Montant en EUR']

    portfolio = pd.DataFrame()
    for day in days:
        link = f"""https://trader.degiro.nl/reporting/secure/v3/positionReport/csv
                ?intAccount={accountID}
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


def update_portfolio_record(sessionID, accountID, creation_date, start_date='last', end_date=date.today()+timedelta(days=-1)):
    
    if os.path.isfile(PORTFOLIO_PATH):
        portfolio = pd.read_csv(PORTFOLIO_PATH, index_col=0)
    else:
        columns = ['Produit', 'Ticker/ISIN', 'Quantité', 'Clôture', 'Devise', 'Montant en EUR','Date']
        portfolio = pd.DataFrame(columns=columns)
        start_date=creation_date

    if start_date == 'last':
        start_date = datetime.strptime(portfolio.iloc[-1,]['Date'], '%d-%m-%Y') 
        start_date = date(start_date.year, start_date.month, start_date.day)
    
    if start_date <= end_date:
        new_portfolio = retrieve_portfolio_record(sessionID, accountID, start_date, end_date)
    
        delta = end_date - start_date
        days = [(start_date + timedelta(days=i)).strftime('%d-%m-%Y') for i in range(delta.days + 1)]

        portfolio = portfolio.drop(portfolio[portfolio['Date'].isin(days)].index, axis=0)
        portfolio = portfolio.append(new_portfolio)   
        portfolio = portfolio.reset_index(drop=True)
        portfolio.to_csv(PORTFOLIO_PATH)

        if start_date == end_date:
            print(f'retrieved {start_date} portfolio')
        else:
            print(f'retrieved portfolios from {start_date} to {end_date}')

    elif start_date > end_date:
        print(f'start date: {start_date} bigger than end date: {end_date}')


def retrieve_account_records(sessionID, accountID, start_date, end_date=date.today()):
    link = f"""https://trader.degiro.nl/reporting/secure/v3/cashAccountReport/csv
            ?intAccount={accountID}
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

    if not os.path.isdir('data'):
        os.makedirs('data')
    account.to_csv(ACCOUNT_PATH)


def add_gains_and_total():
    def get_total_gains_and_cash(account, portfolio):
        deposit, dividend, cash_fund_compensation, purchases, total_non_product_fees, brokerage_fees, sales, flatex_interest = get_account_data(account)
        portfolio_total = portfolio[~portfolio['Produit'].isin(['CASH & CASH FUND (EUR)', 'Total', 'CASH & CASH FUND (USD)'])]['Montant en EUR'].sum() 
        cash = purchases + dividend + brokerage_fees + sales + total_non_product_fees + deposit + cash_fund_compensation + flatex_interest
        return portfolio_total+cash -deposit, cash
    portfolio = pd.read_csv(PORTFOLIO_PATH, index_col=0)
    portfolio['Date'] = pd.to_datetime(portfolio['Date'], format='%d-%m-%Y')
    cash = portfolio[portfolio['Produit'].isin(['CASH & CASH FUND (EUR)','CASH & CASH FUND (USD)'])]
    portfolio = portfolio.drop(portfolio[portfolio['Produit'].isin(['CASH & CASH FUND (EUR)','CASH & CASH FUND (USD)'])].index, axis=0)

    account = pd.read_csv(ACCOUNT_PATH, index_col=0)
    account['Date'] = pd.to_datetime(account['Date'], format='%d-%m-%Y')

    expenses=[]
    buys=[]

    for _, p in portfolio.iterrows():
            expenses.append(account[(account['Date'] <= pd.to_datetime(p['Date'], format='%d-%m-%Y')) 
                                  & (account['Code ISIN']==p['Ticker/ISIN'])]['Mouvements'].sum())

            
            buys.append(account[(account['Date'] <= pd.to_datetime(p['Date'], format='%d-%m-%Y')) 
                              & (account['Code ISIN']==p['Ticker/ISIN'])
                              & ((account['Description'].str.contains('Achat.* EUR \(', regex=True) 
                              | (account['Description'].str.contains('Opération de change - Débit'))))]['Mouvements'].sum())
            
    portfolio['Gains'] = expenses + portfolio['Montant en EUR']
    portfolio['Gains without fees'] = buys + portfolio['Montant en EUR']


    gains = []
    gains_without_fees = []
    portfolio_amount = []
    complete_gains = []
    actual_cash = []
    for day in portfolio['Date'].unique():
        day_gain, day_cash = get_total_gains_and_cash(account[account['Date'] <= day ], portfolio[portfolio['Date'] == day])
        complete_gains.append(day_gain)
        actual_cash.append(day_cash)
        gains.append(portfolio[portfolio['Date'] == day ]['Gains'].sum())
        gains_without_fees.append(portfolio[portfolio['Date'] == day]['Gains without fees'].sum())
        portfolio_amount.append(portfolio[portfolio['Date'] == day]['Montant en EUR'].sum())
    
    total_gains = pd.DataFrame([['Total',d,g,gf,a] for d,g,gf,a in zip(portfolio['Date'].dt.strftime('%Y-%m-%d').unique().tolist(), 
                                                                    # gains, 
                                                                    complete_gains, 
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
    
    actual_cash = pd.DataFrame([['Cash',d,round(c,2)] for d,c in zip(portfolio['Date'].dt.strftime('%Y-%m-%d').unique().tolist(),
                                                           actual_cash)], 
                                                           columns=['Produit','Date', 'Montant en EUR'])
    actual_cash['Date'] = pd.to_datetime(actual_cash['Date'], format='%Y-%m-%d')
    portfolio = pd.concat((portfolio, actual_cash))

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
    portfolio = portfolio[portfolio['Quantité']!=0]

    elements = portfolio['Produit'].unique().tolist()[::-1]
    if metric in ['Gains', 'Gains (%)']:
        removals = ['CASH & CASH FUND (EUR)','CASH & CASH FUND (USD)', 'Cash']
        elements = [e for e in elements if e not in removals]

        fig = px.line(portfolio.drop(portfolio[portfolio['Produit'].isin(removals)].index, axis=0),
                    x='Date', y=metric, color='Produit', color_discrete_map={'Total':'white'}, hover_data=hover_data,
                    labels={'Produit':'Product'}, title=title, height=700, category_orders={'Produit':elements}, template=TEMPLATE)
    else:
        removals = ['CASH & CASH FUND (EUR)','CASH & CASH FUND (USD)','Total']
        elements = [e for e in elements if e not in removals]
        elements.remove('Cash')
        elements.append('Cash')
        fig = px.area(portfolio.drop(portfolio[portfolio['Produit'].isin(removals)].index, axis=0),
                    x='Date', y=metric, color='Produit', color_discrete_map={'Total':'white'}, hover_data=hover_data,
                    labels={'Produit':'Product'}, title=title, height=700, line_group='Produit',category_orders={'Produit':elements}, template=TEMPLATE)

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
    portfolio = portfolio[portfolio['Quantité']!=0]
    portfolio = portfolio[portfolio['Produit']!='Cash']

    if portfolio['Date'].isin([pd.to_datetime(day, format='%Y-%m-%d')]).any():
        day = pd.to_datetime(day, format='%Y-%m-%d')
    else:
        day = pd.to_datetime(portfolio['Date'].iloc[-1], format='%d-%m-%Y')

    portfolio = get_day_portfolio(portfolio, day)

    fig = px.pie(portfolio.drop(portfolio[portfolio['Produit'].isin(['CASH & CASH FUND (EUR)','CASH & CASH FUND (USD)', 'Total'])].index, axis=0),
                values='Amount', names='Produit', 
                hover_data=['Gains variation'],
                labels={'Produit':'Product'}, template=TEMPLATE)
    # fig.update_layout(showlegend=False)
    # fig.show()
    return fig
    
def update(sessionID, accountID, creation_date):
    if sessionID and accountID:
        retrieve_account_records(sessionID, accountID, creation_date)
        update_portfolio_record(sessionID, accountID, creation_date)
