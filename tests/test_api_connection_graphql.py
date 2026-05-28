"""Tests for Carrier GraphQL API connection helpers."""

from datetime import UTC, datetime, timedelta
from typing import Any, Self, cast

from aiohttp import ClientConnectionError, ClientError, ClientResponseError, ClientSession
from gql import GraphQLRequest, gql
from gql.transport.exceptions import TransportQueryError, TransportServerError
import pytest

import carrier_api
from carrier_api import errors
from carrier_api.api_connection_graphql import ApiConnectionGraphql
from carrier_api.const import ActivityTypes, FanModes, HeatSourceTypes, SystemModes
from carrier_api.system import System


class FakeResponse:
    """Minimal aiohttp response double for token refresh tests."""

    def __init__(
        self,
        payload: object,
        status_error: ClientResponseError | None = None,
        json_error: BaseException | None = None,
    ) -> None:
        """Initialize the fake response with JSON payload data.

        Args:
            payload: Data returned from ``json``.
            status_error: Optional error raised by ``raise_for_status``.
            json_error: Optional error raised by ``json``.
        """
        self.payload = payload
        self.status_error = status_error
        self.json_error = json_error
        self.raise_for_status_called = False

    def raise_for_status(self) -> None:
        """Record status validation and raise the configured status error.

        Raises:
            ClientResponseError: When ``status_error`` is configured.
        """
        self.raise_for_status_called = True
        if self.status_error is not None:
            raise self.status_error

    async def json(self) -> object:
        """Return the configured JSON payload.

        Returns:
            The fake response payload.

        Raises:
            BaseException: When ``json_error`` is configured.
        """
        if self.json_error is not None:
            raise self.json_error
        return self.payload


class FakeSession:
    """Minimal session double used by connection tests."""

    def __init__(self) -> None:
        """Initialize captured session state."""
        self.closed = False
        self.post_url: str | None = None
        self.post_data: dict[str, Any] | None = None
        self.response = FakeResponse(
            {
                "expires_in": 3600,
                "token_type": "Bearer",
                "access_token": "new-access",
                "refresh_token": "new-refresh",
            }
        )

    async def close(self) -> None:
        """Record that the session was closed."""
        self.closed = True

    async def post(self, url: str, data: dict[str, Any]) -> FakeResponse:
        """Capture a token refresh request.

        Args:
            url: Requested URL.
            data: Submitted form data.

        Returns:
            The fake token refresh response.
        """
        self.post_url = url
        self.post_data = data
        return self.response


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


@pytest.mark.asyncio
async def test_refresh_auth_token_updates_token_state() -> None:
    """Refresh auth tokens from the OAuth response payload."""
    session = FakeSession()
    connection = ApiConnectionGraphql(
        username="user@example.com",
        password="password",
        client_session=cast("ClientSession", session),
    )
    connection.refresh_token = "old-refresh"

    await connection.refresh_auth_token()

    assert session.response.raise_for_status_called
    assert session.post_url == "https://sso.carrier.com/oauth2/default/v1/token"
    assert session.post_data == {
        "client_id": "0oa1ce7hwjuZbfOMB4x7",
        "grant_type": "refresh_token",
        "refresh_token": "old-refresh",
        "scope": "offline_access",
    }
    assert connection.token_type == "Bearer"
    assert connection.access_token == "new-access"
    assert connection.refresh_token == "new-refresh"
    assert connection.expires_at > datetime.now(UTC)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "refresh_error",
    [
        ClientConnectionError("token refresh connection failed"),
        TimeoutError("token refresh timed out"),
        OSError("token refresh socket failed"),
    ],
)
async def test_refresh_auth_token_wraps_refresh_failures(
    refresh_error: ClientError | TimeoutError | OSError,
) -> None:
    """Raise Carrier token refresh errors instead of raw HTTP exceptions."""

    class FailingSession(FakeSession):
        """Session double that fails token refresh requests."""

        async def post(self, url: str, data: dict[str, Any]) -> FakeResponse:
            """Raise the configured refresh error.

            Args:
                url: Requested URL.
                data: Submitted form data.

            Raises:
                ClientError | TimeoutError | OSError: Always raised for this
                    failing session.
            """
            raise refresh_error

    connection = ApiConnectionGraphql(
        username="user@example.com",
        password="password",
        client_session=cast("ClientSession", FailingSession()),
    )
    connection.refresh_token = "old-refresh"

    with pytest.raises(errors.CarrierApiTokenRefreshError) as error:
        await connection.refresh_auth_token()

    assert error.value.__cause__ is refresh_error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "payload"),
    [(401, {}), (400, {"error": "invalid_grant"})],
)
async def test_refresh_auth_token_treats_auth_rejections_as_auth_error(
    status: int,
    payload: object,
) -> None:
    """Raise auth errors for rejected token refresh responses.

    Args:
        status: HTTP status returned by the fake token endpoint.
        payload: JSON payload returned by the fake token endpoint.
    """
    refresh_error = ClientResponseError(
        request_info=None,  # type: ignore[arg-type]
        history=(),
        status=status,
        message="token rejected",
    )

    session = FakeSession()
    session.response = FakeResponse(payload, status_error=refresh_error)
    connection = ApiConnectionGraphql(
        username="user@example.com",
        password="password",
        client_session=cast("ClientSession", session),
    )
    connection.refresh_token = "old-refresh"

    with pytest.raises(errors.CarrierApiAuthError) as error:
        await connection.refresh_auth_token()

    assert error.value.__cause__ is refresh_error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "json_error",
    [
        TimeoutError("refresh error body timed out"),
        OSError("refresh error body socket failed"),
    ],
)
async def test_refresh_auth_token_normalizes_unreadable_error_payloads(
    json_error: TimeoutError | OSError,
) -> None:
    """Raise Carrier errors when refresh error payload reads fail.

    Args:
        json_error: Error raised while reading the refresh error response body.
    """
    refresh_error = ClientResponseError(
        request_info=None,  # type: ignore[arg-type]
        history=(),
        status=401,
        message="unauthorized",
    )

    session = FakeSession()
    session.response = FakeResponse(
        {},
        status_error=refresh_error,
        json_error=json_error,
    )
    connection = ApiConnectionGraphql(
        username="user@example.com",
        password="password",
        client_session=cast("ClientSession", session),
    )
    connection.refresh_token = "old-refresh"

    with pytest.raises(errors.CarrierApiAuthError) as error:
        await connection.refresh_auth_token()

    assert error.value.__cause__ is refresh_error


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [None, ["invalid_grant"], "invalid_grant"])
async def test_refresh_auth_token_ignores_non_object_error_payloads(
    payload: object,
) -> None:
    """Keep non-object refresh error payloads in the refresh-failure bucket.

    Args:
        payload: Non-object JSON payload returned by the fake response.
    """
    refresh_error = ClientResponseError(
        request_info=None,  # type: ignore[arg-type]
        history=(),
        status=400,
        message="bad request",
    )

    session = FakeSession()
    session.response = FakeResponse(payload, status_error=refresh_error)
    connection = ApiConnectionGraphql(
        username="user@example.com",
        password="password",
        client_session=cast("ClientSession", session),
    )
    connection.refresh_token = "old-refresh"

    with pytest.raises(errors.CarrierApiTokenRefreshError) as error:
        await connection.refresh_auth_token()

    assert error.value.__cause__ is refresh_error


@pytest.mark.asyncio
async def test_refresh_auth_token_normalizes_malformed_error_payload() -> None:
    """Keep malformed refresh error payloads normalized as Carrier errors."""
    refresh_error = ClientResponseError(
        request_info=None,  # type: ignore[arg-type]
        history=(),
        status=400,
        message="bad request",
    )

    session = FakeSession()
    session.response = FakeResponse(
        {},
        status_error=refresh_error,
        json_error=ValueError("invalid json"),
    )
    connection = ApiConnectionGraphql(
        username="user@example.com",
        password="password",
        client_session=cast("ClientSession", session),
    )
    connection.refresh_token = "old-refresh"

    with pytest.raises(errors.CarrierApiTokenRefreshError) as error:
        await connection.refresh_auth_token()

    assert error.value.__cause__ is refresh_error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "cause_type"),
    [
        (
            {
                "expires_in": 3600,
                "token_type": "Bearer",
                "access_token": "new-access",
            },
            KeyError,
        ),
        (None, TypeError),
    ],
)
async def test_refresh_auth_token_normalizes_malformed_success_payloads(
    payload: object,
    cause_type: type[BaseException],
) -> None:
    """Raise token refresh errors for malformed successful OAuth responses.

    Args:
        payload: Malformed successful OAuth payload returned by the fake response.
        cause_type: Expected original exception type preserved as the cause.
    """
    session = FakeSession()
    session.response = FakeResponse(payload)
    connection = ApiConnectionGraphql(
        username="user@example.com",
        password="password",
        client_session=cast("ClientSession", session),
    )
    connection.refresh_token = "old-refresh"

    with pytest.raises(errors.CarrierApiTokenRefreshError) as error:
        await connection.refresh_auth_token()

    assert isinstance(error.value.__cause__, cause_type)


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
