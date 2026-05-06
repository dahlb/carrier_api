"""Manual Carrier API smoke-test script for local development.

Run with ``python3 src/carrier_api/stub.py`` from the repository root.
"""

import asyncio
from asyncio import create_task, sleep
from getpass import getpass
import logging
from pathlib import Path
import sys

path_src = Path(__file__).parents[1]
sys.path.append(str(path_src))


logger = logging.getLogger("carrier_api")
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)


from carrier_api.api_connection_graphql import ApiConnectionGraphql
from carrier_api.api_websocket_data_updater import WebsocketDataUpdater
from carrier_api.const import FanModes


async def read_input(prompt: str) -> str:
    """Read terminal input without blocking the event loop.

    Args:
        prompt: Prompt to display to the user.

    Returns:
        The entered input text.
    """
    return await asyncio.to_thread(input, prompt)


async def read_password() -> str:
    """Read a password without blocking the event loop.

    Returns:
        The password entered by the user.
    """
    return await asyncio.to_thread(getpass)


async def main() -> None:
    """Log in, load systems, start websocket updates, and send one manual update.

    The script prompts for Carrier credentials, prints the loaded systems,
    registers websocket callbacks, sends a sample manual activity mutation to the
    first configured zone, and then keeps the process alive long enough to watch
    realtime messages.
    """
    username = await read_input("username: ")
    password = await read_password()
    api_connection = None
    try:
        api_connection = ApiConnectionGraphql(username=username, password=password)
        systems = await api_connection.load_data()
        print([system.as_dict() for system in systems])

        async def listener() -> None:
            """Register websocket callbacks and start the listener task."""

            async def output(message: str) -> None:
                """Print current in-memory systems after a websocket message.

                Args:
                    message: Raw websocket message text. The callback does not
                        inspect the payload because the data updater callback has
                        already merged it into the shared system objects.
                """
                print([system.as_dict() for system in systems])

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
