# run with "python3 src/carrier_api/stub.py"
import logging
from asyncio import sleep, create_task
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
from src.carrier_api.api_websocket_data_updater import WebsocketDataUpdater
from src.carrier_api.const import FanModes


async def main():
    username = input("username: ")
    password = getpass()
    api_connection = None
    try:
        api_connection = ApiConnectionGraphql(username=username, password=password)
        systems = await api_connection.load_data()
        print([system.__repr__() for system in systems])

        async def listener():
            async def output(message):
                print([system.__repr__() for system in systems])

            ws_data_updater = WebsocketDataUpdater(systems=systems)
            api_websocket = api_connection.api_websocket
            if api_websocket is None:
                raise RuntimeError("api_websocket was not initialized")
            api_websocket.callback_add(ws_data_updater.message_handler)
            api_websocket.callback_add(output)
            await api_websocket.create_task_listener()

        listener_task = create_task(listener(), name="listener")
        logger.debug("started task %s", listener_task.get_name())

        zones = systems[0].config.zones
        if not zones:
            raise RuntimeError("No config zones available")

        await api_connection.set_config_manual_activity(
            system_serial=systems[0].profile.serial,
            zone_id=zones[0].api_id,
            heat_set_point="73",
            cool_set_point="80",
            fan_mode=FanModes.LOW,
        )
        await sleep(500)
    finally:
        if api_connection is not None:
            await api_connection.cleanup()


asyncio.run(main())
