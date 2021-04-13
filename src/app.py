import argparse
from portfolio import Portfolio
import yaml
import dash
import dash_core_components as dcc
import dash_html_components as html
import dash_table
from dash.dependencies import Input, Output
import plotly.express as px
import pandas as pd
import dash_daq as daq
import dash_bootstrap_components as dbc
from dash_table.Format import Format, Group, Prefix, Scheme, Symbol
from dash import callback_context
from datetime import datetime, timedelta
from plotly.subplots import make_subplots
import numpy as np

pd.options.mode.chained_assignment = None  # default='warn'
parser = argparse.ArgumentParser()

parser.add_argument('--settings', 
                    type=str, 
                    help='Path of the file containing settings', 
                    default='../settings.yaml')

FLAGS = parser.parse_args()
settings_path = FLAGS.settings

with open(settings_path) as file:
    settings = yaml.load(file, Loader=yaml.FullLoader)

debug = settings['DEBUG']

print('>> Updating portfolio')
portfolio = Portfolio(settings)
portfolio.add_transactions()
portfolio.get_historic_data()
portfolio.get_data()
portfolio.get_holdings()

gains = portfolio.gains
gains_p = portfolio.gains_p
values = portfolio.values
prices = portfolio.prices
holdings = portfolio.holdings
portfolio_types = portfolio.types
dates = portfolio.dates
assets = [asset.name for asset in portfolio.assets.values()]


TEMPLATE = "plotly_dark"
BGCOLOR = 'rgba(34,34,34,255)'

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY])

euro_format = {'type':'numeric', 'format':Format(symbol=Symbol.yes, symbol_prefix='€ ')}
app.layout = dbc.Container([
    html.Div(id='cards'),
    html.Hr(),
    dbc.Row([
        dbc.Col(
            dcc.Dropdown(
                id = 'typ',
                options=[
                    {'label': key, 'value': key} for key in portfolio_types 
                ],
                value=[],
                multi=True,
                searchable=False
            ),
            width=4
        ),
        dbc.Col(
            dcc.Dropdown(
                id = 'data_type',
                options=[
                    {'label': label, 'value': value} for label, value 
                    in zip(['Gains €', 'Gains %', 'Value', 'Price'], 
                        ['gains', 'gains_p', 'values', 'prices'])
                ],
                value='gains',
                clearable=False,
                searchable=False
            ),  
            width=2
        ),
        dbc.Col(
            dbc.RadioItems(
                options=[
                    {"label": key, "value": key} for key in dates.keys()
                ],
                id="date",
                labelClassName="date-group-labels",
                labelCheckedClassName="date-group-labels-checked",
                className="date-group-items",
                inline=True,
                value = 'All',
            ),
            width=4
        ),
        dbc.Col(
            dbc.Checklist(
                options=[
                    {"label": "Detailed", "value": True},
                ],
                labelCheckedClassName="detailed-label-checked",
                labelClassName="detailed-label",
                className="detailed-item",
                value=[],
                id="detailed",
                switch=True,
            ),
            width=2
        )
    ]), 
    html.Br(),
    dbc.Card(
        dbc.Tabs([
                dbc.Tab(label='History', children=[
                    dbc.Row(dbc.Col(dcc.Graph(id="time-series-chart"),width=12))
                ]),
                dbc.Tab(label='Composition', children=[
                    html.Div([
                        dcc.Graph(id="sunburst")
                    ])
                ]),
                dbc.Tab(label='Holdings', children=[
                    dash_table.DataTable(
                        id='holdings',
                        columns=[
                            {'name': 'Asset', 'id': 'name'},
                            {'name':'Value', 'id': 'value'},
                            {'name':'Price', 'id': 'price'},
                            {'name':'Quantity', 'id': 'quantity', 'type':'numeric', 'format':Format(precision=3)},
                            {'name':'Gains €', 'id': 'gain', **euro_format},
                            {'name':'Gains %', 'id': 'gain_p', 'type':'numeric', 'format':Format(symbol=Symbol.yes, symbol_suffix=' %')},
                            {'name':'Fees', 'id': 'fee', **euro_format},
                            {'name':'Dividends', 'id': 'dividend', **euro_format},
                            ],
                        style_cell={'textAlign': 'left', 'backgroundColor': BGCOLOR, 'color': 'white'},
                        style_as_list_view=True,
                        style_data_conditional=[
                            {
                                'if': {
                                    'filter_query': '{gain} >= 0',
                                    'column_id': ['gain', 'gain_p']
                                },
                                'color': 'green',
                            },
                             {
                                'if': {
                                    'filter_query': '{gain} < 0',
                                    'column_id': ['gain', 'gain_p']
                                },
                                'color': 'red',
                            },
                            {
                                'if':{
                                    'filter_query': '{type} is blank',
                                    'column_id': holdings['All'].columns
                                },
                                'backgroundColor': 'rgb(44,44,44)'
                            }
                        ],
                        data=holdings['All'].to_dict('records'),
                        sort_action="native",
                    )
                ])
        ]),
    )
])


@app.callback(
    Output('cards', 'children'),
    Input('date', 'value')
)
def display_cards(date):
    def format_summary(summary):
        prefix = lambda x: '+'+str(x) if x>=0 else str(x) 
        for key, value in summary.items():
            value['gain'] = '€ ' + prefix(value['gain'])
            value['gain_p'] = prefix(value['gain_p']) + '%'
            summary[key] = value
        return summary

    holding = holdings[date]
    summary = holding[holding['type'].isnull()].set_index('name').to_dict('index')
    colors = []
    for data in summary.values():
        color = 'red' if data['gain'] < 0 else 'green'
        colors.append({'color': color})
    summary = format_summary(summary)

    main_card = dbc.Card(
        [   
            html.Div([
                html.Div(html.H1('HOLDINGS OVERVIEW')),
                html.Div([
                    html.H1(f"€ {summary['Total']['value']}", className='card-value'),
                    html.Div([html.H2(f"{summary['Total']['gain']}", style=colors[0]),
                             html.H2(f"{summary['Total']['gain_p']}", className='gain_p', style=colors[0])],
                             className='card-gain')
                ],
                className='main_data')    
            ],
            className='main-card')
        ],
        body=True,
        color='dark',
        inverse=True
    )
    cards = [
        dbc.Card(
            [   
                html.Div([
                    html.Div([
                        html.H2(f"{key}", className='card-title'),
                        dbc.Progress(value=100*data['value']/summary['Total']['value'])
                        ],
                        className='type-name'),
                    html.Div([
                        html.H2(f"€ {data['value']}", className='card-value'),
                        html.Div([html.H3(f"{data['gain']}", style=colors[it]),
                                 html.H3(f"{data['gain_p']}", className='gain_p', style=colors[it])],
                                 className='card-gain')
                        ],
                        className='type-data')
                ],
                className='type-card')
            ],
            body=True,
            color='dark',
            inverse=True
        )
        for it, (key, data) in enumerate(summary.items()) if key!='Total' 
    ]

    return [dbc.Row([dbc.Col(main_card)]), dbc.Row([dbc.Col(cards)])]

@app.callback(
    Output("time-series-chart", "figure"), 
    [Input("typ", "value"), 
    Input("data_type", "value"), 
    Input("detailed", "value"),
    Input('date', 'value')]
    )
def display_time_series(typ, data_type, detailed, date):
    if detailed:
        typ = [asset for desc in typ for asset in list(portfolio_types[desc])]
        typ = [asset for asset in assets if asset in typ]
    data_types = {'gains':gains, 'gains_p':gains_p, 'values': values, 'prices': prices}
    df = data_types[data_type]
    
    if data_type == 'values':
        fig = px.area(df[pd.to_datetime(df['date'])>=pd.to_datetime(dates[date])],
                    labels={'date':'', 'value':'', 'variable':''},
                    x='date', y=['Total']+typ, template=TEMPLATE)
    else:
        fig = px.line(df[pd.to_datetime(df['date'])>=pd.to_datetime(dates[date])],
                    labels={'date':'', 'value':'', 'variable':''},
                    x='date', y=['Total']+typ, template=TEMPLATE)
    if (data_type == 'values' or detailed) and typ!=[]:
        for trace in fig['data']: 
            if(trace['name'] == 'Total'): trace['visible'] = 'legendonly'

    fig.update_layout(
        legend=dict(
            yanchor="top",
            y=-0.1,
            xanchor="left",
            x=0.01
        ),
        font={'size':20},
        hoverlabel={'font_size':20},
        autosize=True,
        # width=950,
        height=600 + len(typ)*31,
        paper_bgcolor=BGCOLOR,
        plot_bgcolor=BGCOLOR,
        xaxis={'fixedrange':True},
        yaxis={'fixedrange':True}
    )
    fig.update_traces(hovertemplate='%{x}: <b>%{y}</b>')
    
    return fig

@app.callback(
    [Output('holdings', "data"), Output("holdings", "tooltip_data")],
    [Input('typ', "value"), Input("detailed", "value"), Input('date', 'value')]
    )
def update_table(typ, detailed, date):
    holding = holdings[date]
    df = holding[holding.name.isin(typ+['Total'])]
    if detailed:
        df = pd.concat([df,holding[holding.type.isin(typ)]])
    ending = df['name'].str.len()>27
    ending = ending.replace(True,'...').replace(False,'')
    tooltip_data= [{'name':name} for name in df['name']]
    df['name'] = df['name'].str[:20] + ending
    return df.to_dict('records'), tooltip_data

@app.callback(
    Output('sunburst', "figure"),
    [Input("data_type", "value"), Input("detailed", "value"), Input('date', 'value')])
def display_sunburst(data_type, detailed, date):
    def update_data(data):
        new = []
        for item in data:
            if item[0] == '(?)':
                item[0] = item[2]
            new.append(item)
        return np.array(new)

    data_types = {'gains':'gain', 'gains_p':'gain_p', 'values': 'value', 'prices':'price'}
    datatype = data_types[data_type]
    custom_data = ['name', datatype]
    path = ['type', 'symbol'] if detailed else ['type']
    
    holding = holdings[date]

    pos_holding = holding[(~holding['type'].isnull()) & (holding[datatype]>=0)]
    neg_holding = holding[holding[datatype]<0]
    neg_holding.loc[(neg_holding[datatype]<0), datatype] = - neg_holding[datatype] 
    neg_holding = neg_holding[~neg_holding['type'].isnull()]
    
    colors = px.colors.qualitative.Plotly
    types = list(holding[~holding['type'].isnull()].type.unique())
    color_map = {typ: color for typ, color in zip(types, colors)}

    pos_fig = px.sunburst(pos_holding, path=path, values=datatype, color='type', 
                template=TEMPLATE, custom_data=custom_data, color_discrete_map=color_map)
    neg_fig = px.sunburst(neg_holding, path=path, values=datatype, color='type', 
                template=TEMPLATE, custom_data=custom_data, color_discrete_map=color_map)
    
    pos_fig.update_traces(hovertemplate='<b>%{customdata[0]}:</b> %{customdata[1]:.2f}')
    neg_fig.update_traces(hovertemplate='<b>%{customdata[0]}:</b> %{customdata[1]:.2f}')

    pos_fig.for_each_trace(
        lambda trace: trace.update(customdata=update_data(trace['customdata'])),
    )
    neg_fig.for_each_trace(
        lambda trace: trace.update(customdata=update_data(trace['customdata'])),
    )

    titles = {'gains':'gain €', 'gains_p':'gain %', 'values': 'Value', 'prices':'Price'}
    font = dict(size=20,color='#ffffff',family='Lato')
    if neg_fig['data'] and pos_fig['data']:
        fig = make_subplots(rows=1, cols=2, specs=[[{"type": "domain"}, {"type": "domain"}]], 
                            subplot_titles=(f"Positive {titles[data_type]}<br>",f"Negative {titles[data_type]}"))
        fig.add_trace(pos_fig['data'][0], row=1, col=1)
        fig.add_trace(neg_fig['data'][0], row=1, col=2)
        for i in fig['layout']['annotations']:
            i['font'] = font

    else:
        if neg_fig['data']:
            fig = neg_fig
            side = 'Negative' if data_type not in ['values', 'prices'] else ''
        else:
            fig = pos_fig
            side = 'Positive' if data_type not in ['values', 'prices'] else ''
        fig['layout']['title'] = {'text': f'{side} {titles[data_type]}',
                                 'font':font, 'xanchor': 'center', 'xref': 'paper', 'x': 0.5,}
    fig.update_layout(
        paper_bgcolor=BGCOLOR,
        plot_bgcolor=BGCOLOR,
        margin=dict(t=100, b=10, r=10, l=10),
        font={'size':20},
        hoverlabel={'font_size':20}
    )

    return fig

if __name__ == '__main__':
    app.run_server(debug=debug)
