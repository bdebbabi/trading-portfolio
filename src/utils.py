import pandas as pd
from datetime import datetime


def get_transactions(creation_date, webparser):
	degiro = get_degiro_transactions(creation_date, webparser)
	coinbase = get_coinbase_transactions(webparser)
	boursorama = get_boursorama_transactions(webparser)

	transactions = pd.concat([degiro, coinbase, boursorama])
	transactions = transactions.sort_values('date').reset_index(drop=True)
	transactions.to_csv('data/transactions.csv', index=False)
	return transactions


def get_degiro_transactions(creation_date, webparser):
	account, transactions = webparser.get_degiro_data(creation_date)
	account.to_csv('data/degiro_account.csv')
	transactions.to_csv('data/degiro_transactions.csv')
	
	renaming = {'Date': 'date', 'Heure': 'hour','Produit': 'asset', 'Code ISIN': 'id'}
	account_renaming = {'Description': 'description',
						'Unnamed: 8': 'value', 'Unnamed: 10': 'balance', **renaming}
	transaction_renaming = {'Quantité': 'quantity', 'Place boursiè': 'exchange',
							'Montant': 'value', 'Frais de courtage': 'fees', **renaming}
	account.rename(columns=account_renaming, inplace=True)
	transactions.rename(columns=transaction_renaming, inplace=True)

	account['value'] = account['value'].str.replace(',', '.').astype(float)
	account['balance'] = account['balance'].str.replace(',', '.').astype(float)

	account['date'] = pd.to_datetime(
		account['date']+account['hour'], format='%d-%m-%Y%H:%M')
	change = account[(account['description'] ==
					  'Opération de change - Débit') & (account['value'] > 0)]

	dividends = account[(account['description'] == 'Dividende') &
						(account['value'] == account['balance']) &
						(account['date'] <= change['date'].max())]

	dividends = dividends.reset_index(drop=True)
	dividends['value'] = list(change['value'])

	dividends = pd.concat((dividends, account[(account['description'] == 'Dividende') & (
		account['value'] != account['balance'])]))

	transactions['date'] = pd.to_datetime(
		transactions['date']+transactions['hour'], format='%d-%m-%Y%H:%M')

	id_to_asset = dict(zip(transactions.id, transactions.asset))
	dividends['asset'] = dividends.id.map(id_to_asset)

	types, symbols = webparser.get_asset_data(set(transactions.groupby(['id', 'exchange', 'asset']).groups.keys()))
	transactions = pd.concat([transactions, dividends]).sort_values(
		'date', ignore_index=True)
	
	
	transactions = transactions[['date', 'asset', 'id','quantity', 'value', 'fees', 'description','exchange']]
	transactions['via'] = 'Degiro'
	transactions.description[transactions.quantity < 0] = 'sell'
	transactions.description[transactions.quantity > 0] = 'buy'
	transactions.description[transactions.description =='Dividende'] = 'dividend'

	transactions['symbol'] = transactions.id.map(symbols)
	transactions['type'] = transactions.id.map(types)
	transactions.quantity.fillna(0, inplace=True)
	transactions.fees.fillna(0, inplace=True)
	return transactions


def get_coinbase_transactions(webparser):
	client = webparser.client
	accounts = client.get_accounts(limit=100)
	wallets = {}

	for acc in accounts['data']:
		if float(acc['balance']['amount']) != 0:
			wallets[acc['currency']] = acc['id']
	res = []
	for wallet in wallets:
		transactions = client.get_transactions(wallet)['data']
		for line in transactions[::-1]:
			transaction = {}
			transaction_fee = 0
			price = 0
			if line['type'] == 'buy':
				buy = client.get_buy(wallet, line['buy']['id'])
				fees = buy['fees']
				price = buy['subtotal']['amount']
				for fee in fees:
					transaction_fee += float(fee['amount']['amount'])
			transaction['date'] = datetime.strptime(line['created_at'], '%Y-%m-%dT%H:%M:%SZ')
			transaction['asset'] = ' ' .join(line['details']['title'].split(' ')[1:])
			transaction['id'] = line['amount']['currency']
			transaction['quantity'] = float(line['amount']['amount'])
			transaction['value'] = - float(price)
			transaction['fees'] = - transaction_fee
			transaction['description'] = line['type']
			transaction['via'] = 'Coinbase'
			transaction['type'] = 'Crypto'
			transaction['symbol'] = line['amount']['currency']
			res.append(transaction)
	return pd.DataFrame(res)


def get_boursorama_transactions(webparser):
	transactions = pd.read_csv('data/boursorama_transactions.csv', sep=',')
	types, symbols = webparser.get_asset_data(set(transactions.groupby(['id', 'exchange', 'asset']).groups.keys()))
	transactions['symbol'] = transactions.id.map(symbols)
	transactions['type'] = transactions.id.map(types)
	transactions['date'] = pd.to_datetime(transactions['date'], format='%d-%m-%Y %H:%M')

	return transactions
