from datetime import datetime, timedelta
from pathlib import Path
import argparse
import json

from dash_table.Format import Format, Group, Prefix, Scheme, Symbol
from dash.dependencies import Input, Output, State
import dash_bootstrap_components as dbc
from plotly.subplots import make_subplots
import dash_html_components as html
import dash_core_components as dcc
from dash import callback_context
import plotly.express as px
import dash_daq as daq
import pandas as pd
import numpy as np
import dash_table
import dash
import yaml

from portfolio import Portfolio
from utils import get_dates

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
prices_icon = html.I(className="fas fa-sync-alt")
transactions_icon = html.I(className="fas fa-cloud-download-alt")

def get_portfolio_data(data_type):
    data = pd.read_csv(f'data/{data_type}.csv')
    return data


def get_portfolio_holdings(date):
    holdings = pd.read_csv(f'data/holdings_{date}.csv')
    return holdings


def get_portfolio_assets(value):
    with open('data/assets.json') as f:
        assets_data = json.load(f)

    return assets_data[value]


def update_portfolio(update_transactions=True):
    print('>> Updating portfolio')
    portfolio = Portfolio(settings)
    missing = portfolio.add_transactions(
        update_transactions=update_transactions)
    portfolio.get_historic_data()
    portfolio.get_data()
    portfolio.get_holdings()
    return missing


dates = get_dates(datetime.strptime(
    settings['CREATION_DATE'], '%Y-%m-%d').date())

TEMPLATE = "plotly_dark"
BGCOLOR = 'rgba(34,34,34,255)'

app = dash.Dash(__name__, suppress_callback_exceptions=True, external_stylesheets=[
                dbc.themes.DARKLY, 'https://use.fontawesome.com/releases/v5.8.1/css/all.css'])

euro_format = {'type': 'numeric', 'format': Format(
    symbol=Symbol.yes, symbol_prefix='€ ')}
if not Path('data/transactions.csv').is_file():
    update_portfolio()


def create_button(symbol, name):
    return html.Button(symbol,
                       id=f"{name}-button",
                       className="mr-2",
                       style={'font-size': 'x-large',
                              'background-color': 'transparent',
                              'border-color': 'transparent'})


def serve_layout():
    layout = dbc.Container([
        html.Div(id='cards'),
        html.Hr(),
        dbc.Row([
            dbc.Col(
                dcc.Dropdown(
                    id='typ',
                    options=[
                        {'label': key, 'value': key} for key in get_portfolio_assets('types')
                    ],
                    value=[],
                    multi=True,
                    searchable=False
                ),
                width=4
            ),
            dbc.Col(
                dcc.Dropdown(
                    id='data_type',
                    options=[
                        {'label': label, 'value': value} for label, value
                        in zip(['Gains €', 'Gains %', 'Value', 'Price'],
                               ['gains', 'gains_p', 'values', 'prices'])
                    ],
                    value='gains',
                    clearable=False,
                    searchable=False
                ),
                width=2,
                style={
                    'max-width': '14%',
                    'margin-right': '3%'
                }
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
                    value='All',
                ),
                width=3
            ),
            dbc.Col(
                dbc.Checklist(
                    options=[
                        {"label": "+", "value": True},
                    ],
                    labelCheckedClassName="detailed-label-checked",
                    labelClassName="detailed-label",
                    className="detailed-item",
                    value=[],
                    id="detailed",
                    switch=True,
                ),
                width=1
            ),
            dbc.Col(
                [
                    html.Div([create_button(prices_icon, 'prices')],
                             id='update-prices-div'),
                    html.Div(id='update-prices', children=[]),
                ],
                width=1
            ),
            dbc.Col(
                [
                    html.Div([create_button(transactions_icon,
                                            'transactions')], id='update-transactions-div'),
                    html.Div(id='update-transactions', children=[]),
                ],
                width=1,
                style={'margin-left': 'inherit'}
            ),
            dbc.Toast(
                [html.P("This is the content of the toast", className="mb-0")],
                id="toast",
                dismissable=True,
                is_open=False,
                # duration=4000
                className='toast'
            ),
        ]),
        html.Br(),
        dbc.Card(
            dbc.Tabs([
                dbc.Tab(label='History', children=[
                        dbc.Row(
                            dbc.Col(dcc.Graph(id="time-series-chart"), width=12))
                        ]),
                dbc.Tab(label='Composition', children=[
                        html.Div([
                            dcc.Graph(id="sunburst")
                        ])
                        ]),
                dbc.Tab(label='Exposure', children=[
                        html.Div([
                            dcc.Graph(id="exposure-sunburst"),
                            html.P('Top Holdings', style={'margin-left': '15%', 'font-size': '30px'}),
                            dash_table.DataTable(
                                id="exposure-table",
                                columns=[
                                    {'name':'Holding', 'id':'holding'},
                                    {'name':'Weight', 'id':'ratio', 'type': 'numeric', 'format': Format(
                                    symbol=Symbol.yes, symbol_suffix=' %')},
                                    {'name':'Sector', 'id':'type'},
                                ],
                                style_cell={
                                    'textAlign': 'left', 
                                    'backgroundColor': BGCOLOR, 
                                    'color': 'white',
                                    'overflow': 'hidden',
                                    'textOverflow': 'ellipsis',
                                    'maxWidth': 0
                                    },
                                style_as_list_view=True,
                                style_header={
                                    'fontWeight': 'bold'
                                },
                                style_table={
                                    'width': '70%',
                                    'margin-left': '15%'
                                },
                                cell_selectable=False,
                                tooltip_delay=0,
                                tooltip_duration=None,
                                style_cell_conditional=[
                                    {'if': {'column_id': 'holdings'},'width': '40%'},
                                    {'if': {'column_id': 'ratio'},'width': '20%'},
                                    {'if': {'column_id': 'type'},'width': '40%'},
                                ]
                                )
                        ]),
                        ]),
                dbc.Tab(label='Holdings', children=[
                        dash_table.DataTable(
                            id='holdings',
                            columns=[
                                {'name': 'Asset', 'id': 'name'},
                                {'name': 'Value', 'id': 'value'},
                                {'name': 'Price', 'id': 'price'},
                                {'name': 'Quantity', 'id': 'quantity',
                                    'type': 'numeric', 'format': Format(precision=3)},
                                {'name': 'Gains €', 'id': 'gain', **euro_format},
                                {'name': 'Gains %', 'id': 'gain_p', 'type': 'numeric', 'format': Format(
                                    symbol=Symbol.yes, symbol_suffix=' %')},
                                {'name': 'Fees', 'id': 'fee', **euro_format},
                                {'name': 'Dividends', 'id': 'dividend', **euro_format},
                            ],
                            style_cell={
                                'textAlign': 'left', 'backgroundColor': BGCOLOR, 'color': 'white'},
                            style_as_list_view=True,
                            tooltip_header={'gain':'With dividends and fees'},
                            tooltip_delay=0,
                            tooltip_duration=None,
                            cell_selectable=False,
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
                                    'if': {
                                        'filter_query': '{type} is blank',
                                        'column_id': get_portfolio_holdings('All').columns
                                    },
                                    'backgroundColor': 'rgb(44,44,44)'
                                }
                            ],
                            data=get_portfolio_holdings(
                                'All').to_dict('records'),
                            sort_action="native",
                        )
                        ])
            ]),
        ),
        html.Div(id='signal', style={'display': 'none'}),
        html.Div(id='reload', style={'display': 'none'}),
        html.Div(id='update_reload', style={'display': 'none'}),
        html.Div(id='update_reload_trig', style={'display': 'none'}),
    ])
    return layout


@app.callback([
    Output('signal', 'children'),
    Output('update-prices-div', 'children'),
    Output('update-transactions-div', 'children'),
    Output("toast", "is_open"),
    Output("toast", "children"),
],
    [
    Input('prices-button', 'n_clicks'),
    Input('transactions-button', 'n_clicks'),
],
    State('update-prices-div', 'children'),
    State('update-transactions-div', 'children'),
    prevent_initial_call=True,
)
def update_transactionss(bt1, bt2, children_pr, children_tr):
    trigger = callback_context.triggered[0]["prop_id"].split(".")[0]
    import time
    if trigger == 'prices-button':
        missing = update_portfolio(update_transactions=False)
    elif trigger == 'transactions-button':
        missing = update_portfolio()

    new_element = create_button(prices_icon, 'prices')
    children_pr.pop()
    children_pr.append(new_element)

    new_element = create_button(transactions_icon, 'transactions')
    children_tr.pop()
    children_tr.append(new_element)

    if missing:
        missing_list = []
        for miss in missing:
            missing_list.append('- ' + miss)
            missing_list.append(html.Br())
        toast_content = html.P(
            ['Missing values for:', html.Br()]+missing_list[:-1], className="mb-0")
        toast_return = True
    else:
        toast_content = []
        toast_return = False

    return 1, children_pr, children_tr, toast_return, toast_content


@app.callback([
    Output('prices-button', 'children'),
    Output('prices-button', 'disabled'),
    Output('transactions-button', 'children'),
    Output('transactions-button', 'disabled')
],
    [
    Input('prices-button', 'n_clicks'),
    Input('transactions-button', 'n_clicks'),
]
)
def load_update_button(pr_btn, tr_btn):
    trigger = callback_context.triggered[0]["prop_id"].split(".")[0]
    if not pr_btn and not tr_btn:
        return html.I(className="fas fa-sync-alt"), False, transactions_icon, False
    if trigger == 'prices-button':
        return [dbc.Spinner(size="lg")], True, transactions_icon, True
    elif trigger == 'transactions-button':
        return prices_icon, True, [dbc.Spinner(size="lg")], True


@app.callback(
    Output('cards', 'children'),
    [Input('date', 'value'), Input('signal', 'children')]
)
def display_cards(date, signal):
    def format_summary(summary):
        def prefix(x): return '+'+str(x) if x >= 0 else str(x)
        for key, value in summary.items():
            value['gain'] = '€ ' + prefix(value['gain'])
            value['gain_p'] = prefix(value['gain_p']) + '%'
            summary[key] = value
        return summary

    holding = get_portfolio_holdings(date)
    summary = holding[holding['type'].isnull()].set_index(
        'name').to_dict('index')
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
                    html.H1(f"€ {summary['Total']['value']}",
                            className='card-value'),
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
                        dbc.Progress(
                            value=100*data['value']/summary['Total']['value'])
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
        for it, (key, data) in enumerate(summary.items()) if key != 'Total'
    ]

    return [dbc.Row([dbc.Col(main_card)]), dbc.Row([dbc.Col(cards)])]


@app.callback(
    Output("time-series-chart", "figure"),
    [Input("typ", "value"),
     Input("data_type", "value"),
     Input("detailed", "value"),
     Input('date', 'value'),
     Input('signal', 'children'),
     ]
)
def display_time_series(typ, data_type, detailed, date, signal):
    if detailed:
        typ = [asset for desc in typ for asset in list(
            get_portfolio_assets('types')[desc])]
        typ = [asset for asset in get_portfolio_assets(
            'assets') if asset in typ]

    df = get_portfolio_data(data_type)

    if data_type == 'values':
        fig = px.area(df[pd.to_datetime(df['date']) >= pd.to_datetime(dates[date])],
                      labels={'date': '', 'value': '', 'variable': ''},
                      x='date', y=['Total']+typ, template=TEMPLATE)
    else:
        fig = px.line(df[pd.to_datetime(df['date']) >= pd.to_datetime(dates[date])],
                      labels={'date': '', 'value': '', 'variable': ''},
                      x='date', y=['Total']+typ, template=TEMPLATE)
    if (data_type == 'values' or detailed) and typ != []:
        for trace in fig['data']:
            if(trace['name'] == 'Total'):
                trace['visible'] = 'legendonly'

    fig.update_layout(
        legend=dict(
            yanchor="top",
            y=-0.1,
            xanchor="left",
            x=0.01
        ),
        font={'size': 20},
        hoverlabel={'font_size': 20},
        autosize=True,
        # width=950,
        height=600 + len(typ)*31,
        paper_bgcolor=BGCOLOR,
        plot_bgcolor=BGCOLOR,
        xaxis={'fixedrange': True},
        yaxis={'fixedrange': True}
    )
    fig.update_xaxes(showgrid=False, zeroline=False, tickformatstops = [
        dict(dtickrange=[3600000, 36000000], value="%H:%M"),
        dict(dtickrange=[36000000, 86400000], value="%d %b"),
        dict(dtickrange=[86400000, 604800000], value="%d %b"),
        dict(dtickrange=[604800000, "M1"], value="%d %b"),
        dict(dtickrange=["M1", "M12"], value="%b %y"),
        dict(dtickrange=["M12", None], value="%b %y")
        ])

    for ser in fig['data']:
        ser['text']= pd.to_datetime(df['date']).dt.strftime('%d %b %Y').tolist()
        ser['hovertemplate']='%{text}: <b>%{y}</b>'

    fig.update_yaxes(showgrid=False, zeroline=False)
    return fig


@app.callback(
    [Output('holdings', "data"), 
     Output("holdings", "tooltip_data")],
    [Input('typ', "value"), 
     Input("detailed", "value"), 
     Input('date', 'value'), 
     Input('signal', 'children')
    ]
)
def update_table(typ, detailed, date, signal):
    holding = get_portfolio_holdings(date)
    df = holding[holding.name.isin(typ+['Total'])]
    if detailed:
        df = pd.concat([df, holding[holding.type.isin(typ)]])
    ending = df['name'].str.len() > 27
    ending = ending.replace(True, '...').replace(False, '')
    tooltip_data = [{'name': name} for name in df['name']]
    df['name'] = df['name'].str[:20] + ending
    return df.to_dict('records'), tooltip_data


@app.callback(
    Output('sunburst', "figure"),
    [Input("data_type", "value"), 
    Input("detailed", "value"), 
    Input('date', 'value'), 
    Input('signal', 'children')])
def display_sunburst(data_type, detailed, date, signal):
    def update_data(data):
        new = []
        for item in data:
            if item[0] == '(?)':
                item[0] = item[2]
            new.append(item)
        return np.array(new)

    data_types = {'gains': 'gain', 'gains_p': 'gain_p',
                  'values': 'value', 'prices': 'price'}
    datatype = data_types[data_type]
    custom_data = ['name', datatype]
    path = ['type', 'symbol'] if detailed else ['type']

    holding = get_portfolio_holdings(date)

    pos_holding = holding[(~holding['type'].isnull())
                          & (holding[datatype] >= 0)]
    neg_holding = holding[holding[datatype] < 0]
    neg_holding.loc[(neg_holding[datatype] < 0),
                    datatype] = - neg_holding[datatype]
    neg_holding = neg_holding[~neg_holding['type'].isnull()]

    colors = px.colors.qualitative.Plotly
    types = list(holding[~holding['type'].isnull()].type.unique())
    color_map = {typ: color for typ, color in zip(types, colors)}

    pos_fig = px.sunburst(pos_holding, path=path, values=datatype, color='type',
                          template=TEMPLATE, custom_data=custom_data, color_discrete_map=color_map)
    neg_fig = px.sunburst(neg_holding, path=path, values=datatype, color='type',
                          template=TEMPLATE, custom_data=custom_data, color_discrete_map=color_map)

    pos_fig.update_traces(
        hovertemplate='<b>%{customdata[0]}:</b> %{customdata[1]:.2f}')
    neg_fig.update_traces(
        hovertemplate='<b>%{customdata[0]}:</b> %{customdata[1]:.2f}')

    pos_fig.for_each_trace(
        lambda trace: trace.update(
            customdata=update_data(trace['customdata'])),
    )
    neg_fig.for_each_trace(
        lambda trace: trace.update(
            customdata=update_data(trace['customdata'])),
    )

    titles = {'gains': 'gain €', 'gains_p': 'gain %',
              'values': 'Value', 'prices': 'Price'}
    font = dict(size=30, color='#ffffff', family='Lato')
    if neg_fig['data'] and pos_fig['data']:
        fig = make_subplots(rows=1, cols=2, specs=[[{"type": "domain"}, {"type": "domain"}]],
                            subplot_titles=(f"Positive {titles[data_type]}<br>", f"Negative {titles[data_type]}"))
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
                                  'font': font, 'xanchor': 'center', 'xref': 'paper', 'x': 0.5, }
    fig.update_layout(
        paper_bgcolor=BGCOLOR,
        plot_bgcolor=BGCOLOR,
        margin=dict(t=100, b=10, r=10, l=10),
        font={'size': 20},
        hoverlabel={'font_size': 20}
    )
    fig.update_traces(textfont_color='rgb(54,54,54)')

    return fig

@app.callback(
    [Output('exposure-sunburst', "figure"),
    Output('exposure-table', "data"),
    Output("exposure-table", "tooltip_data")
    ],

    [Input("detailed", "value"), 
    Input('signal', 'children')])
def exposure(detailed, signal):
    with open('data/composition.json') as f:
        data = json.load(f)
    
    countries_data = pd.read_csv('assets/countries.csv')
    countries = pd.DataFrame({'country':list(data['countries'].keys()), 'ratio':list(data['countries'].values())})
    countries = countries.merge(countries_data[['country', 'sub-region']], left_on='country', right_on='country')
    
    path = ['sub-region', 'country'] if detailed else ['sub-region']
    countries_fig = px.sunburst(countries, path=path, values='ratio')
    countries_fig.update_traces(hovertemplate='<b>%{label}: %{value}%</b>')

    sectors_map= {
            "Technology": "Sensitive",
            "Real Estate": "Cyclical",
            "Utilities": "Defensive",
            "Consumer Cyclical": "Cyclical",
            "Communication Services": "Sensitive",
            "Financial Services": "Cyclical",
            "Industrials": "Sensitive",
            "Healthcare": "Defensive",
            "Consumer Defensive": "Defensive",
            "Basic Materials": "Cyclical",
            "Energy": "Sensitive"
        }
    main_sector = [sectors_map[sector] for sector in list(data['sectors'].keys())]
    sectors = pd.DataFrame({'main_sector':main_sector, 'sector':list(data['sectors'].keys()), 'ratio':list(data['sectors'].values())})
    path = ['main_sector', 'sector'] if detailed else ['main_sector']

    colors = px.colors.qualitative.Plotly
    color_map = {sector: color for sector, color in zip(set(main_sector), colors)}
    sectors_fig = px.sunburst(sectors, path=path, values='ratio', color='main_sector', color_discrete_map=color_map)
    sectors_fig.update_layout(showlegend=False)
    sectors_fig.update_traces(hovertemplate='<b>%{label}: %{value}%</b>')

    font = dict(size=30, color='#ffffff', family='Lato')

    fig = make_subplots(rows=1, cols=2, specs=[[{"type": "domain"}, {"type": "domain"}]],
                            subplot_titles=(f"Regions", f"Sectors"))
    fig.add_trace(countries_fig['data'][0], row=1, col=1)
    fig.add_trace(sectors_fig['data'][0], row=1, col=2)
    for i in fig['layout']['annotations']:
        i['font'] = font

    fig.update_layout(
        paper_bgcolor=BGCOLOR,
        plot_bgcolor=BGCOLOR,
        margin=dict(t=100, b=10, r=10, l=10),
        font={'size': 20, 'color':'rgb(234,234,234)'},
        hoverlabel={'font_size': 20},
        showlegend=False
    )
    fig.update_traces(textfont_color='rgb(54,54,54)')

    holdings_types = [data['holdings_types'][holding] for holding in data['holdings'].keys()]
    holdings = pd.DataFrame({'holding':list(data['holdings'].keys()), 'ratio':list(data['holdings'].values()), 'type':holdings_types})
    holdings = holdings.iloc[0:20] if detailed else holdings.iloc[0:10]
    tooltip_data = [{'holding': holding} for holding in holdings['holding']]

    return fig, holdings.to_dict('records'), tooltip_data

app.layout = serve_layout

if __name__ == '__main__':
    app.run_server(debug=debug)
