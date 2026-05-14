"""Websocket listener and callback manager for Carrier realtime messages."""

from __future__ import annotations

from asyncio import CancelledError, Task, create_task, current_task, sleep
from collections.abc import Awaitable, Callable
from logging import getLogger
from random import random
from typing import TYPE_CHECKING

from aiohttp import ClientWebSocketResponse, WSMsgType

if TYPE_CHECKING:
    from .api_connection_graphql import ApiConnectionGraphql

_LOGGER = getLogger(__name__)

AsyncCallback = Callable[[str], Awaitable[None]]


class ApiWebsocket:
    """Manage Carrier realtime websocket connection state and callbacks."""

    def __init__(self, api_connection_graphql: ApiConnectionGraphql) -> None:
        """Create a websocket manager bound to a GraphQL API connection.

        Args:
            api_connection_graphql: Authenticated API connection used for token
                refresh and websocket session creation.
        """
        self.websocket: ClientWebSocketResponse | None = None
        self.running: bool | None = None
        self.async_callbacks: list[AsyncCallback] = []
        self.task_heartbeat: Task[None] | None = None
        self.task_listener: Task[None] | None = None
        self.api_connection_graphql = api_connection_graphql
        self.api_connection_graphql.api_websocket = self

    def callback_add(self, async_callback: AsyncCallback) -> None:
        """Register an async callback for incoming text messages.

        Args:
            async_callback: Coroutine function that receives the raw websocket
                message text.
        """
        self.async_callbacks.append(async_callback)

    def callback_remove(self, async_callback: AsyncCallback) -> None:
        """Remove a previously registered async callback.

        Args:
            async_callback: Callback previously added with ``callback_add``.

        Raises:
            ValueError: If the callback is not currently registered.
        """
        self.async_callbacks.remove(async_callback)

    async def loop_heartbeat(self) -> None:
        """Send keepalive messages until the heartbeat task is cancelled.

        The Carrier websocket expects periodic keepalive frames. This loop logs
        transient send failures and exits cleanly when asyncio cancels the task.
        """
        task_name = "unknown"
        current_task_instance = current_task()
        if current_task_instance is not None:
            task_name = current_task_instance.get_name()
        running = True
        while running:
            try:
                if self.websocket is not None:
                    await self.websocket.send_json({"action": "keepalive"})
                    _LOGGER.debug("ws: kept alive in %s", task_name)
                else:
                    _LOGGER.debug("ws: keep alive skipped as no socket available in %s", task_name)
            except CancelledError:
                running = False
            except Exception as error:
                _LOGGER.exception("ws heartbeat error", exc_info=error)
            await sleep(55)

    async def create_task_heartbeat(self) -> None:
        """Start the background websocket heartbeat task."""
        self.task_heartbeat = create_task(
            self.loop_heartbeat(), name=f"carrier_api_ws_heartbeat:{random()}"
        )

    async def listener(self) -> None:
        """Open the websocket and dispatch incoming text messages.

        The listener refreshes authentication if needed, starts the heartbeat,
        forwards text payloads to registered callbacks, and clears connection
        state when the socket closes.
        """
        await self.api_connection_graphql.check_auth_expiration()
        async with self.api_connection_graphql.api_session.ws_connect(
            f"wss://realtime.infinity.iot.carrier.com/?Token={self.api_connection_graphql.access_token}"
        ) as self.websocket:
            if self.task_heartbeat is None:
                await self.create_task_heartbeat()
            if self.websocket is not None:
                async for msg in self.websocket:
                    if msg.type == WSMsgType.TEXT:
                        if msg.data == "close cmd":
                            await self.websocket.close()
                            break
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
        """Keep reconnecting the websocket listener while running is enabled.

        Cancellation stops the loop. Other listener errors are logged so a later
        loop iteration can retry the websocket connection.
        """
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
        """Start the background websocket listener task."""
        self.task_listener = create_task(self.loop_listener(), name="carrier_api_ws")

    async def send_reconcile(self) -> None:
        """Request a Carrier realtime state reconciliation when connected."""
        if self.websocket is not None:
            await self.websocket.send_json({"action": "reconcile"})
            _LOGGER.debug("ws: reconciled")
        else:
            _LOGGER.debug("ws: not reconciled (websocket) missing")
