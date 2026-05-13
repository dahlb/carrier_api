"""Tests for Carrier GraphQL API connection helpers."""

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from aiohttp import ClientSession
from gql import GraphQLRequest
import pytest

from carrier_api.api_connection_graphql import ApiConnectionGraphql
from carrier_api.const import ActivityTypes, FanModes, HeatSourceTypes, SystemModes
from carrier_api.system import System


class FakeResponse:
    """Minimal aiohttp response double for token refresh tests."""

    def __init__(self, payload: dict[str, Any]) -> None:
        """Initialize the fake response with JSON payload data.

        Args:
            payload: Data returned from ``json``.
        """
        self.payload = payload
        self.raise_for_status_called = False

    def raise_for_status(self) -> None:
        """Record that response status validation was requested."""
        self.raise_for_status_called = True

    async def json(self) -> dict[str, Any]:
        """Return the configured JSON payload.

        Returns:
            The fake response payload.
        """
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


class SpyConnection(ApiConnectionGraphql):
    """Connection test double that captures GraphQL and mutation calls."""

    def __init__(self) -> None:
        """Initialize the connection with a fake HTTP session."""
        super().__init__(
            username="user@example.com",
            password="password",
            client_session=cast(ClientSession, FakeSession()),
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


@pytest.fixture
def connection() -> SpyConnection:
    """Build a spy connection for API helper tests.

    Returns:
        A connection double that captures calls instead of using the network.
    """
    return SpyConnection()


@pytest.mark.asyncio
async def test_cleanup_closes_provided_session() -> None:
    """Close the underlying HTTP session."""
    session = FakeSession()
    connection = ApiConnectionGraphql(
        username="user@example.com",
        password="password",
        client_session=cast(ClientSession, session),
    )

    await connection.cleanup()

    assert session.closed


@pytest.mark.asyncio
async def test_refresh_auth_token_updates_token_state() -> None:
    """Refresh auth tokens from the OAuth response payload."""
    session = FakeSession()
    connection = ApiConnectionGraphql(
        username="user@example.com",
        password="password",
        client_session=cast(ClientSession, session),
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
        client_session=cast(ClientSession, FakeSession()),
    )
    connection.api_websocket = websocket  # type: ignore[assignment]
    variables: dict[str, Any] = {"input": {"serial": "SERIAL"}}

    assert await connection._update_infinity_config(variables) == {
        "operation": "updateInfinityConfig",
        "variables": variables,
    }
    assert await connection._update_infinity_zone_activity(variables) == {
        "operation": "updateInfinityZoneActivity",
        "variables": variables,
    }
    assert await connection._update_infinity_zone_config(variables) == {
        "operation": "updateInfinityZoneConfig",
        "variables": variables,
    }
    assert websocket.calls == 3
