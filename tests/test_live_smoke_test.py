"""Tests for the live smoke-test command-line helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from gql.transport.exceptions import TransportServerError
import pytest

from carrier_api.api_connection_graphql import ApiConnectionGraphql
from carrier_api.live_smoke_test import (
    CredentialSource,
    SmokeTestOptions,
    SmokeTestTranscript,
    TeeTextIO,
    load_credentials,
    maybe_send_sample_manual_activity_update,
    parse_args,
    send_sample_manual_activity_update,
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


def test_smoke_test_transcript_captures_traceback(tmp_path: Path) -> None:
    """Transcript files include raised exceptions for later debugging."""
    output_file = tmp_path / "smoke-output.txt"

    with pytest.raises(RuntimeError, match="live failure"), SmokeTestTranscript(output_file):
        raise RuntimeError("live failure")

    output = output_file.read_text(encoding="utf-8")
    assert "RuntimeError: live failure" in output
