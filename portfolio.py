import pandas as pd
import numpy as np 
import datetime
from datetime import date, timedelta
from urllib.request import urlopen, Request
import requests
from io import StringIO
import plotly.graph_objects as go
import argparse
import os.path 

from datetime import datetime as dt
import dash
from dash.dependencies import Input, Output
import dash_html_components as html
import dash_core_components as dcc
import re
import plotly.express as px
import dash_table
from tqdm import tqdm 

from parser import *

CREATION_DATE = date(2020, 1, 9)

def get_last_portfolio(portfolio, day):
    if day == pd.to_datetime(date.today(), format='%Y-%m-%d'):
        last_portfolio = portfolio.drop_duplicates('Produit', 'last')
        last_portfolio = last_portfolio.drop(last_portfolio[~last_portfolio['Produit'].isin(positions['Produit'].unique())].index, axis=0)
    else:
        last_portfolio = portfolio[portfolio['Date']==day]
    return last_portfolio

def summary(portfolio, day=date.today()):
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

    original_dividend =  account[account['Description']=='Dividende']['Mouvements'].sum()
    converted_dividend =  account[(account['Description']=='Opération de change - Débit') & (account['Mouvements']>0)]['Mouvements'].sum()
    FM =  account[account['Description']=='Variation Fonds Monétaires (EUR)']['Mouvements'].sum()
    achats = account[account['Description'].str[0:5]=='Achat']['Mouvements'].sum()
    connexion_fees = account[account['Description'].str[0:40]=='Frais de connexion aux places boursières']['Mouvements'].sum()
    brokerage_fees = account[account['Description']=='Frais de courtage']['Mouvements'].sum()
    deposit = account[account['Description']=='Versement de fonds']['Mouvements'].sum()
    
    # last_date = portfolio.iloc[-1,]['Date']
    

    monetary_funds_refund = MFR if update_portfolio else 0
    
    if day == pd.to_datetime(date.today(), format='%Y-%m-%d'):
        total, portfolio_without_cash, FM, cash, daily_gains, gains = live_data
    else:
        def get_cash(portfolio):
            return portfolio[portfolio['Produit']== 'CASH & CASH FUND (EUR)']['Amount'].values[0]
        
        def get_total(portfolio, cash):
            return portfolio[portfolio['Produit']== 'Total']['Amount'].values[0] + cash

        last_portfolio = get_last_portfolio(portfolio, day)
        previous_last_portfolio = get_last_portfolio(portfolio, day - timedelta(days=1))
        cash = get_cash(last_portfolio)
        total = get_total(last_portfolio, cash)
        portfolio_without_cash = last_portfolio[~last_portfolio['Produit'].isin(['CASH & CASH FUND (EUR)', 'Total', 'CASH & CASH FUND (USD)'])]['Amount'].sum() + monetary_funds_refund
        gains = total - deposit
        
        previous_total = get_total(previous_last_portfolio, get_cash(previous_last_portfolio))
        previous_account = account[account['Date'] <= day - timedelta(days=1) ]
        previous_deposit = previous_account[previous_account['Description']=='Versement de fonds']['Mouvements'].sum()
        previous_gains = previous_total - previous_deposit
        
        daily_gains = gains - previous_gains     

    values = [portfolio_without_cash, gains,converted_dividend, cash,achats,brokerage_fees,connexion_fees,monetary_funds_refund]
    values = ['€ ' + str(round(value, 2))  for value in values]
    names = ['Portfolio', 'Gains','Dividend', 'Cash', 'Buy','Brokerage fees' ,'Connexion fees', 'Monetary funds refund']
    
    daily_gains = '+' + str(round(daily_gains, 2)) if daily_gains >=0 else str(round(daily_gains, 2))
    values[1] = values[1] + ' (' + daily_gains + ')'
    
    table_content = [{'name': name,'value': value} for name, value in zip(names, values)]

    table = dash_table.DataTable(data=table_content, 
                               id = 'summary_table',
                               columns=[{'name':'name', 'id':'name'}, {'name':'value', 'id':'value'}], 
                               style_cell={'textAlign': 'left', 'maxWidth': 20}, 
                               style_as_list_view=True,
                               style_data_conditional=[{'if': {'row_index': [1,2,4,5]},'border-bottom': '3px'}],
                                style_cell_conditional=[{'if': {'column_id': 'value'},'width': '20%'},],
                                style_header={'display':'none'}
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
        start_date = datetime.datetime.strptime(portfolio.iloc[-1,]['Date'], '%d-%m-%Y') 
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

        return portfolio

def portfolio_variation(metric, portfolio):

    if metric == 'Gains':
        hover_data = ['Gains without fees'] 
        title = 'Gains (without connexion fees)'
        tickformat = '€'


    elif metric == 'Gains (%)':
        hover_data = ['Gains without fees (%)'] 
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

    portfolio = get_last_portfolio(portfolio, day)

    fig = px.pie(portfolio.drop(portfolio[portfolio['Produit'].isin(['CASH & CASH FUND (EUR)','CASH & CASH FUND (USD)', 'Total'])].index, axis=0),
                values='Amount', names='Produit', 
                title=f'Portfolio composition {day.strftime("%d-%m-%Y")}',
                hover_data=['Quantité'],
                labels={'Produit':'Product', 'Quantité': 'Quantity' })
    # fig.show()
    return fig
    
def update(sessionID):
    if sessionID:
        retrieve_account_records(sessionID=sessionID)
        update_portfolio_record(sessionID=sessionID)

parser = argparse.ArgumentParser()

parser.add_argument('--update', type=str, help='Whether or not to update the portfolio', default=False)
parser.add_argument('--debug', type=int, help='Debug level', default=0)
parser.add_argument('--live', type=str, help='Live positions', default=False)
parser.add_argument('--mobile', type=str, help='Whether or not to update update portfolio in mobile version', default=False)
FLAGS = parser.parse_args()

update_portfolio = FLAGS.update
debug = FLAGS.debug
live = FLAGS.live
mobile = FLAGS.mobile

if mobile:
    mobile_parser = mobile_parser(debug)
    print('>>updating portfolio')
    sessionID = mobile_parser.get_session_ID()
    update(sessionID)
    
if update_portfolio or live:
    webparser = webparser(debug)
    if update_portfolio:
        print('>>updating portfolio')
        sessionID = webparser.get_session_ID()
        MFR = webparser.get_monetary_funds()
        update(sessionID)

    if live:
        positions = webparser.get_positions()
        live_data = webparser.get_account_summary()

    webparser.quit()    

portfolio = add_gains_and_total()
if live:
    portfolio = pd.concat((portfolio, positions))

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
# initial_day = datetime.datetime.strptime(portfolio['Date'].iloc[-1], '%d-%m-%Y')
summary_width = '40%' if mobile else '30%'
portfolio_composition_width = '60%' if mobile else '70%'
initial_day = portfolio['Date'].iloc[-1]
app.layout = html.Div([
    html.H1(children='Portfolio', style={'margin-left': '100px'}),
    dcc.DatePickerSingle(
            id='my-date-picker-single',
            min_date_allowed=dt(2020, 1, 10),
            max_date_allowed=initial_day,
            initial_visible_month=initial_day,
            date=str(initial_day),
            display_format='DD-MM-YYYY',
            style={'margin-left': '100px', 'width': '50%', 'display':'inline-block', 'margin-bottom':'20px'}
            ),
    html.Div([
        html.Div([html.H6(children='Summary'),summary(portfolio)[0]], style={'margin-left': '100px', 'width': summary_width, 'display':'inline-block'}),
        html.Div([dcc.Graph(id='portfolio_composition', figure=portfolio_composition(portfolio), style={ 'display':'inline-block'}),], 
        style={'width': portfolio_composition_width, 'display':'inline-block', 'margin-left': '100px'})
    ],style={'display':'flex'}),
    dcc.Graph(id='Gains', figure=portfolio_variation('Gains', portfolio)),
    dcc.Graph(id='Gains%', figure=portfolio_variation('Gains (%)', portfolio)),
    dcc.Graph(id='Amount', figure=portfolio_variation('Amount', portfolio)),
    dcc.Interval(
                id='interval-component',
                interval=1*1000, # in milliseconds
                n_intervals=0
            )
    
])


@app.callback(Output('portfolio_composition', 'figure'),[Input('my-date-picker-single', 'date')])
def update_portfolio_composition(date):
    if date is not None:
        date = dt.strptime(re.split('T| ', date)[0], '%Y-%m-%d')
        return portfolio_composition(portfolio, date)

@app.callback(Output('summary_table', 'data'),[Input('my-date-picker-single', 'date')])
def update_table_data(date):
    if date is not None:
        date = dt.strptime(re.split('T| ', date)[0], '%Y-%m-%d')
        return summary(portfolio, date)[1]

@app.callback(Output('summary_table', 'columns'),[Input('my-date-picker-single', 'date')])
def update_table_columns(date):
    if date is not None:
        date = dt.strptime(re.split('T| ', date)[0], '%Y-%m-%d')
        return summary(portfolio, date)[2]


# @app.callback(Output('Gains', 'children'),[Input('interval-component', 'n_intervals')])
# def update_portfolio_data(n):
#     new_positions = webparser.get_positions()
#     portfolio = pd.concat((portfolio, new_positions))


if __name__ == '__main__':
    app.run_server(debug=True)