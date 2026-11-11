"""Tests for Carrier GraphQL API connection helpers."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar, Self, cast

from aiohttp import ClientConnectionError, ClientError, ClientSession
from gql import GraphQLRequest, gql
from gql.transport.exceptions import TransportQueryError, TransportServerError
import pytest

import carrier_api
from carrier_api import errors
from carrier_api.api_connection_graphql import ApiConnectionGraphql
from carrier_api.const import ActivityTypes, FanModes, HeatSourceTypes, SystemModes
from carrier_api.system import System


class FakeSession:
    """Minimal session double used by connection tests."""

    def __init__(self) -> None:
        """Initialize captured session state."""
        self.closed = False

    async def close(self) -> None:
        """Record that the session was closed."""
        self.closed = True


class FakeGraphQLClient:
    """Minimal gql client double that captures constructor arguments."""

    execute_timeout: int | float | None = None

    def __init__(self, **kwargs: Any) -> None:
        """Capture gql client keyword arguments.

        Args:
            kwargs: Keyword arguments passed to ``gql.Client``.
        """
        self.kwargs = kwargs
        FakeGraphQLClient.execute_timeout = kwargs.get("execute_timeout")

    async def __aenter__(self) -> Self:
        """Enter the fake async context manager.

        Returns:
            The fake GraphQL client.
        """
        return self

    async def __aexit__(self, *args: object) -> None:
        """Exit the fake async context manager.

        Args:
            args: Context manager exception details.
        """

    async def execute(
        self,
        query: GraphQLRequest,
        *,
        variable_values: dict[str, Any],
        operation_name: str,
    ) -> dict[str, Any]:
        """Return captured query metadata.

        Args:
            query: GraphQL request.
            variable_values: Variables supplied to the query.
            operation_name: GraphQL operation name.

        Returns:
            Captured query metadata.
        """
        return {
            "query": query,
            "variables": variable_values,
            "operation_name": operation_name,
        }


def graphql_client_double(
    *,
    result: dict[str, Any] | None = None,
    error: BaseException | None = None,
) -> type[object]:
    """Create a GraphQL client double that returns or raises during execute.

    Args:
        result: Optional GraphQL result returned by ``execute``.
        error: Optional error raised by ``execute``.

    Returns:
        A GraphQL client double class suitable for monkeypatching ``Client``.
    """

    class ConfiguredGraphQLClient:
        """GraphQL client double with configured execute behavior."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            """Accept GraphQL client construction arguments."""

        async def __aenter__(self) -> Self:
            """Return the fake session.

            Returns:
                The fake GraphQL session.
            """
            return self

        async def __aexit__(self, *args: object) -> None:
            """Exit the fake session context."""

        async def execute(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            """Return or raise the configured GraphQL result.

            Returns:
                The configured GraphQL result.

            Raises:
                BaseException: When ``error`` is configured.
            """
            if error is not None:
                raise error
            assert result is not None
            return result

    return ConfiguredGraphQLClient


class SpyConnection(ApiConnectionGraphql):
    """Connection test double that captures GraphQL and mutation calls."""

    def __init__(self) -> None:
        """Initialize the connection with a fake HTTP session."""
        super().__init__(
            username="user@example.com",
            password="password",
            client_session=cast("ClientSession", FakeSession()),
        )
        self.authed_calls: list[tuple[str, dict[str, Any]]] = []
        self.config_updates: list[dict[str, Any]] = []
        self.zone_activity_updates: list[dict[str, Any]] = []
        self.zone_config_updates: list[dict[str, Any]] = []
        self.login_count = 0
        self.refresh_count = 0

    async def login(self) -> None:
        """Record login calls and seed token state."""
        self.login_count += 1
        self.refresh_token = "refresh"
        self.expires_at = datetime.now(UTC) + timedelta(hours=1)

    async def refresh_auth_token(self) -> None:
        """Record refresh calls and extend token state."""
        self.refresh_count += 1
        self.expires_at = datetime.now(UTC) + timedelta(hours=1)

    async def authed_query(
        self,
        operation_name: str,
        query: GraphQLRequest,
        variable_values: dict[str, Any],
    ) -> dict[str, Any]:
        """Capture authenticated query metadata.

        Args:
            operation_name: GraphQL operation name.
            query: Parsed GraphQL request.
            variable_values: GraphQL variables.

        Returns:
            A small response containing the operation metadata.
        """
        assert query is not None
        self.authed_calls.append((operation_name, variable_values))
        return {"operation": operation_name, "variables": variable_values}

    async def _update_infinity_config(self, variables: dict[str, Any]) -> dict[str, Any]:
        """Capture system config mutation variables.

        Args:
            variables: Mutation variables.

        Returns:
            A small mutation result.
        """
        self.config_updates.append(variables)
        return {"ok": True, "variables": variables}

    async def _update_infinity_zone_activity(self, variables: dict[str, Any]) -> dict[str, Any]:
        """Capture zone activity mutation variables.

        Args:
            variables: Mutation variables.

        Returns:
            A small mutation result.
        """
        self.zone_activity_updates.append(variables)
        return {"ok": True, "variables": variables}

    async def _update_infinity_zone_config(self, variables: dict[str, Any]) -> dict[str, Any]:
        """Capture zone config mutation variables.

        Args:
            variables: Mutation variables.

        Returns:
            A small mutation result.
        """
        self.zone_config_updates.append(variables)
        return {"ok": True, "variables": variables}


@pytest.mark.asyncio
async def test_authed_query_uses_extended_execute_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Authenticated queries allow slow Carrier responses to complete."""
    monkeypatch.setattr(
        "carrier_api.api_connection_graphql.Client",
        FakeGraphQLClient,
    )
    connection = ApiConnectionGraphql(
        username="user@example.com",
        password="password",
        client_session=cast("ClientSession", FakeSession()),
    )
    connection.refresh_token = "refresh"
    connection.token_type = "Bearer"
    connection.access_token = "access"
    connection.expires_at = datetime.now(UTC) + timedelta(hours=1)

    await connection.authed_query(
        operation_name="ExampleQuery",
        query=gql("query ExampleQuery { example }"),
        variable_values={},
    )

    assert FakeGraphQLClient.execute_timeout == 60


@pytest.fixture
def connection() -> SpyConnection:
    """Build a spy connection for API helper tests.

    Returns:
        A connection double that captures calls instead of using the network.
    """
    return SpyConnection()


def test_public_error_exports_use_carrier_api_prefix() -> None:
    """Expose Carrier-prefixed public API exception classes."""
    assert errors.CarrierApiError.__name__ == "CarrierApiError"
    assert errors.CarrierApiAuthError.__name__ == "CarrierApiAuthError"
    assert errors.CarrierApiConnectionError.__name__ == "CarrierApiConnectionError"
    assert errors.CarrierApiGraphqlError.__name__ == "CarrierApiGraphqlError"
    assert errors.CarrierApiTokenRefreshError.__name__ == "CarrierApiTokenRefreshError"
    assert errors.CarrierApiWebsocketError.__name__ == "CarrierApiWebsocketError"
    assert issubclass(errors.CarrierApiAuthError, errors.CarrierApiError)
    assert issubclass(errors.CarrierApiConnectionError, errors.CarrierApiError)
    assert issubclass(errors.CarrierApiConnectionError, ClientError)
    assert issubclass(errors.CarrierApiGraphqlError, errors.CarrierApiError)
    assert issubclass(errors.CarrierApiTokenRefreshError, errors.CarrierApiConnectionError)
    assert not issubclass(errors.CarrierApiTokenRefreshError, errors.CarrierApiAuthError)
    assert issubclass(errors.CarrierApiWebsocketError, errors.CarrierApiConnectionError)
    assert carrier_api.CarrierApiError is errors.CarrierApiError
    assert carrier_api.CarrierApiAuthError is errors.CarrierApiAuthError
    assert carrier_api.CarrierApiConnectionError is errors.CarrierApiConnectionError
    assert carrier_api.CarrierApiGraphqlError is errors.CarrierApiGraphqlError
    assert carrier_api.CarrierApiTokenRefreshError is errors.CarrierApiTokenRefreshError
    assert carrier_api.CarrierApiWebsocketError is errors.CarrierApiWebsocketError
    assert errors.AuthError is errors.CarrierApiAuthError
    assert errors.BaseError is errors.CarrierApiError
    assert carrier_api.AuthError is errors.CarrierApiAuthError
    assert carrier_api.BaseError is errors.CarrierApiError


@pytest.mark.asyncio
async def test_login_failure_uses_readable_message_and_preserves_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Expose a readable auth failure message while preserving payload access.

    Args:
        monkeypatch: Pytest helper for replacing the GraphQL client.
    """
    payload = {
        "assistedLogin": {
            "success": False,
            "status": "FAILED",
            "errorMessage": "invalid credentials",
        }
    }

    monkeypatch.setattr(
        "carrier_api.api_connection_graphql.Client", graphql_client_double(result=payload)
    )
    connection = ApiConnectionGraphql(
        username="user@example.com",
        password="password",
        client_session=cast("ClientSession", FakeSession()),
    )

    with pytest.raises(errors.CarrierApiAuthError) as error:
        await connection.login()

    assert error.value.args[0] == "Carrier assistedLogin failed: invalid credentials"
    assert error.value.payload == payload


@pytest.mark.asyncio
async def test_cleanup_closes_provided_session() -> None:
    """Close the underlying HTTP session."""
    session = FakeSession()
    connection = ApiConnectionGraphql(
        username="user@example.com",
        password="password",
        client_session=cast("ClientSession", session),
    )

    await connection.cleanup()

    assert session.closed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cleanup_error",
    [
        ClientConnectionError("cleanup connection failed"),
        TimeoutError("cleanup timed out"),
        OSError("cleanup socket failed"),
    ],
)
async def test_cleanup_wraps_session_close_errors(
    cleanup_error: ClientError | TimeoutError | OSError,
) -> None:
    """Raise Carrier connection errors instead of raw session cleanup errors.

    Args:
        cleanup_error: Error raised by the fake session close.
    """

    class FailingCloseSession(FakeSession):
        """Session double that fails during cleanup."""

        async def close(self) -> None:
            """Raise the configured cleanup error.

            Raises:
                ClientError | TimeoutError | OSError: Always raised for this
                    failing session.
            """
            raise cleanup_error

    connection = ApiConnectionGraphql(
        username="user@example.com",
        password="password",
        client_session=cast("ClientSession", FailingCloseSession()),
    )

    with pytest.raises(errors.CarrierApiConnectionError) as error:
        await connection.cleanup()

    assert error.value.__cause__ is cleanup_error


class FetchAccessTokenClient:
    """GraphQL client double for ``fetchAccessToken`` refresh calls."""

    calls: ClassVar[list[dict[str, Any]]] = []
    result: ClassVar[object] = None
    error: ClassVar[BaseException | None] = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Accept GraphQL client construction arguments."""

    async def __aenter__(self) -> Self:
        """Return the fake session.

        Returns:
            The fake GraphQL session.
        """
        return self

    async def __aexit__(self, *args: object) -> None:
        """Exit the fake session context.

        Args:
            args: Context manager exception details.
        """

    async def execute(
        self,
        query: GraphQLRequest,
        *,
        variable_values: dict[str, Any],
        operation_name: str,
    ) -> object:
        """Record the refresh call and return or raise the configured outcome.

        Args:
            query: GraphQL request.
            variable_values: Variables supplied to the mutation.
            operation_name: GraphQL operation name.

        Returns:
            The configured GraphQL result.

        Raises:
            BaseException: When ``error`` is configured.
        """
        FetchAccessTokenClient.calls.append(
            {"operation_name": operation_name, "variables": variable_values}
        )
        if FetchAccessTokenClient.error is not None:
            raise FetchAccessTokenClient.error
        return FetchAccessTokenClient.result


@pytest.fixture
def fetch_access_token(monkeypatch: pytest.MonkeyPatch) -> type[FetchAccessTokenClient]:
    """Route GraphQL clients to the ``fetchAccessToken`` double.

    Args:
        monkeypatch: Pytest helper for replacing the GraphQL client.

    Returns:
        The configured client double class.
    """
    FetchAccessTokenClient.calls = []
    FetchAccessTokenClient.result = None
    FetchAccessTokenClient.error = None
    monkeypatch.setattr("carrier_api.api_connection_graphql.Client", FetchAccessTokenClient)
    return FetchAccessTokenClient


def _fetch_result(**data: object) -> dict[str, Any]:
    """Build a successful ``fetchAccessToken`` result.

    Args:
        data: Token fields overriding the defaults.

    Returns:
        A GraphQL result payload.
    """
    token_data: dict[str, object] = {
        "token_type": "Bearer",
        "expires_in": 3600,
        "access_token": "new-access",
        "scope": "login",
        "refresh_token": "new-refresh",
        **data,
    }
    return {"fetchAccessToken": {"success": True, "errorMessage": None, "data": token_data}}


def _refresh_connection() -> ApiConnectionGraphql:
    """Build a connection holding a stored refresh token.

    Returns:
        A connection ready for ``refresh_auth_token``.
    """
    connection = ApiConnectionGraphql(
        username="user@example.com",
        password="password",
        client_session=cast("ClientSession", FakeSession()),
    )
    connection.refresh_token = "old-refresh"
    return connection


@pytest.mark.asyncio
async def test_refresh_auth_token_uses_fetch_access_token(
    fetch_access_token: type[FetchAccessTokenClient],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Refresh through Carrier's mutation and store the rotated token state.

    Args:
        fetch_access_token: GraphQL client double for the refresh mutation.
        caplog: Pytest log capture fixture.
    """
    caplog.set_level("DEBUG", logger="carrier_api.api_connection_graphql")
    fetch_access_token.result = _fetch_result()
    connection = _refresh_connection()

    await connection.refresh_auth_token()

    assert fetch_access_token.calls == [
        {
            "operation_name": "fetchAccessToken",
            "variables": {"input": {"username": "user@example.com", "refreshToken": "old-refresh"}},
        }
    ]
    assert connection.token_type == "Bearer"
    assert connection.access_token == "new-access"
    assert connection.refresh_token == "new-refresh"
    assert connection.expires_at > datetime.now(UTC)
    assert "refresh token rotated" in caplog.text
    assert "new-refresh" not in caplog.text
    assert "new-access" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("refresh_token", ["old-refresh", None])
async def test_refresh_auth_token_keeps_unrotated_refresh_token(
    fetch_access_token: type[FetchAccessTokenClient],
    caplog: pytest.LogCaptureFixture,
    refresh_token: str | None,
) -> None:
    """Keep the stored refresh token when the provider does not rotate it.

    Args:
        fetch_access_token: GraphQL client double for the refresh mutation.
        caplog: Pytest log capture fixture.
        refresh_token: Refresh token returned by the mutation.
    """
    caplog.set_level("DEBUG", logger="carrier_api.api_connection_graphql")
    fetch_access_token.result = _fetch_result(refresh_token=refresh_token)
    connection = _refresh_connection()

    await connection.refresh_auth_token()

    assert connection.refresh_token == "old-refresh"
    assert connection.access_token == "new-access"
    assert "refresh token unchanged" in caplog.text


@pytest.mark.asyncio
async def test_refresh_auth_token_treats_unsuccessful_result_as_auth_error(
    fetch_access_token: type[FetchAccessTokenClient],
) -> None:
    """Raise auth errors when Carrier reports the refresh as unsuccessful.

    Args:
        fetch_access_token: GraphQL client double for the refresh mutation.
    """
    rejection = {
        "success": False,
        "errorMessage": "AADSTS9002313: Invalid request.",
        "data": None,
    }
    fetch_access_token.result = {"fetchAccessToken": rejection}
    connection = _refresh_connection()

    with pytest.raises(errors.CarrierApiAuthError) as error:
        await connection.refresh_auth_token()

    assert error.value.payload == rejection
    assert connection.refresh_token == "old-refresh"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("refresh_error", "expected"),
    [
        (TransportQueryError("refresh failed"), errors.CarrierApiTokenRefreshError),
        (ClientConnectionError("connection failed"), errors.CarrierApiTokenRefreshError),
        (TimeoutError("timed out"), errors.CarrierApiTokenRefreshError),
        (OSError("socket failed"), errors.CarrierApiTokenRefreshError),
        (TransportServerError("server error", 500), errors.CarrierApiTokenRefreshError),
        (TransportServerError("unauthorized", 401), errors.CarrierApiAuthError),
    ],
)
async def test_refresh_auth_token_normalizes_request_failures(
    fetch_access_token: type[FetchAccessTokenClient],
    refresh_error: BaseException,
    expected: type[errors.CarrierApiError],
) -> None:
    """Map refresh request failures to Carrier errors.

    Args:
        fetch_access_token: GraphQL client double for the refresh mutation.
        refresh_error: Error raised by the GraphQL client.
        expected: Carrier error expected from the refresh.
    """
    fetch_access_token.error = refresh_error
    connection = _refresh_connection()

    with pytest.raises(expected) as error:
        await connection.refresh_auth_token()

    assert type(error.value) is expected
    assert error.value.__cause__ is refresh_error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [
        None,
        {},
        {"fetchAccessToken": None},
        {"fetchAccessToken": {"success": True, "errorMessage": None, "data": None}},
        {"fetchAccessToken": {"success": True, "data": {}}},
        {"fetchAccessToken": {"success": True, "data": {"token_type": "Bearer"}}},
    ],
)
async def test_refresh_auth_token_rejects_malformed_results(
    fetch_access_token: type[FetchAccessTokenClient],
    result: object,
) -> None:
    """Raise token refresh errors for malformed mutation results.

    Args:
        fetch_access_token: GraphQL client double for the refresh mutation.
        result: Malformed GraphQL result.
    """
    fetch_access_token.result = result
    connection = _refresh_connection()

    with pytest.raises(errors.CarrierApiTokenRefreshError):
        await connection.refresh_auth_token()

    assert connection.refresh_token == "old-refresh"
    assert connection.access_token is None


@pytest.mark.asyncio
async def test_check_auth_expiration_logs_in_then_refreshes_when_expired(
    connection: SpyConnection,
) -> None:
    """Log in when missing a refresh token and refresh expired tokens.

    Args:
        connection: Spy connection under test.
    """
    await connection.check_auth_expiration()
    connection.expires_at = datetime.now(UTC) - timedelta(seconds=1)

    await connection.check_auth_expiration()

    assert connection.login_count == 1
    assert connection.refresh_count == 1


class RefreshSpyConnection(ApiConnectionGraphql):
    """Connection double whose token refresh outcome is configurable."""

    def __init__(self, refresh_error: BaseException | None = None) -> None:
        """Initialize an expired connection with a stored refresh token.

        Args:
            refresh_error: Optional error raised by every token refresh.
        """
        super().__init__(
            username="user@example.com",
            password="password",
            client_session=cast("ClientSession", FakeSession()),
        )
        self.refresh_error = refresh_error
        self.login_error: BaseException | None = None
        self.refresh_token = "stored-refresh"
        self.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        self.login_count = 0
        self.refreshed_tokens: list[str | None] = []

    async def login(self) -> None:
        """Record login calls and seed fresh token state.

        Raises:
            BaseException: When ``login_error`` is configured.
        """
        self.login_count += 1
        if self.login_error is not None:
            raise self.login_error
        self.refresh_token = "login-refresh"
        self.expires_at = datetime.now(UTC) + timedelta(hours=1)

    async def refresh_auth_token(self) -> None:
        """Record the refresh token used and rotate it like Okta.

        Raises:
            BaseException: When ``refresh_error`` is configured.
        """
        self.refreshed_tokens.append(self.refresh_token)
        await asyncio.sleep(0)
        if self.refresh_error is not None:
            raise self.refresh_error
        self.refresh_token = f"rotated-{len(self.refreshed_tokens)}"
        self.expires_at = datetime.now(UTC) + timedelta(hours=1)


@pytest.mark.asyncio
async def test_check_auth_expiration_logs_in_when_refresh_is_rejected() -> None:
    """Fall back to one password login when Carrier rejects the refresh token."""
    connection = RefreshSpyConnection(errors.CarrierApiAuthError("rejected"))

    await connection.check_auth_expiration()

    assert connection.refreshed_tokens == ["stored-refresh"]
    assert connection.login_count == 1
    assert connection.refresh_token == "login-refresh"
    assert connection.expires_at > datetime.now(UTC)


@pytest.mark.asyncio
async def test_check_auth_expiration_raises_when_fallback_login_is_rejected() -> None:
    """Surface auth errors when the fallback password login is also rejected."""
    connection = RefreshSpyConnection(errors.CarrierApiAuthError("rejected"))
    login_error = errors.CarrierApiAuthError("bad password")
    connection.login_error = login_error

    with pytest.raises(errors.CarrierApiAuthError) as error:
        await connection.check_auth_expiration()

    assert error.value is login_error
    assert connection.refresh_token is None


@pytest.mark.asyncio
async def test_check_auth_expiration_keeps_token_on_transient_refresh_failure() -> None:
    """Do not log in again when token refresh fails for transient reasons."""
    connection = RefreshSpyConnection(errors.CarrierApiTokenRefreshError("network"))

    with pytest.raises(errors.CarrierApiTokenRefreshError):
        await connection.check_auth_expiration()

    assert connection.login_count == 0
    assert connection.refresh_token == "stored-refresh"


@pytest.mark.asyncio
async def test_check_auth_expiration_serializes_concurrent_refreshes() -> None:
    """Send a single-use refresh token only once when callers race after expiry."""
    connection = RefreshSpyConnection()

    await asyncio.gather(
        connection.check_auth_expiration(),
        connection.check_auth_expiration(),
        connection.check_auth_expiration(),
    )

    assert connection.refreshed_tokens == ["stored-refresh"]
    assert connection.refresh_token == "rotated-1"


@pytest.mark.asyncio
async def test_login_wraps_graphql_query_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Raise Carrier GraphQL errors instead of raw GraphQL query exceptions.

    Args:
        monkeypatch: Pytest helper for replacing the GraphQL client.
    """
    transport_error = TransportQueryError("invalid credentials")

    monkeypatch.setattr(
        "carrier_api.api_connection_graphql.Client", graphql_client_double(error=transport_error)
    )
    connection = ApiConnectionGraphql(
        username="user@example.com",
        password="password",
        client_session=cast("ClientSession", FakeSession()),
    )

    with pytest.raises(errors.CarrierApiGraphqlError) as error:
        await connection.login()

    assert error.value.__cause__ is transport_error
    assert isinstance(error.value, errors.CarrierApiError)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "transport_error",
    [
        ClientConnectionError("connection failed"),
        TimeoutError("connection timed out"),
        OSError("socket failed"),
    ],
)
async def test_login_wraps_connection_errors(
    monkeypatch: pytest.MonkeyPatch,
    transport_error: ClientError | TimeoutError | OSError,
) -> None:
    """Raise Carrier connection errors instead of raw login transport exceptions.

    Args:
        monkeypatch: Pytest helper for replacing the GraphQL client.
        transport_error: Network or transport exception raised by the fake client.
    """
    monkeypatch.setattr(
        "carrier_api.api_connection_graphql.Client", graphql_client_double(error=transport_error)
    )
    connection = ApiConnectionGraphql(
        username="user@example.com",
        password="password",
        client_session=cast("ClientSession", FakeSession()),
    )

    with pytest.raises(errors.CarrierApiConnectionError) as error:
        await connection.login()

    assert error.value.__cause__ is transport_error


@pytest.mark.asyncio
async def test_authed_query_wraps_graphql_query_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise Carrier API errors instead of raw GraphQL transport exceptions.

    Args:
        monkeypatch: Pytest helper for replacing the GraphQL client.
    """
    transport_error = TransportQueryError("query failed")

    monkeypatch.setattr(
        "carrier_api.api_connection_graphql.Client", graphql_client_double(error=transport_error)
    )
    connection = ApiConnectionGraphql(
        username="user@example.com",
        password="password",
        client_session=cast("ClientSession", FakeSession()),
    )
    connection.refresh_token = "refresh"
    connection.token_type = "Bearer"
    connection.access_token = "access"
    connection.expires_at = datetime.now(UTC) + timedelta(hours=1)

    with pytest.raises(errors.CarrierApiGraphqlError) as error:
        await connection.authed_query(
            operation_name="getUser",
            query=cast("GraphQLRequest", object()),
            variable_values={},
        )

    assert error.value.__cause__ is transport_error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "transport_error",
    [
        TransportServerError("server unavailable", code=503),
        ClientConnectionError("connection failed"),
        TimeoutError("connection timed out"),
        OSError("socket failed"),
    ],
)
async def test_authed_query_wraps_connection_errors(
    monkeypatch: pytest.MonkeyPatch,
    transport_error: Exception | TimeoutError | OSError,
) -> None:
    """Raise Carrier connection errors instead of raw network exceptions.

    Args:
        monkeypatch: Pytest helper for replacing the GraphQL client.
        transport_error: Network or transport exception raised by the fake client.
    """
    monkeypatch.setattr(
        "carrier_api.api_connection_graphql.Client", graphql_client_double(error=transport_error)
    )
    connection = ApiConnectionGraphql(
        username="user@example.com",
        password="password",
        client_session=cast("ClientSession", FakeSession()),
    )
    connection.refresh_token = "refresh"
    connection.token_type = "Bearer"
    connection.access_token = "access"
    connection.expires_at = datetime.now(UTC) + timedelta(hours=1)

    with pytest.raises(errors.CarrierApiConnectionError) as error:
        await connection.authed_query(
            operation_name="getUser",
            query=cast("GraphQLRequest", object()),
            variable_values={},
        )

    assert error.value.__cause__ is transport_error


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_authed_query_maps_auth_transport_errors_to_auth_error(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    """Raise auth errors when GraphQL transport reports auth HTTP statuses.

    Args:
        monkeypatch: Pytest helper for replacing the GraphQL client.
        status: HTTP status raised by the fake GraphQL transport.
    """
    transport_error = TransportServerError("unauthorized", code=status)

    monkeypatch.setattr(
        "carrier_api.api_connection_graphql.Client", graphql_client_double(error=transport_error)
    )
    connection = ApiConnectionGraphql(
        username="user@example.com",
        password="password",
        client_session=cast("ClientSession", FakeSession()),
    )
    connection.refresh_token = "refresh"
    connection.token_type = "Bearer"
    connection.access_token = "access"
    connection.expires_at = datetime.now(UTC) + timedelta(hours=1)

    with pytest.raises(errors.CarrierApiAuthError) as error:
        await connection.authed_query(
            operation_name="getUser",
            query=cast("GraphQLRequest", object()),
            variable_values={},
        )

    assert error.value.__cause__ is transport_error


@pytest.mark.asyncio
async def test_query_helpers_send_expected_operation_and_variables(
    connection: SpyConnection,
) -> None:
    """Build GraphQL query operations with the expected variable values.

    Args:
        connection: Spy connection under test.
    """
    assert await connection.get_user_info() == {
        "operation": "getUser",
        "variables": {"userName": "user@example.com"},
    }
    assert await connection.get_systems() == {
        "operation": "getInfinitySystems",
        "variables": {"userName": "user@example.com"},
    }
    assert await connection.get_energy("SERIAL") == {
        "operation": "getInfinityEnergy",
        "variables": {"serial": "SERIAL"},
    }

    assert connection.authed_calls == [
        ("getUser", {"userName": "user@example.com"}),
        ("getInfinitySystems", {"userName": "user@example.com"}),
        ("getInfinityEnergy", {"serial": "SERIAL"}),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "transport_error"),
    [
        ("get_user_info", TimeoutError("get user timed out")),
        ("get_user_info", OSError("get user socket failed")),
        ("load_data", TimeoutError("load data timed out")),
        ("load_data", OSError("load data socket failed")),
    ],
)
async def test_public_query_helpers_preserve_connection_error_normalization(
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    transport_error: TimeoutError | OSError,
) -> None:
    """Keep public query helpers from leaking raw network exceptions.

    Args:
        monkeypatch: Pytest helper for replacing the GraphQL client.
        method_name: Public helper method called by API consumers.
        transport_error: Network exception raised by the fake client.
    """
    monkeypatch.setattr(
        "carrier_api.api_connection_graphql.Client", graphql_client_double(error=transport_error)
    )
    connection = ApiConnectionGraphql(
        username="user@example.com",
        password="password",
        client_session=cast("ClientSession", FakeSession()),
    )
    connection.refresh_token = "refresh"
    connection.token_type = "Bearer"
    connection.access_token = "access"
    connection.expires_at = datetime.now(UTC) + timedelta(hours=1)

    with pytest.raises(errors.CarrierApiConnectionError) as error:
        await getattr(connection, method_name)()

    assert error.value.__cause__ is transport_error


@pytest.mark.asyncio
async def test_load_data_builds_systems_from_query_payloads(
    system_response: dict[str, Any],
    energy_response: dict[str, Any],
) -> None:
    """Build system aggregates from stored GraphQL fixture payloads.

    Args:
        system_response: Parsed systems fixture.
        energy_response: Parsed energy fixture.
    """

    class FixtureConnection(SpyConnection):
        """Connection that returns fixture-backed system and energy payloads."""

        async def get_systems(self) -> dict[str, Any]:
            """Return fixture system data.

            Returns:
                Stored GraphQL systems fixture.
            """
            return system_response

        async def get_energy(self, system_serial: str) -> dict[str, Any]:
            """Return fixture energy data for a system.

            Args:
                system_serial: Serial requested by ``load_data``.

            Returns:
                Stored GraphQL energy fixture.
            """
            assert system_serial == "SERIALXXX"
            return energy_response

    systems = await FixtureConnection().load_data()

    assert len(systems) == 1
    assert isinstance(systems[0], System)
    assert systems[0].profile.serial == "SERIALXXX"
    assert systems[0].energy.current_year_measurements() is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "args", "expected"),
    [
        (
            "set_config_mode",
            ("SERIAL", SystemModes.HEAT),
            {"input": {"serial": "SERIAL", "mode": "heat"}},
        ),
        (
            "set_config_heat_humidity",
            ("SERIAL", 0),
            {"input": {"serial": "SERIAL", "humidityHome": {"humidifier": "off"}}},
        ),
        (
            "set_config_heat_humidity",
            ("SERIAL", 35),
            {"input": {"serial": "SERIAL", "humidityHome": {"humidifier": "on", "rhtg": 7.0}}},
        ),
        (
            "set_heat_source",
            ("SERIAL", HeatSourceTypes.SYSTEM),
            {"input": {"serial": "SERIAL", "heatsource": "system"}},
        ),
    ],
)
async def test_system_config_mutations_build_expected_variables(
    connection: SpyConnection,
    method_name: str,
    args: tuple[Any, ...],
    expected: dict[str, Any],
) -> None:
    """Build expected system-level config mutation variables.

    Args:
        connection: Spy connection under test.
        method_name: Name of the mutation helper to call.
        args: Arguments passed to the helper.
        expected: Expected mutation variables.
    """
    method = getattr(connection, method_name)

    assert await method(*args) == {"ok": True, "variables": expected}
    assert connection.config_updates[-1] == expected


@pytest.mark.asyncio
async def test_set_humidifier_builds_combined_home_humidity_payload(
    connection: SpyConnection,
) -> None:
    """Build combined humidifier, over-cooling, cooling, and heating settings.

    Args:
        connection: Spy connection under test.
    """
    await connection.set_humidifier(
        system_serial="SERIAL",
        over_cooling=True,
        cooling_percent=40,
        heating_percent=25,
    )
    await connection.set_humidifier(system_serial="SERIAL", humidifier_on=False)

    assert connection.config_updates == [
        {
            "input": {
                "serial": "SERIAL",
                "humidityHome": {
                    "humid": "manual",
                    "humidifier": "on",
                    "rclgovercool": "on",
                    "rclg": 8.0,
                    "rhtg": 5.0,
                },
            }
        },
        {
            "input": {
                "serial": "SERIAL",
                "humidityHome": {
                    "humid": "off",
                    "humidifier": "off",
                },
            }
        },
    ]


@pytest.mark.asyncio
async def test_zone_mutations_build_expected_variables(connection: SpyConnection) -> None:
    """Build expected zone activity and zone config mutation variables.

    Args:
        connection: Spy connection under test.
    """
    await connection.update_fan("SERIAL", "1", ActivityTypes.HOME, FanModes.HIGH)
    await connection.set_config_hold("SERIAL", "1", ActivityTypes.MANUAL, "23:00")
    await connection.resume_schedule("SERIAL", "1")
    await connection.set_config_manual_activity("SERIAL", "1", "70", "76", FanModes.LOW)
    await connection.set_config_manual_activity("SERIAL", "1", "68", "74")

    assert connection.zone_activity_updates == [
        {
            "input": {
                "serial": "SERIAL",
                "zoneId": "1",
                "activityType": "home",
                "fan": "high",
            }
        },
        {
            "input": {
                "serial": "SERIAL",
                "zoneId": "1",
                "activityType": "manual",
                "clsp": "76",
                "htsp": "70",
                "fan": "low",
            }
        },
        {
            "input": {
                "serial": "SERIAL",
                "zoneId": "1",
                "activityType": "manual",
                "clsp": "74",
                "htsp": "68",
            }
        },
    ]
    assert connection.zone_config_updates == [
        {
            "input": {
                "serial": "SERIAL",
                "zoneId": "1",
                "hold": "on",
                "holdActivity": "manual",
                "otmr": "23:00",
            }
        },
        {
            "input": {
                "serial": "SERIAL",
                "zoneId": "1",
                "hold": "off",
                "holdActivity": None,
                "otmr": None,
            }
        },
    ]


@pytest.mark.asyncio
async def test_update_methods_send_reconcile_when_websocket_exists() -> None:
    """Send reconcile after low-level mutation helpers when websocket is available."""

    class ReconcileWebsocket:
        """Fake websocket that records reconcile requests."""

        def __init__(self) -> None:
            """Initialize call count."""
            self.calls = 0

        async def send_reconcile(self) -> None:
            """Record a reconcile request."""
            self.calls += 1

    class MutatingConnection(ApiConnectionGraphql):
        """Connection with authed queries stubbed for mutation helper tests."""

        async def authed_query(
            self,
            operation_name: str,
            query: GraphQLRequest,
            variable_values: dict[str, Any],
        ) -> dict[str, Any]:
            """Return captured mutation metadata.

            Args:
                operation_name: GraphQL operation name.
                query: Parsed GraphQL request.
                variable_values: GraphQL variables.

            Returns:
                Mutation metadata.
            """
            assert query is not None
            return {"operation": operation_name, "variables": variable_values}

    websocket = ReconcileWebsocket()
    connection = MutatingConnection(
        username="user@example.com",
        password="password",
        client_session=cast("ClientSession", FakeSession()),
    )
    connection.api_websocket = websocket  # type: ignore[assignment]
    config_variables: dict[str, Any] = {"input": {"serial": "SERIAL"}}
    zone_activity_variables: dict[str, Any] = {"input": {"serial": "SERIAL"}}
    zone_config_variables: dict[str, Any] = {"input": {"serial": "SERIAL"}}

    assert await connection._update_infinity_config(config_variables) == {
        "operation": "updateInfinityConfig",
        "variables": config_variables,
    }
    assert await connection._update_infinity_zone_activity(zone_activity_variables) == {
        "operation": "updateInfinityZoneActivity",
        "variables": zone_activity_variables,
    }
    assert await connection._update_infinity_zone_config(zone_config_variables) == {
        "operation": "updateInfinityZoneConfig",
        "variables": zone_config_variables,
    }
    assert websocket.calls == 3


@pytest.mark.asyncio
async def test_get_entry_level_systems_sends_username(connection: SpyConnection) -> None:
    """Query entry-level systems by account username."""
    await connection.get_entry_level_systems()
    assert connection.authed_calls[-1] == (
        "getEntryLevelSystems",
        {"username": connection.username},
    )


@pytest.mark.asyncio
async def test_update_entry_level_zone_builds_input(connection: SpyConnection) -> None:
    """Send only provided fields, pairing cool and heat set points."""
    await connection.update_entry_level_zone(
        "SERIALXXX",
        0,
        mode="cool",
        cool_set_point=74,
        heat_set_point=62,
    )
    operation, variables = connection.authed_calls[-1]
    assert operation == "updateEntryLevelZone"
    assert variables == {
        "input": {
            "serial": "SERIALXXX",
            "index": 0,
            "mode": "cool",
            "clsp": {"current": 74},
            "htsp": {"current": 62},
        }
    }


@pytest.mark.asyncio
async def test_hold_entry_level_zone_disables_schedule(connection: SpyConnection) -> None:
    """Holding a zone disables its schedule and applies the set point."""
    await connection.hold_entry_level_zone("SERIALXXX", cool_set_point=74)
    _, variables = connection.authed_calls[-1]
    assert variables["input"]["schedule_enabled"] is False
    assert variables["input"]["clsp"] == {"current": 74}


@pytest.mark.asyncio
async def test_resume_entry_level_schedule_enables_schedule(connection: SpyConnection) -> None:
    """Resuming a zone re-enables its schedule."""
    await connection.resume_entry_level_schedule("SERIALXXX")
    _, variables = connection.authed_calls[-1]
    assert variables["input"] == {
        "serial": "SERIALXXX",
        "index": 0,
        "schedule_enabled": True,
    }


@pytest.mark.asyncio
async def test_load_entry_level_data_parses_systems(
    connection: SpyConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Build EntryLevelSystem models from the query response."""

    async def fake_get_entry_level_systems() -> dict[str, Any]:
        return {
            "entryLevelSystems": [{"serial": "SERIALXXX", "zones": [{"index": 0, "mode": "cool"}]}]
        }

    monkeypatch.setattr(connection, "get_entry_level_systems", fake_get_entry_level_systems)
    systems = await connection.load_entry_level_data()
    assert len(systems) == 1
    assert systems[0].serial == "SERIALXXX"
    assert systems[0].zones[0].mode == "cool"
