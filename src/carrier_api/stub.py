# run with "python3 src/carrier_api/stub.py"
import logging
from getpass import getpass
from pathlib import Path
import sys

import asyncio

path_root = Path(__file__).parents[2]
sys.path.append(str(path_root))


logger = logging.getLogger("src.carrier_api")
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)


from src.carrier_api.api_connection_graphql import ApiConnectionGraphql

async def main():
    username = input("username: ")
    password = getpass()
    api_connection = None
    try:
        api_connection = ApiConnectionGraphql(username=username, password=password)
        await api_connection.login()
        systems = await api_connection.load_data()
        for system in systems:
            print(system)
    finally:
        if api_connection is not None:
            await api_connection.cleanup()


asyncio.run(main())