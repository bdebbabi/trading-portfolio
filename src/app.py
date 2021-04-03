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

# gains = pd.read_csv('gains.csv')
# gains_p = pd.read_csv('gains_p.csv')
# values = pd.read_csv('values.csv')
# holdings = pd.read_csv('holdings.csv').sort_values('value', ascending=False)

gains = portfolio.gains
gains_p = portfolio.gains_p
values = portfolio.values
holdings = portfolio.holdings
portfolio_types = portfolio.types

summary = holdings[holdings['type'].isnull()].set_index('name').to_dict('index')
colors = []
for data in summary.values():
    color = 'red' if data['last_gain'] < 0 else 'green'
    colors.append({'color': color})

TEMPLATE = "plotly_dark"
BGCOLOR = 'rgba(34,34,34,255)'

app = dash.Dash(__name__, 
                external_stylesheets=[dbc.themes.DARKLY],
                )

main_card = dbc.Card(
    [   
        html.Div([
            html.Div(html.H1('HOLDINGS OVERVIEW')),
            html.Div([
                html.H1(f"€ {summary['Total']['value']}", className='card-value'),
                html.H2(f"€ {summary['Total']['last_gain']} {summary['Total']['gains_p']}%", className='card-text', style=colors[0])
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
                    html.H3(f"€ {data['last_gain']}  {data['gains_p']}%", className='card-gain', style=colors[it])
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

euro_format = {'type':'numeric', 'format':Format(symbol=Symbol.yes, symbol_prefix='€ ')}
app.layout = dbc.Container([
    dbc.Row([dbc.Col(main_card)]),
    dbc.Row([dbc.Col(cards)]),
    html.Hr(),
    dbc.Row([
        dbc.Col(
            dcc.Dropdown(
                id = 'typ',
                options=[
                    {'label': label, 'value': value} for label, value 
                    in zip(['ETF', 'Stock', 'Crypto'], 
                        ['ETF', 'STOCK', 'crypto'])
                ],
                value=[],
                multi=True
                ),  
        ),
        dbc.Col(
            dcc.Dropdown(
                id = 'data_type',
                options=[
                    {'label': label, 'value': value} for label, value 
                    in zip(['Gains €', 'Gains %', 'Value'], 
                        ['gains', 'gains_p', 'values'])
                ],
                value='gains',
                clearable=False
                ),  
        ),
        dbc.Col(
            html.Div([
                daq.BooleanSwitch(
                    id='detailed',
                    on=False,
                    label="Detailed",
                    labelPosition="left",
                    style={'font-size':'20px !important;'}
                    ), 
            ],
            className='boolean-detailed')
        )
    ]), 
    html.Br(),
    dbc.Card(
        dbc.Tabs([
                dbc.Tab(label='History', children=[
                    dcc.Graph(id="time-series-chart")
                ]),
                dbc.Tab(label='Composition', children=[
                    html.Div([
                        dcc.Graph(id="positive_sunburst"),
                        dcc.Graph(id="negative_sunburst")
                    ])
                ]),
                dbc.Tab(label='Holdings', children=[
                    dash_table.DataTable(
                        id='holdings',
                        columns=[
                            {'name': 'Asset', 'id': 'name'},
                            {'name':'Value', 'id': 'value'},
                            {'name':'Quantity', 'id': 'quantity', 'type':'numeric', 'format':Format(precision=3)},
                            {'name':'Gains €', 'id': 'last_gain', **euro_format},
                            {'name':'Gains %', 'id': 'gains_p', 'type':'numeric', 'format':Format(symbol=Symbol.yes, symbol_suffix=' %')},
                            {'name':'Fees', 'id': 'fee', **euro_format},
                            {'name':'Dividends', 'id': 'dividend', **euro_format},
                             
                            ],
                        style_cell={'textAlign': 'left', 'backgroundColor': BGCOLOR, 'color': 'white'},
                        style_as_list_view=True,
                        style_data_conditional=[
                            {
                                'if': {
                                    'filter_query': '{last_gain} >= 0',
                                    'column_id': ['last_gain', 'gains_p']
                                },
                                'color': 'green',
                            },
                             {
                                'if': {
                                    'filter_query': '{last_gain} < 0',
                                    'column_id': ['last_gain', 'gains_p']
                                },
                                'color': 'red',
                            },
                        ],
                        data=holdings.to_dict('records'),
                        sort_action="native",
                    )
                ])
        ]),
    )
])

@app.callback(
    Output("time-series-chart", "figure"), 
    [Input("typ", "value"), 
    Input("data_type", "value"), 
    Input("detailed", "on")])
def display_time_series(typ, data_type, detailed):
    if detailed:
        typ = [asset for desc in typ for asset in list(portfolio_types[desc])]
    data_types = {'gains':gains, 'gains_p':gains_p, 'values': values}

    fig = px.line(data_types[data_type],
                  labels={'date':'', 'value':'', 'variable':''},
                  x='date', y=typ+['Total'], template=TEMPLATE)
    if detailed and typ!=[]:
        for trace in fig['data']: 
            if(trace['name'] == 'Total'): trace['visible'] = 'legendonly'
    fig.update_xaxes(
        # rangeslider_visible=True,
        rangeselector=dict(
            buttons=list([
                dict(step="all", label="All"),
                dict(count=1, label="1Y", step="year", stepmode="backward"),
                dict(count=1, label="YTD", step="year", stepmode="todate"),
                dict(count=6, label="6m", step="month", stepmode="backward"),
                dict(count=1, label="1m", step="month", stepmode="backward")
            ])
        )
    )

    fig.update_layout(
        legend=dict(
            yanchor="top",
            y=-0.1,
            xanchor="left",
            x=0.01
        ),
        autosize=True,
        width=950,
        height=600 + len(typ)*20,
        paper_bgcolor=BGCOLOR,
        plot_bgcolor=BGCOLOR

    )
    
    return fig

@app.callback(
    Output('holdings', "data"),
    [Input('typ', "value"), Input("detailed", "on")])
def update_table(typ, detailed):
    df = holdings[holdings.name.isin(typ+['Total'])]
    if detailed:
        df = pd.concat([df,holdings[holdings.type.isin(typ)]])
    return df.to_dict('records')

@app.callback(
    [Output('positive_sunburst', "figure"), Output('negative_sunburst', "figure")],
    [Input("data_type", "value"), Input("detailed", "on")])
def display_sunburst(data_type, detailed):
    data_types = {'gains':'last_gain', 'gains_p':'gains_p', 'values': 'value'}
    data_type = data_types[data_type]
    path = ['type', 'short_name'] if detailed else ['type']
    pos_fig = px.sunburst(holdings[(~holdings['type'].isnull()) &
            (holdings[data_type]>=0)], 
            path=path, values=data_type, color='type', template=TEMPLATE)
    neg_holdings = holdings[holdings[data_type]<0]
    neg_holdings.loc[(neg_holdings[data_type]<0), data_type] = - neg_holdings[data_type] 
    neg_fig = px.sunburst(neg_holdings[~neg_holdings['type'].isnull()], 
            path=path, values=data_type, color='type',template=TEMPLATE)
    
    pos_fig.update_layout(
        paper_bgcolor=BGCOLOR,
        plot_bgcolor=BGCOLOR
    )
    neg_fig.update_layout(
        paper_bgcolor=BGCOLOR,
        plot_bgcolor=BGCOLOR
    )

    return pos_fig, neg_fig

if __name__ == '__main__':
    app.run_server(debug=debug)
