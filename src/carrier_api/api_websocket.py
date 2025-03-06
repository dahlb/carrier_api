import asyncio
from asyncio import sleep, create_task, CancelledError, get_event_loop, current_task
from logging import getLogger
from collections.abc import Callable
from random import random

from aiohttp import WSMsgType, ClientWebSocketResponse

_LOGGER = getLogger(__name__)


class ApiWebsocket:
    websocket: ClientWebSocketResponse | None = None
    running = None
    async_callbacks: list[Callable] = []
    task_heartbeat = None
    task_listener = None

    def __init__(
            self,
            api_connection_graphql
    ):
        self.api_connection_graphql = api_connection_graphql
        self.api_connection_graphql.api_websocket = self

    def callback_add(self, async_callback):
        self.async_callbacks.append(async_callback)

    def callback_remove(self, async_callback):
        self.async_callbacks.remove(async_callback)

    async def loop_heartbeat(self) -> None:
        task_name = "unknown"
        current_task_instance = current_task()
        if current_task_instance is not None:
            task_name = current_task_instance.get_name()
        running = True
        while running:
            try:
                if self.websocket is not None:
                    await self.websocket.send_json({"action": "keepalive"})
                    _LOGGER.debug(f"ws: kept alive in {task_name}")
                else:
                    _LOGGER.debug(f"ws: keep alive skipped as no socket available in {task_name}")
            except CancelledError:
                running = False
            except Exception as error:
                _LOGGER.exception("ws heartbeat error", exc_info=error)
            await sleep(55)

    async def create_task_heartbeat(self) -> None:
        self.task_heartbeat = get_event_loop().create_task(self.loop_heartbeat(), name=f"carrier_api_ws_heartbeat:{random()}")

    async def listener(self) -> None:
        await self.api_connection_graphql.check_auth_expiration()
        async with self.api_connection_graphql.api_session.ws_connect(
                f"wss://realtime.infinity.iot.carrier.com/?Token={self.api_connection_graphql.access_token}") as self.websocket:
            if self.task_heartbeat is None:
                await self.create_task_heartbeat()
            if self.websocket is not None:
                async for msg in self.websocket:
                    if msg.type == WSMsgType.TEXT:
                        if msg.data == 'close cmd':
                            await self.websocket.close()
                            break
                        else:
                            for async_callback in self.async_callbacks:
                                await async_callback(msg.data)
                    elif msg.type == WSMsgType.ERROR:
                        break
            _LOGGER.debug("ws: closed")
            self.websocket = None
            if self.task_heartbeat is not None:
                self.task_heartbeat.cancel()
            self.task_heartbeat = None

    async def loop_listener(self) -> None:
        self.running = True
        while self.running:
            try:
                _LOGGER.debug("websocket task listening")
                await self.listener()
                _LOGGER.debug("websocket task ending")
            except CancelledError:
                self.running = False
                _LOGGER.debug("websocket task cancelled")
            except Exception as websocket_error:
                _LOGGER.exception("websocket task exception", exc_info=websocket_error)

    async def create_task_listener(self) -> None:
        self.task_listener = create_task(self.loop_listener(), name="carrier_api_ws")

    async def send_reconcile(self) -> None:
        if self.websocket is not None:
            await self.websocket.send_json({"action": "reconcile"})
            _LOGGER.debug("ws: reconciled")
        else:
            _LOGGER.debug("ws: not reconciled (websocket) missing")
