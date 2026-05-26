"""Tests for websocket connection state isolation."""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import cast

from aiohttp import ClientConnectionError, ClientSession, WSMsgType
import pytest

from carrier_api import ApiConnectionGraphql, ApiWebsocket, CarrierApiWebsocketError


class DummyApiConnectionGraphql(ApiConnectionGraphql):
    """Minimal API connection stand-in used to construct websocket managers."""

    def __init__(self) -> None:
        """Initialize only the websocket attribute needed by the constructor."""
        self.api_websocket: ApiWebsocket | None = None


async def websocket_callback(_message: str) -> None:
    """Handle a websocket message during tests.

    Args:
        _message: The websocket message payload.
    """


def test_callbacks_are_instance_scoped() -> None:
    """Ensure callbacks registered on one websocket do not leak to another instance."""
    first_websocket = ApiWebsocket(DummyApiConnectionGraphql())
    second_websocket = ApiWebsocket(DummyApiConnectionGraphql())

    first_websocket.callback_add(websocket_callback)

    assert first_websocket.async_callbacks == [websocket_callback]
    assert second_websocket.async_callbacks == []


def test_callback_remove_unregisters_callback() -> None:
    """Remove a registered websocket callback from the instance."""
    api_websocket = ApiWebsocket(DummyApiConnectionGraphql())
    api_websocket.callback_add(websocket_callback)

    api_websocket.callback_remove(websocket_callback)

    assert api_websocket.async_callbacks == []


class FakeSendWebsocket:
    """Fake websocket that records JSON messages."""

    def __init__(self) -> None:
        """Initialize captured send state."""
        self.sent: list[dict[str, str]] = []

    async def send_json(self, payload: dict[str, str]) -> None:
        """Record a sent JSON payload.

        Args:
            payload: Websocket payload.
        """
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_send_reconcile_sends_only_when_websocket_exists() -> None:
    """Send reconcile payloads only when a websocket connection exists."""
    api_websocket = ApiWebsocket(DummyApiConnectionGraphql())
    fake_websocket = FakeSendWebsocket()

    await api_websocket.send_reconcile()
    api_websocket.websocket = fake_websocket  # type: ignore[assignment]
    await api_websocket.send_reconcile()

    assert fake_websocket.sent == [{"action": "reconcile"}]


class FakeHeartbeatTask:
    """Fake heartbeat task that records cancellation."""

    def __init__(self) -> None:
        """Initialize cancellation state."""
        self.cancelled = False

    def cancel(self) -> None:
        """Record task cancellation."""
        self.cancelled = True


class FakeListenerWebsocket:
    """Async websocket iterator for listener tests."""

    def __init__(
        self,
        messages: list[SimpleNamespace],
        exception: BaseException | None = None,
    ) -> None:
        """Initialize queued websocket messages.

        Args:
            messages: Messages yielded by the websocket iterator.
            exception: Optional websocket error reported by ``exception``.
        """
        self.messages = messages
        self.closed = False
        self.exception_value = exception

    def __aiter__(self) -> AsyncIterator[SimpleNamespace]:
        """Return this websocket as an async iterator.

        Returns:
            The websocket async iterator.
        """
        return self

    async def __anext__(self) -> SimpleNamespace:
        """Return the next queued message.

        Returns:
            The next fake websocket message.

        Raises:
            StopAsyncIteration: When no messages remain.
        """
        if not self.messages:
            raise StopAsyncIteration
        return self.messages.pop(0)

    async def close(self) -> None:
        """Record websocket close requests."""
        self.closed = True

    def exception(self) -> BaseException | None:
        """Return the configured websocket exception.

        Returns:
            Optional websocket receive exception.
        """
        return self.exception_value


class FakeWebsocketContext:
    """Async context manager for websocket connection tests."""

    def __init__(self, websocket: FakeListenerWebsocket) -> None:
        """Initialize the context manager with a websocket.

        Args:
            websocket: Websocket returned on context entry.
        """
        self.websocket = websocket

    async def __aenter__(self) -> FakeListenerWebsocket:
        """Enter the websocket context.

        Returns:
            The fake websocket.
        """
        return self.websocket

    async def __aexit__(self, *_args: object) -> None:
        """Exit the websocket context."""


class FakeListenerSession:
    """Session that returns a fake websocket context."""

    def __init__(self, websocket: FakeListenerWebsocket) -> None:
        """Initialize the session with a websocket.

        Args:
            websocket: Websocket returned by ``ws_connect``.
        """
        self.websocket = websocket
        self.connected_url: str | None = None

    def ws_connect(self, url: str) -> FakeWebsocketContext:
        """Capture websocket URL and return a fake context.

        Args:
            url: Websocket URL.

        Returns:
            Fake websocket context manager.
        """
        self.connected_url = url
        return FakeWebsocketContext(self.websocket)


class FailingListenerSession:
    """Session that fails websocket connection attempts."""

    def __init__(self, error: ClientConnectionError) -> None:
        """Initialize the session with the error to raise.

        Args:
            error: Connection error raised by ``ws_connect``.
        """
        self.error = error

    def ws_connect(self, url: str) -> FakeWebsocketContext:
        """Raise the configured websocket connection error.

        Args:
            url: Websocket URL.

        Raises:
            ClientConnectionError: Always raised for this failing session.
        """
        raise self.error


class FakeListenerConnection(DummyApiConnectionGraphql):
    """Connection double with auth and websocket session behavior."""

    def __init__(self, websocket: FakeListenerWebsocket) -> None:
        """Initialize fake connection state.

        Args:
            websocket: Websocket yielded by the fake session.
        """
        super().__init__()
        self.access_token = "token"
        self.listener_session = FakeListenerSession(websocket)
        self.api_session = cast("ClientSession", self.listener_session)
        self.auth_checked = False

    async def check_auth_expiration(self) -> None:
        """Record auth expiration checks."""
        self.auth_checked = True


class FailingListenerConnection(DummyApiConnectionGraphql):
    """Connection double with a failing websocket session."""

    def __init__(self, error: ClientConnectionError) -> None:
        """Initialize fake connection state.

        Args:
            error: Connection error raised by the fake session.
        """
        super().__init__()
        self.access_token = "token"
        self.listener_session = FailingListenerSession(error)
        self.api_session = cast("ClientSession", self.listener_session)
        self.auth_checked = False

    async def check_auth_expiration(self) -> None:
        """Record auth expiration checks."""
        self.auth_checked = True


class FakeHeartbeatApiWebsocket(ApiWebsocket):
    """Websocket manager that installs a fake heartbeat task."""

    def __init__(
        self,
        api_connection_graphql: ApiConnectionGraphql,
        heartbeat_task: FakeHeartbeatTask,
    ) -> None:
        """Initialize with a fake heartbeat task.

        Args:
            api_connection_graphql: Fake API connection.
            heartbeat_task: Task double to install when heartbeat starts.
        """
        super().__init__(api_connection_graphql)
        self.fake_heartbeat_task = heartbeat_task

    async def create_task_heartbeat(self) -> None:
        """Install the configured fake heartbeat task."""
        self.task_heartbeat = self.fake_heartbeat_task  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_listener_dispatches_text_and_closes_on_close_command() -> None:
    """Dispatch text messages, close on close command, and clear task state."""
    websocket = FakeListenerWebsocket(
        [
            SimpleNamespace(type=WSMsgType.TEXT, data="payload"),
            SimpleNamespace(type=WSMsgType.TEXT, data="close cmd"),
        ]
    )
    connection = FakeListenerConnection(websocket)
    heartbeat_task = FakeHeartbeatTask()
    api_websocket = FakeHeartbeatApiWebsocket(connection, heartbeat_task)
    received: list[str] = []

    async def capture(message: str) -> None:
        """Capture dispatched websocket messages.

        Args:
            message: Raw websocket text.
        """
        received.append(message)

    api_websocket.callback_add(capture)

    await api_websocket.listener()

    assert connection.auth_checked
    assert connection.listener_session.connected_url == (
        "wss://realtime.infinity.iot.carrier.com/?Token=token"
    )
    assert received == ["payload"]
    assert websocket.closed
    assert heartbeat_task.cancelled
    assert api_websocket.websocket is None
    assert api_websocket.task_heartbeat is None


@pytest.mark.asyncio
async def test_listener_wraps_websocket_connection_errors() -> None:
    """Raise Carrier websocket errors instead of raw aiohttp connection errors."""
    connection_error = ClientConnectionError("websocket unavailable")
    connection = FailingListenerConnection(connection_error)
    api_websocket = ApiWebsocket(connection)

    with pytest.raises(CarrierApiWebsocketError) as error:
        await api_websocket.listener()

    assert connection.auth_checked
    assert error.value.__cause__ is connection_error


@pytest.mark.asyncio
async def test_listener_does_not_wrap_callback_connection_errors() -> None:
    """Let callback I/O errors propagate instead of marking websocket failed."""
    websocket = FakeListenerWebsocket([SimpleNamespace(type=WSMsgType.TEXT, data="payload")])
    connection = FakeListenerConnection(websocket)
    heartbeat_task = FakeHeartbeatTask()
    api_websocket = FakeHeartbeatApiWebsocket(connection, heartbeat_task)
    callback_error = ClientConnectionError("callback request failed")

    async def fail_callback(message: str) -> None:
        """Raise the configured callback I/O error.

        Args:
            message: Raw websocket text.

        Raises:
            ClientConnectionError: Always raised for this callback.
        """
        raise callback_error

    api_websocket.callback_add(fail_callback)

    with pytest.raises(ClientConnectionError) as error:
        await api_websocket.listener()

    assert error.value is callback_error
    assert heartbeat_task.cancelled
    assert api_websocket.websocket is None
    assert api_websocket.task_heartbeat is None


@pytest.mark.asyncio
async def test_listener_raises_websocket_error_message_exception() -> None:
    """Raise Carrier websocket errors when the websocket reports an exception."""
    websocket_error = ClientConnectionError("websocket receive failed")
    websocket = FakeListenerWebsocket(
        [SimpleNamespace(type=WSMsgType.ERROR, data=None)], exception=websocket_error
    )
    connection = FakeListenerConnection(websocket)
    heartbeat_task = FakeHeartbeatTask()
    api_websocket = FakeHeartbeatApiWebsocket(connection, heartbeat_task)

    with pytest.raises(CarrierApiWebsocketError) as error:
        await api_websocket.listener()

    assert error.value.__cause__ is websocket_error
    assert heartbeat_task.cancelled
    assert api_websocket.websocket is None
    assert api_websocket.task_heartbeat is None


@pytest.mark.asyncio
async def test_listener_raises_websocket_error_message_without_exception() -> None:
    """Raise Carrier websocket errors when aiohttp omits the underlying exception."""
    websocket = FakeListenerWebsocket([SimpleNamespace(type=WSMsgType.ERROR, data=None)])
    connection = FakeListenerConnection(websocket)
    heartbeat_task = FakeHeartbeatTask()
    api_websocket = FakeHeartbeatApiWebsocket(connection, heartbeat_task)

    with pytest.raises(CarrierApiWebsocketError) as error:
        await api_websocket.listener()

    assert error.value.__cause__ is None
    assert heartbeat_task.cancelled
    assert api_websocket.websocket is None
    assert api_websocket.task_heartbeat is None
