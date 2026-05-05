"""Tests for websocket connection state isolation."""

from collections.abc import Awaitable, Callable
from typing import Any, cast

from carrier_api import ApiWebsocket


class DummyApiConnectionGraphql:
    """Minimal API connection stand-in used to construct websocket managers."""

    api_websocket: ApiWebsocket | None = None


async def websocket_callback(_message: str) -> None:
    """Handle a websocket message during tests.

    Args:
        _message: The websocket message payload.
    """


def test_callbacks_are_instance_scoped() -> None:
    """Ensure callbacks registered on one websocket do not leak to another instance."""
    first_websocket = ApiWebsocket(cast(Any, DummyApiConnectionGraphql()))
    second_websocket = ApiWebsocket(cast(Any, DummyApiConnectionGraphql()))
    callback = cast(Callable[[str], Awaitable[None]], websocket_callback)

    first_websocket.callback_add(callback)

    assert first_websocket.async_callbacks == [callback]
    assert second_websocket.async_callbacks == []
