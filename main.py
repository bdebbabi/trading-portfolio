import argparse
import dash
from dash.dependencies import Input, Output
import dash_html_components as html
import dash_core_components as dcc
from datetime import datetime as dt
import re
import pandas as pd
from portfolio import update, add_gains_and_total, summary, portfolio_composition, portfolio_variation, add_gains_variation
from parser import webparser
import ast
parser = argparse.ArgumentParser()

parser.add_argument('--update', type=ast.literal_eval, help='Whether or not to update the portfolio', default=True)
parser.add_argument('--debug', type=int, help='Debug level', default=0)
parser.add_argument('--live', type=ast.literal_eval, help='Live positions', default=True)
parser.add_argument('--mobile', type=ast.literal_eval, help='Whether or not to update portfolio in mobile version', default=False)
FLAGS = parser.parse_args()

update_portfolio = FLAGS.update
debug = FLAGS.debug
live = FLAGS.live

    
mobile = FLAGS.mobile
if update_portfolio or live:
    web_parser = webparser(debug)
    live_data = None
    if update_portfolio:
        print('>>updating portfolio')
        sessionID = web_parser.get_session_ID()
        update(sessionID)

    if live:
        positions = web_parser.get_positions()
        live_data = web_parser.get_account_summary()
    


portfolio = add_gains_and_total()
if live:
    portfolio = pd.concat((portfolio, positions),ignore_index=True)

portfolio = add_gains_variation(portfolio)

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
# initial_day = datetime.datetime.strptime(portfolio['Date'].iloc[-1], '%d-%m-%Y')
summary_width = '60%' if mobile else '30%'
portfolio_composition_width = '100%' if mobile else '70%'
display = 'block' if mobile else 'flex'
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
        html.Div([html.H6(children='Summary'),summary(portfolio, live_data=live_data)[0]], style={'margin-left': '100px', 'width': summary_width, 'display':'inline-block'}),
        html.Div([dcc.Graph(id='portfolio_composition', figure=portfolio_composition(portfolio), style={ 'display':'inline-block'}),], 
        style={'width': portfolio_composition_width, 'display':'inline-block', 'margin-left': '100px'})
    ],style={'display': display}),
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
        return summary(portfolio, date, live_data)[1]

@app.callback(Output('summary_table', 'columns'),[Input('my-date-picker-single', 'date')])
def update_table_columns(date):
    if date is not None:
        date = dt.strptime(re.split('T| ', date)[0], '%Y-%m-%d')
        return summary(portfolio, date, live_data)[2]


# @app.callback(Output('Gains', 'children'),[Input('interval-component', 'n_intervals')])
# def update_portfolio_data(n):
#     new_positions = webparser.get_positions()
#     portfolio = pd.concat((portfolio, new_positions))


if __name__ == '__main__':
    app.run_server(debug=True)