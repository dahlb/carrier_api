"""Tests for the live smoke-test command-line helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from carrier_api.live_smoke_test import (
    CredentialSource,
    SmokeTestTranscript,
    SmokeTestOptions,
    TeeTextIO,
    load_credentials,
)


def test_load_credentials_reads_dotenv_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Credentials are read from a dotenv-style file before prompting."""
    credentials_file = tmp_path / ".carrier.env"
    credentials_file.write_text(
        "CARRIER_USERNAME=dotenv@example.com\n"
        "CARRIER_PASSWORD='dotenv password'\n",
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


def test_smoke_test_transcript_captures_traceback(tmp_path: Path) -> None:
    """Transcript files include raised exceptions for later debugging."""
    output_file = tmp_path / "smoke-output.txt"

    with pytest.raises(RuntimeError, match="live failure"):
        with SmokeTestTranscript(output_file):
            raise RuntimeError("live failure")

    output = output_file.read_text(encoding="utf-8")
    assert "RuntimeError: live failure" in output
