import aiohttp
import discord
from discord.ext import commands, tasks
from keys import *
import asyncio
import json
import copy

class Nft(commands.Cog):
    """
    Standard discord cog for relaying trending collections
    """

    def __init__(self, bot):
        self.bot = bot
        self.trendingAlerts.start()

    @tasks.loop(minutes=10)
    async def trendingAlerts(self):
        """
        Runs every 10 minutes to send alerts
        :return:
        """
        await self.trendingCall()


    async def getData(self, source, *args):
        """
        Traverse json, dictionaries, etc
        :param source: dictionary/json we're traversing
        :param args: key, key in key, key in key in key....
        :return:
        """
        try:
            tmp = source
            for arg in args:
                tmp = tmp[arg]
            return tmp

        except:
            print("getData failed for some reason")

    async def pushData(self, data, value, *keys):
        '''
        Assigns data[*key_path] = value

        data must not be None.  Pass an empty dict if you have no prior data.

        Example Usage:

        set_values(foo, 25, 'bar', 'baz') # Sets foo['bar']['baz'] = 25
        '''

        # We need a reference to initialize.  Can't do it for the caller.
        if data is None:
            raise ValueError(
                f"first parameter to set_values must not be None.  Pass an empty dict if you have no prior data.")

        # create a new copy of the dictionary
        newData = copy.deepcopy(data)
        # the one we jump through
        curData = newData
        # iterate through *keys
        for i in range(len(keys)):  # arg_key = hannah_montana
            curKey = keys[i]

            # last iteration, finally set the value
            if i == len(keys) - 1:
                curData[curKey] = value
                break

            # Continue recursing deeper into the nested data structure
            if curKey in curData:
                curData = curData[curKey]
            else:
                curData[curKey] = {}
                curData = curData[curKey]
        return newData

    async def osData(self, contract):
        """
        Query OS for basic information relating to
        :param contract:
        :return:
        """

        url = "https://api.opensea.io/api/v1/asset_contract/" + contract
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as r:
                if r.status == 200:
                    js = await r.json()

                    name = await self.getData(js, 'name' )
                    description = await self.getData(js, 'collection', 'description')
                    site = self.getData(js, 'external_link')
                    slug = await self.getData(js, 'collection', 'slug')
                    osCollection = "https://opensea.io/collection/" + slug

                    return name, description, site, osCollection

    async def trendingCall(self):
        """
        get trending from icy tools
        :return:
        """
        KEY = {"x-api-key": ICY_KEY}

        query = """  query TrendingCollections {
            contracts(orderBy: SALES, orderDirection: DESC) {
              edges {
                node {
                  address
                  ... on ERC721Contract {
                    name
                    stats {
                      totalSales
                      average
                      ceiling
                      floor
                      volume
                    }
                    symbol
                  }
                }
              }
            }
          }
          """
        url = "https://graphql.icy.tools/graphql"
        async with aiohttp.ClientSession() as session:
            async with session.get(url=url, json={'query': query}, headers=KEY) as r:
                if r.status == 200:
                    js = await r.json()
                    listOfTrending = await self.getData(js, "data", "contracts", "edges")

        # sort through trending for contract addresses
        for item in listOfTrending:
            tmp = await self.getData(item, "node", "address")
            name, description, site, osCollection = await self.osData(tmp)
            await self.trendingUpdate(name, description, site, osCollection)

    async def trendingUpdate(self, name, description, site, osCollection):
        embed = discord.Embed(title="Trending: " + name, description=description)
        embed.add_field(name="Website", value=site, inline=False)
        embed.add_field(name="OS Collection", value=osCollection, inline=True)
        embed.set_footer(text="Information provided by openseas and icytools")
        channel = self.bot.get_channel(int(BOT_CHANNEL))
        await channel.send(embed=embed)

def setup(bot):
    bot.add_cog(Nft(bot))
