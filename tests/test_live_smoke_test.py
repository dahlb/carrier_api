"""Tests for the live smoke-test command-line helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Self, cast

from gql import GraphQLRequest
from gql.transport.exceptions import TransportServerError
import pytest

from carrier_api.api_connection_graphql import ApiConnectionGraphql
from carrier_api.live_smoke_test import (
    CredentialSource,
    SmokeTestOptions,
    SmokeTestTranscript,
    TeeTextIO,
    load_credentials,
    main,
    maybe_send_sample_manual_activity_update,
    parse_args,
    send_sample_manual_activity_update,
    write_captured_schema,
    write_schema_output,
)


def test_load_credentials_reads_dotenv_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Credentials are read from a dotenv-style file before prompting."""
    credentials_file = tmp_path / ".carrier.env"
    credentials_file.write_text(
        "CARRIER_USERNAME=dotenv@example.com\nCARRIER_PASSWORD='dotenv password'\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("CARRIER_USERNAME", raising=False)
    monkeypatch.delenv("CARRIER_PASSWORD", raising=False)

    credentials = load_credentials(SmokeTestOptions(credentials_file=credentials_file))

    assert credentials == CredentialSource(
        username="dotenv@example.com",
        password="dotenv password",
        description=str(credentials_file),
    )


def test_load_credentials_prefers_file_over_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit credential files take precedence over process environment."""
    credentials_file = tmp_path / "carrier.toml"
    credentials_file.write_text(
        'username = "file@example.com"\npassword = "file-password"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("CARRIER_USERNAME", "env@example.com")
    monkeypatch.setenv("CARRIER_PASSWORD", "env-password")

    credentials = load_credentials(SmokeTestOptions(credentials_file=credentials_file))

    assert credentials == CredentialSource(
        username="file@example.com",
        password="file-password",
        description=str(credentials_file),
    )


def test_load_credentials_reads_carrier_toml_section(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TOML credentials can be grouped under a carrier section."""
    credentials_file = tmp_path / "carrier.toml"
    credentials_file.write_text(
        '[carrier]\nusername = "section@example.com"\npassword = "section-password"\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("CARRIER_USERNAME", raising=False)
    monkeypatch.delenv("CARRIER_PASSWORD", raising=False)

    credentials = load_credentials(SmokeTestOptions(credentials_file=credentials_file))

    assert credentials == CredentialSource(
        username="section@example.com",
        password="section-password",
        description=str(credentials_file),
    )


def test_load_credentials_rejects_partial_credentials_file(tmp_path: Path) -> None:
    """Explicit credential files fail fast when a value is missing."""
    credentials_file = tmp_path / ".carrier.env"
    credentials_file.write_text("CARRIER_USERNAME=partial@example.com\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must include both"):
        load_credentials(SmokeTestOptions(credentials_file=credentials_file))


def test_load_credentials_rejects_json_null_values(tmp_path: Path) -> None:
    """JSON null credentials do not become literal None strings."""
    credentials_file = tmp_path / "carrier.json"
    credentials_file.write_text('{"username": null, "password": null}', encoding="utf-8")

    with pytest.raises(ValueError, match="must include both"):
        load_credentials(SmokeTestOptions(credentials_file=credentials_file))


def test_load_credentials_uses_environment_when_file_is_not_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Environment credentials are used when no file path is provided."""
    monkeypatch.setenv("CARRIER_USERNAME", "env@example.com")
    monkeypatch.setenv("CARRIER_PASSWORD", "env-password")

    credentials = load_credentials(SmokeTestOptions())

    assert credentials == CredentialSource(
        username="env@example.com",
        password="env-password",
        description="environment variables",
    )


def test_load_credentials_returns_none_for_partial_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Partial environment credentials do not suppress the interactive prompt."""
    monkeypatch.setenv("CARRIER_USERNAME", "env@example.com")
    monkeypatch.delenv("CARRIER_PASSWORD", raising=False)

    assert load_credentials(SmokeTestOptions()) is None


def test_tee_text_io_writes_to_stream_and_output_file(tmp_path: Path) -> None:
    """Tee text output preserves console behavior while writing a transcript."""
    output_file = tmp_path / "smoke-output.txt"
    console_file = tmp_path / "console-output.txt"

    with (
        console_file.open("w", encoding="utf-8") as console,
        output_file.open("w", encoding="utf-8") as transcript,
    ):
        tee = TeeTextIO(console, transcript)
        written = tee.write("captured output\n")
        tee.flush()

    assert written == len("captured output\n")
    assert console_file.read_text(encoding="utf-8") == "captured output\n"
    assert output_file.read_text(encoding="utf-8") == "captured output\n"


def test_parse_args_accepts_schema_output_file() -> None:
    """Command-line options include a path for captured schema output."""
    options = parse_args(
        [
            "--credentials-file",
            "live_smoke_test.env",
            "--output-file",
            "/tmp/smoke.txt",
            "--schema-output-file",
            "/tmp/schema.json",
        ],
    )

    assert options == SmokeTestOptions(
        credentials_file=Path("live_smoke_test.env"),
        output_file=Path("/tmp/smoke.txt"),
        schema_output_file=Path("/tmp/schema.json"),
    )


def test_parse_args_accepts_read_only() -> None:
    """Command-line options can disable the sample thermostat mutation."""
    options = parse_args(["--read-only"])

    assert options.read_only is True


def test_parse_args_resolves_relative_paths_from_launcher_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Relative paths survive the launcher changing to the project root."""
    monkeypatch.setenv("CARRIER_API_LIVE_SMOKE_CWD", str(tmp_path))

    options = parse_args(
        [
            "--credentials-file",
            "./live_smoke_test.env",
            "--output-file",
            "smoke.txt",
            "--schema-output-file",
            "schema.json",
        ],
    )

    assert options == SmokeTestOptions(
        credentials_file=tmp_path / "live_smoke_test.env",
        output_file=tmp_path / "smoke.txt",
        schema_output_file=tmp_path / "schema.json",
    )


@pytest.mark.asyncio
async def test_main_writes_schema_before_loading_live_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Schema capture happens before the live data load and websocket wait."""
    calls: list[str] = []

    class FakeWebsocket:
        """Minimal websocket double for the live smoke-test listener setup."""

        websocket = None
        task_listener = None
        task_heartbeat = None
        running = False

        def callback_add(self, callback: object) -> None:
            """Record callback registration.

            Args:
                callback: Callback registered by the smoke test.
            """
            calls.append("callback")

        async def create_task_listener(self) -> None:
            """Record listener startup."""
            calls.append("listener")

    class FakeConnection:
        """Connection double that records live smoke-test operation order."""

        def __init__(self, username: str, password: str) -> None:
            """Initialize the fake connection.

            Args:
                username: Carrier account username.
                password: Carrier account password.
            """
            self.username = username
            self.password = password
            self.api_websocket = FakeWebsocket()

        async def load_data(self) -> list[Any]:
            """Record live data loading.

            Returns:
                Minimal system data for listener setup.
            """
            calls.append("load")
            return [
                SimpleNamespace(
                    as_dict=lambda: {"serial": "serial-1"},
                    profile=SimpleNamespace(serial="serial-1"),
                    config=SimpleNamespace(zones=[SimpleNamespace(api_id="zone-1")]),
                )
            ]

        async def cleanup(self) -> None:
            """Record cleanup."""
            calls.append("cleanup")

    async def fake_write_captured_schema(
        api_connection: ApiConnectionGraphql,
        schema_output_file: Path,
    ) -> None:
        """Record schema capture.

        Args:
            api_connection: API connection passed to schema capture.
            schema_output_file: Schema output path.
        """
        calls.append("schema")

    async def fake_sleep(seconds: float) -> None:
        """Record the websocket observation wait.

        Args:
            seconds: Wait duration.
        """
        calls.append("sleep")

    monkeypatch.setattr(
        "carrier_api.live_smoke_test.ApiConnectionGraphql",
        FakeConnection,
    )
    monkeypatch.setattr(
        "carrier_api.live_smoke_test.write_captured_schema", fake_write_captured_schema
    )
    monkeypatch.setattr("carrier_api.live_smoke_test.sleep", fake_sleep)

    credentials_file = tmp_path / "carrier.env"
    credentials_file.write_text(
        "CARRIER_USERNAME=test@example.com\nCARRIER_PASSWORD=password\n",
        encoding="utf-8",
    )

    await main(
        SmokeTestOptions(
            credentials_file=credentials_file,
            schema_output_file=tmp_path / "schema.json",
            read_only=True,
        ),
    )

    assert calls.index("schema") < calls.index("load")
    assert calls.index("schema") < calls.index("sleep")


@pytest.mark.asyncio
async def test_maybe_send_sample_manual_activity_update_skips_read_only(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Read-only mode skips the sample thermostat mutation."""

    class FailingConnection:
        """Connection double that must not be called in read-only mode."""

        async def set_config_manual_activity(self, **kwargs: Any) -> None:
            """Fail if the mutation is attempted.

            Args:
                kwargs: Captured mutation arguments.
            """
            raise AssertionError("mutation should not be called")

    sent = await maybe_send_sample_manual_activity_update(
        cast("ApiConnectionGraphql", FailingConnection()),
        [],
        read_only=True,
    )

    assert sent is False
    assert "Read-only mode enabled" in capsys.readouterr().out


def test_write_schema_output_writes_pretty_json(tmp_path: Path) -> None:
    """Captured GraphQL schema data is written as inspectable JSON."""
    schema_output_file = tmp_path / "nested" / "schema.json"

    write_schema_output(
        schema_output_file,
        {"__schema": {"queryType": {"name": "Query"}}},
    )

    assert schema_output_file.read_text(encoding="utf-8") == (
        '{\n  "__schema": {\n    "queryType": {\n      "name": "Query"\n    }\n  }\n}'
    )


@pytest.mark.asyncio
async def test_write_captured_schema_executes_with_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Schema capture uses the gql session so timeout and query errors apply."""

    class FakeTransport:
        """Transport double that must not execute queries directly."""

        def __init__(self, **kwargs: Any) -> None:
            """Accept transport constructor arguments.

            Args:
                kwargs: Transport keyword arguments.
            """

        async def execute(self, query: GraphQLRequest) -> dict[str, Any]:
            """Fail if schema capture bypasses the session.

            Args:
                query: GraphQL request.
            """
            raise AssertionError("transport.execute should not be called directly")

    class FakeClient:
        """gql client double that captures session execution."""

        def __init__(self, **kwargs: Any) -> None:
            """Initialize fake client state.

            Args:
                kwargs: Client keyword arguments.
            """
            self.client = SimpleNamespace(introspection_args={})
            self.execute_timeout = kwargs["execute_timeout"]

        async def __aenter__(self) -> Self:
            """Enter the async context manager.

            Returns:
                The fake client.
            """
            return self

        async def __aexit__(self, *args: object) -> None:
            """Exit the async context manager.

            Args:
                args: Context manager exception details.
            """

        async def execute(self, query: GraphQLRequest) -> dict[str, Any]:
            """Return fake introspection data through the session path.

            Args:
                query: GraphQL request.

            Returns:
                Fake schema payload.
            """
            return {"__schema": {"queryType": {"name": "Query"}}}

    class FakeConnection:
        """Connection double for schema capture."""

        token_type = "Bearer"
        access_token = "access"

        async def check_auth_expiration(self) -> None:
            """Record that auth was checked."""

    monkeypatch.setattr("carrier_api.live_smoke_test.AIOHTTPTransport", FakeTransport)
    monkeypatch.setattr("carrier_api.live_smoke_test.Client", FakeClient)
    schema_output_file = tmp_path / "schema.json"

    await write_captured_schema(
        cast("ApiConnectionGraphql", FakeConnection()),
        schema_output_file,
    )

    assert "Query" in schema_output_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_write_captured_schema_propagates_session_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GraphQL introspection errors are not written as successful schemas."""

    class FakeTransport:
        """Transport double for schema capture."""

        def __init__(self, **kwargs: Any) -> None:
            """Accept transport constructor arguments.

            Args:
                kwargs: Transport keyword arguments.
            """

    class FakeClient:
        """gql client double that raises from session execution."""

        def __init__(self, **kwargs: Any) -> None:
            """Initialize fake client state.

            Args:
                kwargs: Client keyword arguments.
            """
            self.client = SimpleNamespace(introspection_args={})

        async def __aenter__(self) -> Self:
            """Enter the async context manager.

            Returns:
                The fake client.
            """
            return self

        async def __aexit__(self, *args: object) -> None:
            """Exit the async context manager.

            Args:
                args: Context manager exception details.
            """

        async def execute(self, query: GraphQLRequest) -> dict[str, Any]:
            """Raise a GraphQL execution failure.

            Args:
                query: GraphQL request.
            """
            raise RuntimeError("introspection failed")

    class FakeConnection:
        """Connection double for schema capture."""

        token_type = "Bearer"
        access_token = "access"

        async def check_auth_expiration(self) -> None:
            """Record that auth was checked."""

    monkeypatch.setattr("carrier_api.live_smoke_test.AIOHTTPTransport", FakeTransport)
    monkeypatch.setattr("carrier_api.live_smoke_test.Client", FakeClient)
    schema_output_file = tmp_path / "schema.json"

    with pytest.raises(RuntimeError, match="introspection failed"):
        await write_captured_schema(
            cast("ApiConnectionGraphql", FakeConnection()),
            schema_output_file,
        )

    assert not schema_output_file.exists()


@pytest.mark.asyncio
async def test_send_sample_manual_activity_update_continues_on_gateway_timeout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Carrier mutation gateway failures are captured without ending the smoke test."""

    class FailingConnection:
        """Connection double that raises the Carrier gateway timeout shape."""

        async def set_config_manual_activity(self, **kwargs: Any) -> None:
            """Raise the same transport error produced by Carrier 504 responses.

            Args:
                kwargs: Captured mutation arguments.
            """
            raise TransportServerError("504 Gateway Timeout", 504)

    systems = [
        SimpleNamespace(
            profile=SimpleNamespace(serial="serial-1"),
            config=SimpleNamespace(zones=[SimpleNamespace(api_id="zone-1")]),
        )
    ]

    updated = await send_sample_manual_activity_update(
        cast("ApiConnectionGraphql", FailingConnection()),
        systems,
    )

    assert updated is False
    assert "Manual activity update failed" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_send_sample_manual_activity_update_reraises_non_timeout_server_errors() -> None:
    """Only Carrier gateway timeouts are downgraded to smoke-test warnings."""

    class FailingConnection:
        """Connection double that raises a non-timeout server failure."""

        async def set_config_manual_activity(self, **kwargs: Any) -> None:
            """Raise a non-timeout transport error.

            Args:
                kwargs: Captured mutation arguments.
            """
            raise TransportServerError("401 Unauthorized", 401)

    systems = [
        SimpleNamespace(
            profile=SimpleNamespace(serial="serial-1"),
            config=SimpleNamespace(zones=[SimpleNamespace(api_id="zone-1")]),
        )
    ]

    with pytest.raises(TransportServerError, match="401 Unauthorized"):
        await send_sample_manual_activity_update(
            cast("ApiConnectionGraphql", FailingConnection()),
            systems,
        )


def test_smoke_test_transcript_captures_traceback(tmp_path: Path) -> None:
    """Transcript files include raised exceptions for later debugging."""
    output_file = tmp_path / "smoke-output.txt"

    with pytest.raises(RuntimeError, match="live failure"), SmokeTestTranscript(output_file):
        raise RuntimeError("live failure")

    output = output_file.read_text(encoding="utf-8")
    assert "RuntimeError: live failure" in output
