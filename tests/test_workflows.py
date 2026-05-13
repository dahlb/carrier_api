"""Workflow-level tests for Carrier API model, websocket, and mutation paths."""

from collections.abc import AsyncIterator
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from aiohttp import ClientSession, WSMsgType
from gql import GraphQLRequest
import pytest

from carrier_api import ApiConnectionGraphql, ApiWebsocket, WebsocketDataUpdater
from carrier_api.const import ActivityTypes, FanModes
from carrier_api.system import System

FIXTURE_ROOT = Path(__file__).parent


class FixtureLoadConnection(ApiConnectionGraphql):
    """Connection that returns fixture-backed GraphQL payloads."""

    def __init__(
        self,
        system_response: dict[str, Any],
        energy_response: dict[str, Any],
    ) -> None:
        """Initialize the fixture-backed connection.

        Args:
            system_response: Stored systems GraphQL response fixture.
            energy_response: Stored energy GraphQL response fixture.
        """
        self.system_response = system_response
        self.energy_response = energy_response
        self.energy_serials: list[str] = []

    async def get_systems(self) -> dict[str, Any]:
        """Return fixture-backed systems data.

        Returns:
            Stored systems response fixture.
        """
        return self.system_response

    async def get_energy(self, system_serial: str) -> dict[str, Any]:
        """Return fixture-backed energy data.

        Args:
            system_serial: Serial number requested by ``load_data``.

        Returns:
            Stored energy response fixture.
        """
        self.energy_serials.append(system_serial)
        return self.energy_response


@pytest.mark.asyncio
async def test_load_data_workflow_builds_usable_system_graph(
    system_response: dict[str, Any],
    energy_response: dict[str, Any],
) -> None:
    """Load fixture-backed account data into a complete usable system graph.

    Args:
        system_response: Stored systems GraphQL response fixture.
        energy_response: Stored energy GraphQL response fixture.
    """
    connection = FixtureLoadConnection(system_response, energy_response)

    systems = await connection.load_data()

    assert connection.energy_serials == ["SERIALXXX"]
    assert len(systems) == 1
    system = systems[0]
    assert isinstance(system, System)
    assert system.profile.serial == "SERIALXXX"
    assert system.status.zones[0].api_id == "1"
    assert system.config.zones[0].api_id == "1"
    assert system.energy.current_year_measurements() is not None
    assert system.as_dict()["profile"]["serial"] == "SERIALXXX"
    assert system.as_dict()["status"]["zones"][0]["conditioning"] == "active_heat"
    assert system.as_dict()["config"]["zones"][0]["activities"]
    assert system.as_dict()["energy"]["periods"][-1]["id"] == "year2"


class FakeWorkflowWebsocket:
    """Async websocket iterator for workflow tests."""

    def __init__(self, messages: list[SimpleNamespace]) -> None:
        """Initialize queued websocket messages.

        Args:
            messages: Messages yielded by the websocket iterator.
        """
        self.messages = messages
        self.closed = False

    def __aiter__(self) -> AsyncIterator[SimpleNamespace]:
        """Return this websocket as its async iterator.

        Returns:
            This websocket iterator.
        """
        return self

    async def __anext__(self) -> SimpleNamespace:
        """Yield the next queued websocket message.

        Returns:
            The next fake websocket message.

        Raises:
            StopAsyncIteration: When all messages have been consumed.
        """
        if not self.messages:
            raise StopAsyncIteration
        return self.messages.pop(0)

    async def close(self) -> None:
        """Record websocket close requests."""
        self.closed = True


class FakeWorkflowWebsocketContext:
    """Async context manager that yields a fake websocket."""

    def __init__(self, websocket: FakeWorkflowWebsocket) -> None:
        """Initialize the context with a fake websocket.

        Args:
            websocket: Fake websocket yielded by this context.
        """
        self.websocket = websocket

    async def __aenter__(self) -> FakeWorkflowWebsocket:
        """Enter the websocket context.

        Returns:
            The configured fake websocket.
        """
        return self.websocket

    async def __aexit__(self, *_args: object) -> None:
        """Exit the websocket context."""


class FakeWorkflowSession:
    """Session that returns a fake websocket context."""

    def __init__(self, websocket: FakeWorkflowWebsocket) -> None:
        """Initialize the fake session.

        Args:
            websocket: Fake websocket returned by ``ws_connect``.
        """
        self.websocket = websocket
        self.connected_url: str | None = None

    def ws_connect(self, url: str) -> FakeWorkflowWebsocketContext:
        """Capture the websocket URL and return a fake context.

        Args:
            url: Websocket URL.

        Returns:
            Fake websocket context.
        """
        self.connected_url = url
        return FakeWorkflowWebsocketContext(self.websocket)


class WorkflowConnection(ApiConnectionGraphql):
    """Connection double for websocket workflow tests."""

    def __init__(self, websocket: FakeWorkflowWebsocket) -> None:
        """Initialize websocket workflow state.

        Args:
            websocket: Fake websocket yielded by the fake session.
        """
        self.access_token = "workflow-token"
        self.workflow_session = FakeWorkflowSession(websocket)
        self.api_session = cast(ClientSession, self.workflow_session)
        self.api_websocket: ApiWebsocket | None = None
        self.auth_checks = 0

    async def check_auth_expiration(self) -> None:
        """Record auth checks before websocket connection."""
        self.auth_checks += 1


class WorkflowApiWebsocket(ApiWebsocket):
    """Websocket manager that avoids starting a real heartbeat task."""

    async def create_task_heartbeat(self) -> None:
        """Skip creating a real heartbeat task for deterministic workflow tests."""
        self.task_heartbeat = None


@pytest.mark.asyncio
async def test_websocket_listener_workflow_dispatches_updates_into_models(
    systems: list[System],
) -> None:
    """Dispatch captured websocket messages through listener callbacks into models.

    Args:
        systems: Prepared system fixture models.
    """
    message = (FIXTURE_ROOT / "messages/status_idu_cfm.json").read_text()
    websocket = FakeWorkflowWebsocket(
        [
            SimpleNamespace(type=WSMsgType.TEXT, data=message),
            SimpleNamespace(type=WSMsgType.TEXT, data="close cmd"),
        ]
    )
    connection = WorkflowConnection(websocket)
    api_websocket = WorkflowApiWebsocket(connection)
    updater = WebsocketDataUpdater(systems)

    api_websocket.callback_add(updater.message_handler)
    await api_websocket.listener()

    assert connection.auth_checks == 1
    assert connection.workflow_session.connected_url == (
        "wss://realtime.infinity.iot.carrier.com/?Token=workflow-token"
    )
    assert systems[0].status.airflow_cfm == 525
    assert websocket.closed
    assert api_websocket.websocket is None


class ReconcileRecorder:
    """Fake websocket that records reconcile calls in a shared event log."""

    def __init__(self, events: list[tuple[str, dict[str, Any] | None]]) -> None:
        """Initialize the recorder.

        Args:
            events: Shared mutation workflow event log.
        """
        self.events = events

    async def send_reconcile(self) -> None:
        """Append a reconcile event."""
        self.events.append(("reconcile", None))


class MutationWorkflowConnection(ApiConnectionGraphql):
    """Connection double that records public mutation workflow events."""

    def __init__(self) -> None:
        """Initialize mutation workflow state."""
        self.events: list[tuple[str, dict[str, Any] | None]] = []
        self.api_websocket = cast(ApiWebsocket, ReconcileRecorder(self.events))

    async def authed_query(
        self,
        operation_name: str,
        query: GraphQLRequest,
        variable_values: dict[str, Any],
    ) -> dict[str, Any]:
        """Record mutation operation metadata.

        Args:
            operation_name: GraphQL operation name.
            query: Parsed GraphQL request.
            variable_values: GraphQL variables.

        Returns:
            Captured mutation metadata.
        """
        assert query is not None
        copied_variables = deepcopy(variable_values)
        self.events.append((operation_name, copied_variables))
        return {"operation": operation_name, "variables": copied_variables}


@pytest.mark.asyncio
async def test_public_mutation_workflow_sends_expected_payloads_then_reconciles() -> None:
    """Run public mutation helpers through authed mutation calls and reconcile."""
    connection = MutationWorkflowConnection()

    manual_result = await connection.set_config_manual_activity(
        system_serial="SERIAL",
        zone_id="1",
        heat_set_point="70",
        cool_set_point="76",
        fan_mode=FanModes.LOW,
    )
    hold_result = await connection.set_config_hold(
        system_serial="SERIAL",
        zone_id="1",
        activity_type=ActivityTypes.MANUAL,
        hold_until="23:00",
    )
    resume_result = await connection.resume_schedule(system_serial="SERIAL", zone_id="1")
    humidifier_result = await connection.set_humidifier(
        system_serial="SERIAL",
        humidifier_on=False,
    )

    assert manual_result["operation"] == "updateInfinityZoneActivity"
    assert hold_result["operation"] == "updateInfinityZoneConfig"
    assert resume_result["operation"] == "updateInfinityZoneConfig"
    assert humidifier_result["operation"] == "updateInfinityConfig"
    assert connection.events == [
        (
            "updateInfinityZoneActivity",
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
        ),
        ("reconcile", None),
        (
            "updateInfinityZoneConfig",
            {
                "input": {
                    "serial": "SERIAL",
                    "zoneId": "1",
                    "hold": "on",
                    "holdActivity": "manual",
                    "otmr": "23:00",
                }
            },
        ),
        ("reconcile", None),
        (
            "updateInfinityZoneConfig",
            {
                "input": {
                    "serial": "SERIAL",
                    "zoneId": "1",
                    "hold": "off",
                    "holdActivity": None,
                    "otmr": None,
                }
            },
        ),
        ("reconcile", None),
        (
            "updateInfinityConfig",
            {
                "input": {
                    "serial": "SERIAL",
                    "humidityHome": {
                        "humid": "off",
                        "humidifier": "off",
                    },
                }
            },
        ),
        ("reconcile", None),
    ]
