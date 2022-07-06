from gql import gql, Client
from gql.transport.aiohttp import AIOHTTPTransport
import requests
import pandas as pd
import argparse
import datetime as dt
from datetime import datetime, timedelta
import time 
import json

def statsQuery(gte, lte, address):
  query = gql(
    '''
    query($address: String!, $gte: Date, $lte: Date) {
      contract(address: $address) {
        address
       
        ... on ERC721Contract {
          name
         
          stats(timeRange: { gte: $gte, lte: $lte }) {
            average
            ceiling
            floor
            totalSales
            volume
          }
        }
      }
    }
  ''')
  parameters = {"address": address, "gte":gte, "lte":lte}
  return query, parameters

def transactionQuery(after):
    if after:
      return gql(
      """
      query Vayner ($filter: LogsFilterInputType, $first: Int!, $after: String!){
 logs(first: $first, after: $after, filter: $filter) {
    edges {
      cursor
      node {
        contractAddress
        fromAddress
        toAddress
        estimatedConfirmedAt
        type
        token {tokenId}
       transactionHash
        ... on OrderLog {
          marketplace
          priceInEth
        }
      }
    }
  }
}
  """
  )
    else:
      return gql(
      """
      query Vayner ($filter: LogsFilterInputType, $first: Int!){
 logs(first: $first, filter: $filter) {
    edges {
      cursor
      node {
        contractAddress
        fromAddress
        toAddress
        estimatedConfirmedAt
        type
        token {tokenId}
       transactionHash
        ... on OrderLog {
          marketplace
          priceInEth
        }
      }
    }
  }
}
  """
  )

def transactionsFromICY(query, after, contracts, estconfirmed):
  
  transport = AIOHTTPTransport(url='https://graphql.icy.tools/graphql', headers={'x-api-key': 'f59a44bd-c4a7-457f-8844-37f911577970'})

  client = Client(transport=transport, fetch_schema_from_transport=True)
  params = { 
  "first":1000,
  "after":after,
  "filter": {
    "contractAddress": {"in": contracts},
    "type": {'eq': "ORDER"},
    "estimatedConfirmedAt": estconfirmed
        }
  }
  result = client.execute(query, variable_values=params)
  return result

def processStatResult(result, lte, lookback):
  # average,ceiling,floor,totalSales,volume
  x = {
  'datapull_ds':dt.date.today().strftime('%Y-%m-%d')
  ,'ds': lte
  , 'lookback': lookback
  , 'address': result.get('contract').get('address')
  , 'name': result.get('contract').get('name')
  }
  if result.get('contract').get('stats'):
    y = result.get('contract').get('stats')
  else:
    y = {
    'average':0
    ,'ceiling':0
    ,'floor':0
    ,'totalSales':0
    ,'volume':0
    }
  return {**x,**y}

def getFirstCursor(contracts):
  query = transactionQuery(None)
  start = (datetime.today()-timedelta(days=1)).strftime('%Y-%m-%d')
  estC = {"gte":"{0}".format(start+"T00:00:00.000Z")}
  transport = AIOHTTPTransport(url='https://graphql.icy.tools/graphql', headers={'x-api-key': 'f59a44bd-c4a7-457f-8844-37f911577970'})
  client = Client(transport=transport, fetch_schema_from_transport=True)
  params = { 
  "first":50,
  "filter": {
    "contractAddress": {"in": contracts},
    "type": {'eq': "ORDER"},
    "estimatedConfirmedAt": estC
        }
  }
  result = client.execute(query, variable_values=params)
  print('first cursor: ', result.get('logs').get('edges')[0])
  return result.get('logs').get('edges')[0].get('cursor')

def processTransactionResult(result):
  x = [{**i.get('node'),**{'cursor':i.get('cursor')}} for i in result.get('logs').get('edges')]
  for i in x:
    try:
      i['token'] = i.get('token').get('tokenId')
    except:
      i['token'] = -1
  return x

def processDF(df):
  df['collection'] = df['contractAddress'].map(contract_mapping)
  df['notes'] = df['contractAddress'].map(royalty_dict)
  df['notes']=df['notes'].fillna('n/a')
  df.marketplace=df.marketplace.fillna('UNK')
  df['ds'] = df['estimatedConfirmedAt'].apply(lambda x: x.split('T')[0])
  df['transactionHash'] = df['transactionHash'].fillna(df['fromAddress']+df['toAddress']+df['ds'])
  return df

def dedupeDF(list_of_dataframes, dedup_cols, sort_cols):
  newdf = pd.concat(list_of_dataframes)
  newdf = newdf.drop_duplicates(subset=dedup_cols)
  newdf = newdf.sort_values(by=sort_cols, ascending=False)
  return newdf


if __name__ == '__main__':

  parser = argparse.ArgumentParser()
  parser.add_argument("--endpoint", help='e.g. transactions, stats')
  parser.add_argument("--lookback", help='list of lookback windows e.g 1,7,30')
  parser.add_argument("--start", help='')
  parser.add_argument("--end", help='')
  parser.add_argument("--backfill", help='')
  args = parser.parse_args()
  
  with open('data/royalty_dict.json') as json_file:
    royalty_dict = json.load(json_file)

  with open('data/address_dict.json') as json_file:
    address_dict = json.load(json_file)

  contracts = list(address_dict.keys()) 
  contracts_with_royalty_contracts = contracts + list(royalty_dict.keys())
  contract_mapping = {**{k:'royalty' for k,v in royalty_dict.items()}, **address_dict}
  transaction_df = pd.read_csv('data/icy_transactions.csv', keep_default_na=False)    

  if args.endpoint == 'transactions':    
    
    estconfirmed = {"gte":"{0}".format(transaction_df.estimatedConfirmedAt[0])}
    record_list = []
    after=getFirstCursor(contracts_with_royalty_contracts)
    continue_flag = True
    while continue_flag:
      query = transactionQuery(after)
      result = transactionsFromICY(query, after, contracts_with_royalty_contracts, estconfirmed) 
      data = processTransactionResult(result)
      if data != []:
        print(data[0].get('estimatedConfirmedAt'), data[-1].get('estimatedConfirmedAt'))
        record_list += data
        after = result.get('logs').get('edges')[-1].get('cursor')
        time.sleep(1)
      else:
        continue_flag=False
    df = pd.DataFrame.from_records(record_list)
    df = processDF(df)
    transaction_df = processDF(transaction_df)
    ndf = dedupeDF([df,transaction_df], ['contractAddress', 'fromAddress', 'toAddress', 'token', 'ds'], 'estimatedConfirmedAt')
    # fix weird notes bug
    ndf['notes_'] = ndf['notes'].apply(lambda x: x+' ') 
    ndf['notes'] = ndf['notes_']
    ndf.drop('notes_', axis=1, inplace=True)
    # write to csv
    ndf.to_csv('data/icy_transactions.csv', index=False, header=list(ndf.columns))

  if args.endpoint=='stats':
    transport = AIOHTTPTransport(url='https://graphql.icy.tools/graphql', headers={'x-api-key': 'f59a44bd-c4a7-457f-8844-37f911577970'})
    client = Client(transport=transport, fetch_schema_from_transport=True)
    
    old_df = pd.read_csv('data/icy_stats.csv')
    if args.start == 'daily':
      start = (datetime.today()-timedelta(days=1)).strftime('%Y-%m-%d')
    else:
      start = args.start
    start_ = dt.datetime.strptime(start, '%Y-%m-%d')
    backfill = int(args.backfill) or 0
    lookbacks = [int(i) for i in args.lookback.split(',')] if args.lookback else [1]
    dt_range = [start_ - timedelta(days=x) for x in range(backfill)]
    result_list = []
    for contract in contracts_with_royalty_contracts:
      for lookback in lookbacks:
        for d in dt_range:
          print(contract, d, lookback)
          exist_df = old_df.loc[(old_df.ds==d.strftime('%Y-%m-%d')) & (old_df.lookback==lookback) & (old_df.address==contract)]
          if len(exist_df) > 0:
            print('data exists previously')
            continue 
          gte = (d - timedelta(days=lookback)).strftime('%Y-%m-%d')
          lte = d.strftime('%Y-%m-%d')
          query, parameters = statsQuery(gte, lte, contract)
          try:
            result = client.execute(query, variable_values=parameters)
            data = processStatResult(result, lte, lookback)
            print(data)
            result_list.append(data)
          except:
            df = pd.DataFrame.from_records(result_list)
            ndf = dedupeDF([df,old_df],['ds', 'lookback', 'address'], ['ds', 'address','lookback'])
            ndf.to_csv('data/icy_stats.csv', index=False, header=list(ndf.columns))
            print('breaking from API error')
            break
          time.sleep(5)
    df = pd.DataFrame.from_records(result_list)
    ndf = dedupeDF([df,old_df],['ds', 'lookback', 'address'], ['ds', 'address','lookback'])
    ndf.to_csv('data/icy_stats.csv', index=False, header=list(ndf.columns))
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
