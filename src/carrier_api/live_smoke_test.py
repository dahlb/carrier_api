"""Manual live Carrier API smoke-test script for local development.

This module is an interactive development harness, not part of the automated
pytest suite. It connects to the real Carrier API with credentials entered at
the terminal, loads the account's configured systems, prints their current
structured state, subscribes to websocket updates, and sends one sample manual
activity update to the first available zone.

Use this when developing or debugging behavior that needs a live Carrier
account, such as captured GraphQL payloads, websocket reconciliation, manual
activity mutations, or field changes that are hard to represent from stored
fixtures alone. Do not use it as a substitute for adding deterministic tests in
``tests/``; any fixed behavior should still be covered by pytest fixtures or
unit tests where practical.

The script intentionally prints raw inspected state to the console and mutates
``sys.path`` so it can be run directly from a source checkout without installing
the package first. It may change a thermostat's active settings because it calls
``set_config_manual_activity`` with sample heat, cool, and fan values.

Run it through the repository helper script so it starts from the project root
and uses the repository virtual environment:
``scripts/live_smoke_test``.
"""

import asyncio
from asyncio import CancelledError, Task, sleep
from contextlib import suppress
from datetime import datetime
from getpass import getpass
import logging
from pathlib import Path
import sys

path_src = Path(__file__).parents[1]
sys.path.append(str(path_src))

from carrier_api.api_connection_graphql import ApiConnectionGraphql
from carrier_api.api_websocket_data_updater import WebsocketDataUpdater
from carrier_api.const import FanModes

logger = logging.getLogger("carrier_api")
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)

SMOKE_TEST_WAIT_SECONDS = 300

INTRO_TEXT = """\
This smoke test connects to the live Carrier API.
It loads your configured systems, prints their current state, starts websocket
updates, sends one sample manual activity update to the first available zone,
and then waits so incoming realtime messages can be observed.

This script will change thermostat settings on the first available zone: it
sets the heat set point to 73, the cool set point to 80, and the fan mode to low.
After that update, it waits 5 minutes, so the terminal
will appear to pause while it listens for websocket messages.

Enter the Carrier or Bryant account email address and password that you
use for the official thermostat app. These credentials are read from this
terminal session only; the script does not store them.
"""


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


def current_timestamp() -> str:
    """Return the current local date and time for console output.

    Returns:
        Local timestamp formatted for human-readable smoke-test logs.
    """
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


async def wait_for_cancelled_task(task: Task[None] | None) -> None:
    """Cancel and await a background task if it is still running.

    Args:
        task: Background task to cancel and drain.
    """
    if task is None:
        return
    if not task.done():
        task.cancel()
    with suppress(CancelledError):
        await task


async def shutdown_websocket_listener(api_connection: ApiConnectionGraphql) -> None:
    """Stop websocket background tasks before closing the aiohttp session.

    Args:
        api_connection: API connection whose websocket listener should be
            stopped before the underlying HTTP session is closed.
    """
    api_websocket = api_connection.api_websocket
    if api_websocket is None:
        return

    api_websocket.running = False
    if api_websocket.websocket is not None and not api_websocket.websocket.closed:
        await api_websocket.websocket.close()
    await wait_for_cancelled_task(api_websocket.task_listener)
    await wait_for_cancelled_task(api_websocket.task_heartbeat)
    api_websocket.task_listener = None
    api_websocket.task_heartbeat = None


async def main() -> None:
    """Log in, load systems, start websocket updates, and send one manual update.

    The script prompts for Carrier credentials, prints the loaded systems,
    registers websocket callbacks, sends a sample manual activity mutation to the
    first configured zone, and then keeps the process alive long enough to watch
    realtime messages.
    """
    print(INTRO_TEXT)
    print()
    username = await read_input("Carrier or Bryant account email address: ")
    password = await read_password()
    api_connection = None
    completed = False
    print()
    print(f"Starting Smoke Test at {current_timestamp()}")
    print("--------------------------------------------------------------------------")
    print()
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

        await listener()
        logger.debug("started websocket listener task")

        if not systems:
            raise RuntimeError("No systems available")
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
        print()
        print("--------------------------------------------------------------------------")
        print("The script will now wait 5 minutes, so websocket messages can be observed")
        print("--------------------------------------------------------------------------")
        print()
        await sleep(SMOKE_TEST_WAIT_SECONDS)
        completed = True
    finally:
        if api_connection is not None:
            await shutdown_websocket_listener(api_connection)
            await api_connection.cleanup()
        if completed:
            print()
            print("--------------------------------------------------------------------------")
            print(f"Smoke test complete at {current_timestamp()}")


if __name__ == "__main__":
    asyncio.run(main())
