"""Tests for websocket connection state isolation."""

import asyncio
from collections.abc import AsyncIterator, Callable
from types import SimpleNamespace
from typing import Any, cast

from aiohttp import ClientConnectionError, ClientError, ClientSession, WSMsgType
import pytest

from carrier_api import (
    ApiConnectionGraphql,
    ApiWebsocket,
    CarrierApiWebsocketError,
    api_websocket as api_websocket_module,
)
from carrier_api.const import (
    WEBSOCKET_RECONNECT_MAX_DELAY_SECONDS,
    WEBSOCKET_RECONNECT_MIN_DELAY_SECONDS,
    WEBSOCKET_STABLE_CONNECTION_SECONDS,
)


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

    def __init__(self, error: ClientError | TimeoutError | OSError) -> None:
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
            ClientError | TimeoutError | OSError: Always raised for this
                failing session.
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

    def __init__(self, error: ClientError | TimeoutError | OSError) -> None:
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
@pytest.mark.parametrize(
    "connection_error",
    [
        ClientConnectionError("websocket unavailable"),
        TimeoutError("websocket timed out"),
        OSError("websocket socket failed"),
    ],
)
async def test_listener_wraps_websocket_connection_errors(
    connection_error: ClientError | TimeoutError | OSError,
) -> None:
    """Raise Carrier websocket errors instead of raw aiohttp connection errors."""
    connection = FailingListenerConnection(connection_error)
    api_websocket = ApiWebsocket(connection)

    with pytest.raises(CarrierApiWebsocketError) as error:
        await api_websocket.listener()

    assert connection.auth_checked
    assert error.value.__cause__ is connection_error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "callback_error",
    [
        ClientConnectionError("callback request failed"),
        TimeoutError("callback timed out"),
        OSError("callback socket failed"),
    ],
)
async def test_listener_does_not_wrap_callback_connection_errors(
    callback_error: ClientError | TimeoutError | OSError,
) -> None:
    """Let callback I/O errors propagate instead of marking websocket failed."""
    websocket = FakeListenerWebsocket([SimpleNamespace(type=WSMsgType.TEXT, data="payload")])
    connection = FakeListenerConnection(websocket)
    heartbeat_task = FakeHeartbeatTask()
    api_websocket = FakeHeartbeatApiWebsocket(connection, heartbeat_task)

    async def fail_callback(message: str) -> None:
        """Raise the configured callback I/O error.

        Args:
            message: Raw websocket text.

        Raises:
            ClientError | TimeoutError | OSError: Always raised for this
                callback.
        """
        raise callback_error

    api_websocket.callback_add(fail_callback)

    with pytest.raises(type(callback_error)) as error:
        await api_websocket.listener()

    assert error.value is callback_error
    assert heartbeat_task.cancelled
    assert api_websocket.websocket is None
    assert api_websocket.task_heartbeat is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "websocket_error",
    [
        ClientConnectionError("websocket receive failed"),
        TimeoutError("websocket receive timed out"),
        OSError("websocket receive socket failed"),
        None,
    ],
)
async def test_listener_raises_websocket_error_messages(
    websocket_error: BaseException | None,
) -> None:
    """Raise Carrier websocket errors for websocket error messages.

    Args:
        websocket_error: Optional aiohttp websocket exception reported by the
            fake websocket.
    """
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
async def test_listener_logs_callback_parse_errors_and_keeps_listening(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Drop a message a callback cannot parse without closing the websocket.

    Args:
        caplog: Pytest log capture fixture.
    """
    websocket = FakeListenerWebsocket(
        [
            SimpleNamespace(type=WSMsgType.TEXT, data="bad"),
            SimpleNamespace(type=WSMsgType.TEXT, data="good"),
        ]
    )
    connection = FakeListenerConnection(websocket)
    api_websocket = FakeHeartbeatApiWebsocket(connection, FakeHeartbeatTask())
    received: list[str] = []

    async def parse(message: str) -> None:
        """Fail on the bad message and record the rest.

        Args:
            message: Raw websocket text.

        Raises:
            ValueError: When the message is ``"bad"``.
        """
        if message == "bad":
            raise ValueError("unparsable")
        received.append(message)

    async def record(message: str) -> None:
        """Record every message.

        Args:
            message: Raw websocket text.
        """
        received.append(f"second:{message}")

    api_websocket.callback_add(parse)
    api_websocket.callback_add(record)

    await api_websocket.listener()

    assert received == ["second:bad", "good", "second:good"]
    assert "callback failed to handle message" in caplog.text


class ScriptedListenerWebsocket(ApiWebsocket):
    """Websocket manager whose listener runs scripted outcomes."""

    def __init__(self, outcomes: list[tuple[float, BaseException | None]]) -> None:
        """Initialize scripted listener outcomes.

        Args:
            outcomes: For each listener call, how long the connection stays up
                (in fake seconds) and the error to raise, if any.
        """
        super().__init__(DummyApiConnectionGraphql())
        self.outcomes = outcomes
        self.clock = 0.0
        self.calls = 0

    async def listener(self) -> None:
        """Run the next scripted outcome.

        Raises:
            BaseException: When the scripted outcome carries an error.
        """
        self.calls += 1
        uptime, error = self.outcomes.pop(0)
        self._connected_at = self.clock
        self.clock += uptime
        if error is not None:
            raise error


@pytest.fixture
def scripted_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[float], Callable[[ScriptedListenerWebsocket, int], None]]:
    """Replace websocket sleeps with a recorder that can stop the loop.

    Args:
        monkeypatch: Pytest helper for replacing ``sleep`` and the clock.

    Returns:
        The list of recorded delays and a binder that sets which websocket to
        stop after a number of sleeps.
    """
    delays: list[float] = []
    state: dict[str, Any] = {}

    async def fake_sleep(delay: float) -> None:
        """Record the delay, advance the fake clock, and stop when done.

        Args:
            delay: Requested sleep in seconds.
        """
        delays.append(delay)
        websocket: ScriptedListenerWebsocket = state["websocket"]
        websocket.clock += delay
        if len(delays) >= state["limit"]:
            websocket.running = False

    def bind(websocket: ScriptedListenerWebsocket, limit: int) -> None:
        """Bind the fake sleep and clock to a websocket.

        Args:
            websocket: Websocket whose loop is being tested.
            limit: Number of sleeps after which the loop stops.
        """
        state["websocket"] = websocket
        state["limit"] = limit
        monkeypatch.setattr(
            api_websocket_module,
            "get_running_loop",
            lambda: SimpleNamespace(time=lambda: websocket.clock),
        )

    monkeypatch.setattr(api_websocket_module, "sleep", fake_sleep)
    monkeypatch.setattr(api_websocket_module, "random", lambda: 0.0)
    return delays, bind


@pytest.mark.asyncio
async def test_loop_listener_backs_off_exponentially_up_to_the_maximum(
    scripted_sleep: tuple[list[float], Callable[[ScriptedListenerWebsocket, int], None]],
) -> None:
    """Wait longer after each failed connection, capped at the maximum delay.

    Args:
        scripted_sleep: Recorded delays and the loop binder.
    """
    delays, bind = scripted_sleep
    attempts = 12
    api_websocket = ScriptedListenerWebsocket(
        [(0.0, CarrierApiWebsocketError("down")) for _ in range(attempts)]
    )
    bind(api_websocket, attempts)

    await api_websocket.loop_listener()

    assert delays[:4] == [1, 2, 4, 8]
    assert max(delays) == WEBSOCKET_RECONNECT_MAX_DELAY_SECONDS
    assert delays[-1] == WEBSOCKET_RECONNECT_MAX_DELAY_SECONDS
    assert api_websocket.calls == attempts
    assert api_websocket.running is False


@pytest.mark.asyncio
async def test_loop_listener_resets_backoff_after_a_stable_connection(
    scripted_sleep: tuple[list[float], Callable[[ScriptedListenerWebsocket, int], None]],
) -> None:
    """Reconnect quickly again once a connection has stayed up.

    Args:
        scripted_sleep: Recorded delays and the loop binder.
    """
    delays, bind = scripted_sleep
    api_websocket = ScriptedListenerWebsocket(
        [
            (0.0, CarrierApiWebsocketError("down")),
            (0.0, CarrierApiWebsocketError("down")),
            (0.0, CarrierApiWebsocketError("down")),
            (WEBSOCKET_STABLE_CONNECTION_SECONDS, None),
            (0.0, CarrierApiWebsocketError("down")),
        ]
    )
    bind(api_websocket, 5)

    await api_websocket.loop_listener()

    assert delays == [1, 2, 4, WEBSOCKET_RECONNECT_MIN_DELAY_SECONDS, 2]


@pytest.mark.asyncio
async def test_loop_listener_exits_quietly_when_cancelled() -> None:
    """Stop the reconnect loop when its task is cancelled."""
    started = asyncio.Event()

    class BlockingListenerWebsocket(ApiWebsocket):
        """Websocket manager whose listener blocks until cancelled."""

        async def listener(self) -> None:
            """Block until cancelled."""
            started.set()
            await asyncio.Event().wait()

    api_websocket = BlockingListenerWebsocket(DummyApiConnectionGraphql())
    task = asyncio.create_task(api_websocket.loop_listener())
    await started.wait()

    task.cancel()
    await task

    assert api_websocket.running is False


class BlockingSendWebsocket:
    """Websocket whose send blocks until cancelled."""

    def __init__(self) -> None:
        """Initialize the send-started event."""
        self.send_started = asyncio.Event()

    async def send_json(self, payload: dict[str, str]) -> None:
        """Block until cancelled.

        Args:
            payload: Websocket payload.
        """
        self.send_started.set()
        await asyncio.Event().wait()


@pytest.mark.asyncio
async def test_heartbeat_ends_promptly_when_cancelled_during_send() -> None:
    """End the heartbeat task at once when cancelled mid-send."""
    api_websocket = ApiWebsocket(DummyApiConnectionGraphql())
    websocket = BlockingSendWebsocket()
    api_websocket.websocket = websocket  # type: ignore[assignment]
    await api_websocket.create_task_heartbeat()
    assert api_websocket.task_heartbeat is not None
    await websocket.send_started.wait()

    api_websocket.task_heartbeat.cancel()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(api_websocket.task_heartbeat, timeout=1)


@pytest.mark.asyncio
async def test_heartbeat_logs_send_failures_and_keeps_running(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Keep sending keepalives after a failed send.

    Args:
        monkeypatch: Pytest helper for replacing ``sleep``.
        caplog: Pytest log capture fixture.
    """
    sends = 0

    class FlakySendWebsocket:
        """Websocket whose first send fails."""

        async def send_json(self, payload: dict[str, str]) -> None:
            """Fail on the first send.

            Args:
                payload: Websocket payload.

            Raises:
                ClientConnectionError: On the first send.
            """
            nonlocal sends
            sends += 1
            if sends == 1:
                raise ClientConnectionError("closing")

    async def fake_sleep(_delay: float) -> None:
        """Stop the heartbeat after the second send.

        Args:
            _delay: Requested sleep in seconds.

        Raises:
            asyncio.CancelledError: After the second send.
        """
        if sends >= 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(api_websocket_module, "sleep", fake_sleep)
    api_websocket = ApiWebsocket(DummyApiConnectionGraphql())
    api_websocket.websocket = FlakySendWebsocket()  # type: ignore[assignment]

    with pytest.raises(asyncio.CancelledError):
        await api_websocket.loop_heartbeat()

    assert sends == 2
    assert "keepalive failed" in caplog.text


@pytest.mark.asyncio
async def test_stop_cancels_tasks_and_closes_websocket() -> None:
    """Cancel listener and heartbeat tasks and close the open websocket."""
    api_websocket = ApiWebsocket(DummyApiConnectionGraphql())
    websocket = FakeListenerWebsocket([])
    api_websocket.websocket = websocket  # type: ignore[assignment]
    api_websocket.running = True
    listener_task = asyncio.create_task(asyncio.Event().wait())
    heartbeat_task = asyncio.create_task(asyncio.Event().wait())
    api_websocket.task_listener = listener_task  # type: ignore[assignment]
    api_websocket.task_heartbeat = heartbeat_task  # type: ignore[assignment]

    await api_websocket.stop()

    assert websocket.closed
    assert listener_task.cancelled()
    assert heartbeat_task.cancelled()
    assert api_websocket.running is False
    assert api_websocket.websocket is None
    assert api_websocket.task_listener is None
    assert api_websocket.task_heartbeat is None

    await api_websocket.stop()


@pytest.mark.asyncio
async def test_stop_ends_a_running_listener_loop() -> None:
    """Stop a real listener loop task started with ``create_task_listener``."""
    started = asyncio.Event()

    class BlockingListenerWebsocket(ApiWebsocket):
        """Websocket manager whose listener blocks until cancelled."""

        async def listener(self) -> None:
            """Block until cancelled."""
            started.set()
            await asyncio.Event().wait()

    api_websocket = BlockingListenerWebsocket(DummyApiConnectionGraphql())
    await api_websocket.create_task_listener()
    task = api_websocket.task_listener
    assert task is not None
    await started.wait()

    await api_websocket.stop()

    assert task.done()
    assert api_websocket.running is False
