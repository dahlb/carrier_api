"""Websocket listener and callback manager for Carrier realtime messages."""

from __future__ import annotations

from asyncio import CancelledError, Task, create_task, current_task, get_running_loop, sleep
from collections.abc import Awaitable, Callable
from logging import getLogger
from random import random
from typing import TYPE_CHECKING

from aiohttp import ClientError, ClientWebSocketResponse, WSMsgType

from .const import (
    WEBSOCKET_HEARTBEAT_INTERVAL_SECONDS,
    WEBSOCKET_RECONNECT_MAX_DELAY_SECONDS,
    WEBSOCKET_RECONNECT_MIN_DELAY_SECONDS,
    WEBSOCKET_STABLE_CONNECTION_SECONDS,
)
from .errors import CarrierApiWebsocketError

if TYPE_CHECKING:
    from .api_connection_graphql import ApiConnectionGraphql

_LOGGER = getLogger(__name__)

AsyncCallback = Callable[[str], Awaitable[None]]

# Errors a callback raises when one message cannot be parsed or applied. They
# are logged and the message is dropped, so one bad payload does not close the
# websocket and force a reconnect.
_CALLBACK_MESSAGE_ERRORS = (ValueError, KeyError, TypeError, IndexError, AttributeError)


class _CallbackError(Exception):
    """Internal wrapper used to avoid treating callback I/O as websocket I/O."""

    def __init__(self, error: ClientError | TimeoutError | OSError) -> None:
        """Initialize the callback error wrapper.

        Args:
            error: Original callback exception to re-raise outside websocket
                transport normalization.
        """
        super().__init__(str(error))
        self.error = error


class ApiWebsocket:
    """Manage Carrier realtime websocket connection state and callbacks."""

    def __init__(self, api_connection_graphql: ApiConnectionGraphql) -> None:
        """Create a websocket manager bound to a GraphQL API connection.

        Args:
            api_connection_graphql: Authenticated API connection used for token
                refresh and websocket session creation.
        """
        self.websocket: ClientWebSocketResponse | None = None
        self.running: bool = False
        self.async_callbacks: list[AsyncCallback] = []
        self.task_heartbeat: Task[None] | None = None
        self.task_listener: Task[None] | None = None
        self._connected_at: float | None = None
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
        transient send failures and lets asyncio cancellation end the task.
        """
        task_name = "unknown"
        current_task_instance = current_task()
        if current_task_instance is not None:
            task_name = current_task_instance.get_name()
        while True:
            if self.websocket is not None:
                try:
                    await self.websocket.send_json({"action": "keepalive"})
                    _LOGGER.debug("ws: kept alive in %s", task_name)
                except (ClientError, OSError, RuntimeError) as error:
                    _LOGGER.warning("ws: keepalive failed in %s: %s", task_name, error)
            else:
                _LOGGER.debug("ws: keep alive skipped as no socket available in %s", task_name)
            await sleep(WEBSOCKET_HEARTBEAT_INTERVAL_SECONDS)

    async def create_task_heartbeat(self) -> None:
        """Start the background websocket heartbeat task."""
        self.task_heartbeat = create_task(
            self.loop_heartbeat(), name=f"carrier_api_ws_heartbeat:{id(self):x}"
        )

    async def _dispatch(self, message: str) -> None:
        """Pass one text message to every registered callback.

        A callback that fails to parse or apply the message is logged and the
        remaining callbacks still run. Callback I/O errors are wrapped so the
        listener does not report them as websocket failures.

        Args:
            message: Raw websocket message text.

        Raises:
            _CallbackError: If a callback raises a network or OS error.
        """
        for async_callback in self.async_callbacks:
            try:
                await async_callback(message)
            except (ClientError, TimeoutError, OSError) as error:
                raise _CallbackError(error) from error
            except _CALLBACK_MESSAGE_ERRORS:
                _LOGGER.exception("ws: callback failed to handle message: %s", message)

    async def listener(self) -> None:
        """Open the websocket and dispatch incoming text messages.

        The listener refreshes authentication if needed, starts the heartbeat,
        forwards text payloads to registered callbacks, and clears connection
        state when the socket closes.
        """
        await self.api_connection_graphql.check_auth_expiration()
        try:
            async with self.api_connection_graphql.api_session.ws_connect(
                "wss://realtime.infinity.iot.carrier.com/"
                f"?Token={self.api_connection_graphql.access_token}"
            ) as self.websocket:
                self._connected_at = get_running_loop().time()
                _LOGGER.debug("ws: connected")
                if self.task_heartbeat is None:
                    await self.create_task_heartbeat()
                if self.websocket is not None:
                    async for msg in self.websocket:
                        if msg.type == WSMsgType.TEXT:
                            if msg.data == "close cmd":
                                await self.websocket.close()
                                break
                            await self._dispatch(msg.data)
                        elif msg.type == WSMsgType.ERROR:
                            websocket_error = self.websocket.exception()
                            if websocket_error is None:
                                raise CarrierApiWebsocketError(
                                    "Carrier websocket connection failed"
                                )
                            raise CarrierApiWebsocketError(
                                "Carrier websocket connection failed"
                            ) from websocket_error
                _LOGGER.debug("ws: closed")
        except _CallbackError as error:
            raise error.error from None
        except CarrierApiWebsocketError:
            raise
        except (ClientError, TimeoutError, OSError) as error:
            raise CarrierApiWebsocketError("Carrier websocket connection failed") from error
        finally:
            self.websocket = None
            if self.task_heartbeat is not None:
                self.task_heartbeat.cancel()
            self.task_heartbeat = None

    def _next_reconnect_delay(self, delay: float) -> float:
        """Return the base reconnect delay to use after a connection ends.

        A connection that stayed open at least
        ``WEBSOCKET_STABLE_CONNECTION_SECONDS`` resets the delay to the minimum;
        otherwise the delay is kept, so repeated failures keep backing off.

        Args:
            delay: Base delay used before the connection that just ended.

        Returns:
            The base delay, in seconds, before the next connection attempt.
        """
        connected_at = self._connected_at
        if (
            connected_at is not None
            and get_running_loop().time() - connected_at >= WEBSOCKET_STABLE_CONNECTION_SECONDS
        ):
            return WEBSOCKET_RECONNECT_MIN_DELAY_SECONDS
        return delay

    async def loop_listener(self) -> None:
        """Keep reconnecting the websocket listener while running is enabled.

        Cancellation stops the loop. Other listener errors are logged, and each
        reconnect waits with exponential backoff and jitter so an outage or a
        rejected token does not cause a tight reconnect loop. A connection that
        stays up resets the backoff.
        """
        self.running = True
        delay = WEBSOCKET_RECONNECT_MIN_DELAY_SECONDS
        try:
            while self.running:
                self._connected_at = None
                try:
                    _LOGGER.debug("websocket task listening")
                    await self.listener()
                    _LOGGER.debug("websocket task ending")
                except Exception as websocket_error:
                    # The background loop must survive any listener failure,
                    # including errors raised by user callbacks, so it can retry.
                    _LOGGER.exception("websocket task exception", exc_info=websocket_error)
                if not self.running:
                    break
                delay = self._next_reconnect_delay(delay)
                wait = delay * (1 + random() * 0.25)
                _LOGGER.debug("websocket reconnecting in %.1f seconds", wait)
                await sleep(wait)
                delay = min(delay * 2, WEBSOCKET_RECONNECT_MAX_DELAY_SECONDS)
        except CancelledError:
            _LOGGER.debug("websocket task cancelled")
        finally:
            self.running = False

    async def create_task_listener(self) -> None:
        """Start the background websocket listener task."""
        self.task_listener = create_task(self.loop_listener(), name="carrier_api_ws")

    async def stop(self) -> None:
        """Stop the listener and heartbeat tasks and close the websocket.

        Safe to call more than once and when nothing is running. If the task
        calling ``stop`` is itself being cancelled, that cancellation is
        re-raised after shutdown.
        """
        self.running = False
        tasks = [task for task in (self.task_listener, self.task_heartbeat) if task is not None]
        self.task_listener = None
        self.task_heartbeat = None
        websocket = self.websocket
        if websocket is not None:
            try:
                await websocket.close()
            except (ClientError, OSError, RuntimeError) as error:
                _LOGGER.debug("ws: close during stop failed: %s", error)
        for task in tasks:
            if task is current_task() or task.done():
                continue
            task.cancel()
            try:
                await task
            except CancelledError:
                calling_task = current_task()
                if calling_task is not None and calling_task.cancelling():
                    raise
        self.websocket = None
        _LOGGER.debug("ws: stopped")

    async def send_reconcile(self) -> None:
        """Request a Carrier realtime state reconciliation when connected."""
        if self.websocket is not None:
            await self.websocket.send_json({"action": "reconcile"})
            _LOGGER.debug("ws: reconciled")
        else:
            _LOGGER.debug("ws: not reconciled (websocket) missing")
