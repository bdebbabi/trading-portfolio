import argparse
import dash
from dash.dependencies import Input, Output
import dash_html_components as html
import dash_core_components as dcc
from datetime import datetime as dt
import re
import pandas as pd
from portfolio import update, add_gains_and_total, summary, portfolio_composition, portfolio_variation, add_gains_variation, positions_summary
from parser import webparser
import ast
parser = argparse.ArgumentParser()

parser.add_argument('--debug', type=int, help='Debug level', default=0)
parser.add_argument('--live', type=ast.literal_eval, help='Live positions', default=True)
parser.add_argument('--mobile', type=ast.literal_eval, help='Whether or not to use mobile version', default=False)
parser.add_argument('--creationDate', type=str, help='Account creation date in the following format YYYY-MM-dd', default='2020-01-09')

parser.add_argument('--authentificationFile', type=str, help='Path of the file containing authetification info', default='pass.bin')
parser.add_argument('--hashed', type=ast.literal_eval, help='Whether or not the authentification file is storing hashed values', default=True)

FLAGS = parser.parse_args()

debug = FLAGS.debug
live = FLAGS.live
mobile = FLAGS.mobile
creation_date = dt.strptime(FLAGS.creationDate, '%Y-%m-%d')
authentification_file = FLAGS.authentificationFile
hashed = FLAGS.hashed

if live:
    print('>>updating portfolio')
    live_data = None
    web_parser = webparser(authentification_file, hashed, debug)
    sessionID = web_parser.get_session_ID()
    update(sessionID, creation_date)
    positions = web_parser.get_positions()
    live_data = web_parser.get_account_summary()
    current_time = dt.now().strftime("%H:%M:%S")
    print(f'Showing live positions at {current_time}.')    
else:
    live_data = None

portfolio = add_gains_and_total()
if live:
    portfolio = pd.concat((portfolio, positions),ignore_index=True)

portfolio = add_gains_variation(portfolio)

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
summary_width = '60%' if mobile else '30%'
portfolio_composition_width = '100%' if mobile else '70%'
display = 'block' if mobile else 'flex'
min_day = portfolio['Date'].iloc[0]
max_day = portfolio['Date'].iloc[-1]
app.layout = html.Div([
    html.H1(children='Portfolio', style={'margin-left': '100px'}),
    html.Div([
            html.H4(children='Date:', style={'margin-left': '100px'}),
            dcc.DatePickerSingle(
                id='my-date-picker-single',
                min_date_allowed=min_day,
                max_date_allowed=max_day,
                initial_visible_month=max_day,
                date=str(max_day),
                display_format='DD-MM-YYYY',
                style={'margin-left': '10px','margin-top': '10px', 'width': '50%', 'display':'inline-block'}
                )
    ], style={'display':'flex'}),
    html.Div([
        html.Div([html.H6(children='Summary'),summary(portfolio, live_data=live_data)[0]], style={'margin-left': '100px', 'width': summary_width, 'display':'inline-block'}),
        html.Div([html.H6(children='Portfolio composition'), dcc.Graph(id='portfolio_composition', figure=portfolio_composition(portfolio), style={ 'display':'inline-block'}),], 
        style={'width': portfolio_composition_width, 'display':'inline-block', 'margin-left': '100px'})
    ],style={'display': display}),
    html.Div([html.H6(children='Positions'),positions_summary(portfolio)[0]], style={'margin-left': '100px', 'width':'60%'}),

    dcc.Graph(id='Gains', figure=portfolio_variation('Gains', portfolio)),
    dcc.Graph(id='Gains%', figure=portfolio_variation('Gains (%)', portfolio)),
    dcc.Graph(id='Amount', figure=portfolio_variation('Amount', portfolio))
    
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
        return summary(portfolio, date, live_data)[1]

@app.callback(Output('summary_table', 'columns'),[Input('my-date-picker-single', 'date')])
def update_table_columns(date):
    if date is not None:
        date = dt.strptime(re.split('T| ', date)[0], '%Y-%m-%d')
        return summary(portfolio, date, live_data)[2]

@app.callback(Output('positions_summary_table', 'data'),[Input('my-date-picker-single', 'date')])
def update_positions_table_data(date):
    if date is not None:
        date = dt.strptime(re.split('T| ', date)[0], '%Y-%m-%d')
        return positions_summary(portfolio, date)[1]

@app.callback(Output('positions_summary_table', 'columns'),[Input('my-date-picker-single', 'date')])
def update_positions_table_columns(date):
    if date is not None:
        date = dt.strptime(re.split('T| ', date)[0], '%Y-%m-%d')
        return positions_summary(portfolio, date)[2]


if __name__ == '__main__':
    app.run_server(debug=True)