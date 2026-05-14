"""Tests for websocket connection state isolation."""

from carrier_api import ApiConnectionGraphql, ApiWebsocket


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
