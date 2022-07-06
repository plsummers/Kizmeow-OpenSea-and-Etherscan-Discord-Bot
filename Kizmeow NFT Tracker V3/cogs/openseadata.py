# python osea_data_1.py --collections budverse-cans-heritage-edition,pepsi-mic-drop
import requests
import pandas as pd
import argparse
import datetime as dt
import time 
from icytools import dedupeDF
import json

pd.set_option('display.max_columns', 500)
pd.set_option('display.max_colwidth', 20)

def fieldsFromAPI(c):
	token = c.get('token_id', {}) # e.g. 527 - specifies token
	permalink = c.get('permalink', {})
	top_bid=c.get('top_bid', {})
	num_sales=c.get('num_sales', {})
	owner = c.get('owner', {}).get('address', {})
	collection_slug = c.get('collection', {}).get('slug', {})
	if c.get('sell_orders'):
		if c.get('sell_orders')[0].get('expiration_time',1)>time.time():
			priceInEth=round(float(c.get('sell_orders')[0].get('current_price'))/(10**18),5)
		else:
			priceInEth=None
	else:
		priceInEth=None
	try:
		last_sale_usd= c.get('last_sale').get('payment_token').get('usd_price') if (c.get('last_sale') or None) is not None else None
		last_sale_eth= c.get('last_sale').get('payment_token').get('eth_price') if (c.get('last_sale') or None) is not None else None
		last_sale_from_address = c.get('last_sale').get('transaction').get('from_account').get('address')
		last_sale_from_user = c.get('last_sale').get('transaction').get('from_account').get('user').get('username')
		last_sale_to_address = c.get('last_sale').get('transaction').get('to_account').get('address')
		last_sale_to_user = c.get('last_sale').get('transaction').get('to_account').get('user').get('username')
	except:
		last_sale_usd = None
		last_sale_eth = None
		last_sale_from_address = None
		last_sale_from_user = None
		last_sale_to_address = None
		last_sale_to_user = None
	traits = c.get('traits', {})
	last_sale_ds = c.get('created_date', {})
	contractAddress = c.get('asset_contract', {}).get('address', {})
	datapull_ds = dt.date.today().strftime('%Y-%m-%d')
	asset_data = {'token': token, 'owner':owner, 'collection': collection_slug, 'contractAddress':contractAddress, 'datapull_ds': datapull_ds,  'permalink': permalink, 'num_sales': num_sales, 'traits': traits, 'priceInEth':priceInEth}
	return asset_data

def dfFromCollection(asset_contract_address, headers, test):
	asset_list = []	
	offset=0
	pagination_flag=True
	while pagination_flag==True:
		url = "https://api.opensea.io/api/v1/assets?order_direction=desc&offset={1}&asset_contract_address={0}&limit=50".format(asset_contract_address, offset)
		response = requests.request("GET", url, headers=headers)
		if response.status_code != 200:
			print(response.text)
			break
		assets = dict(response.json()).get('assets', {})
		for c in assets:
			asset_data = fieldsFromAPI(c)
			asset_data['collection']=contract_mapping.get(asset_contract_address,{})
			asset_list.append(asset_data)
		if response.text != '{"assets":[]}':
			offset += 50
			time.sleep(5)
		else:
			pagination_flag=False
		if test:
			break
	df = pd.DataFrame.from_records(asset_list, columns=asset_list[0].keys()).sort_values(by='token', ascending=True) # ['token', 'permalink', 'last_sale_usd', 'last_sale_eth', 'top_bid', 'num_sales']
	df = df.fillna(value=0)
	return df, assets

def StatsByCollection(collection, addToday=True, addCollection=True):
	url='https://api.opensea.io/api/v1/collection/{}/stats'.format(collection)
	response = requests.request("GET", url)
	stats = dict(response.json()).get("stats", {})
	if addToday:
		stats['ds'] = dt.date.today().strftime("%Y-%m-%d")
	if addCollection:
		stats['collection'] = collection
	df = pd.DataFrame.from_records([stats])
	return df

def ListingStatus(collection, headers):
	url = "https://api.opensea.io/api/v1/events?collection_slug={}&event_type=transfer&only_opensea=false&offset=0&limit=100".format(collection)
	response = requests.request("GET", url, headers=headers)
	
	return dict(response.json()).get("asset_events",{})

def mapLastSale(df, tf): # could be refactored to take column as function parameter
	contract = df.contractAddress[0]
	tf_ = tf.loc[tf.contractAddress==contract]
	map_price_dict= tf.loc[tf.contractAddress==contract].groupby('token').first()['priceInEth'].to_dict()
	df['last_sold_price_eth'] = df['token'].map(map_price_dict)
	df['last_sold_price_eth'].fillna(value=0, inplace=True)
	return df


if __name__ == '__main__':
	
	parser = argparse.ArgumentParser()
	parser.add_argument("--collections", help='e.g. data/test1.csv')
	parser.add_argument("--outfolder", help='e.g. data/test1.csv')
	parser.add_argument("--test", help='if true use one row')
	parser.add_argument("--outfile_prefix", help='prefix for outfile')
	parser.add_argument("--endpoint", help='e.g. stats or token')
	args = parser.parse_args()
	api_key = '610c839f631b446f98c8ed1f2611d89e'
	headers = {
	"Accept": "application/json",
	"X-API-KEY": '610c839f631b446f98c8ed1f2611d89e'
		#"X-API-KEY": '61b26b9037b34d19bfdac807abff6140'
	}
	
	with open('data/royalty_dict.json') as json_file:
		royalty_dict = json.load(json_file)

	with open('data/address_dict.json') as json_file:
		address_dict = json.load(json_file)

	contracts = list(address_dict.keys()) 
	contracts_with_royalty_contracts = contracts + [i.lower() for i in royalty_dict.keys()]
	contract_mapping = {**{k:'royalty' for k,v in royalty_dict.items()}, **address_dict}
	transaction_df = pd.read_csv('data/icy_transactions.csv', keep_default_na=False)    
	tf = pd.read_csv('data/icy_transactions.csv', dtype={'token':'string'})
	
	if args.endpoint == 'token':
		list_of_dataframes = []
		for asset_contract_address in contracts_with_royalty_contracts:
			print(contract_mapping.get(asset_contract_address))
			df_, assets = dfFromCollection(asset_contract_address, headers, args.test)
			df_ = mapLastSale(df_, tf)
			list_of_dataframes.append(df_)        
		df = pd.concat(list_of_dataframes)
		ndf = dedupeDF([df],['token','contractAddress'], ['collection'])
		ndf['notes'] = df['contractAddress'].map(royalty_dict)
		ndf['notes'].fillna(value=' ', inplace=True)
		ndf.to_csv('data/token_metadata.csv', index=False, header=list(ndf.columns))

	if args.endpoint == 'stats':
		list_of_dataframes=[]
		for collection in collections:
			_df = StatsByCollection(collection, addToday=True, addCollection=True)
			list_of_dataframes.append(_df)
		df = pd.concat(list_of_dataframes)
		df.to_csv('data/os_stats.csv', index=False, header=list(df.columns))
Footer
© 2022 GitHub, Inc.
Footer navigation
Terms
Privacy
Security
Status
Docs
Contact GitHub
Pricing
API
Training
Blog
About
