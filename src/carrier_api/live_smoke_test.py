"""Manual live Carrier API smoke-test script for local development.

This module is an interactive development harness, not part of the automated
pytest suite. It connects to the real Carrier API with credentials entered at
the terminal, loads the account's configured systems, prints their current
structured state, subscribes to websocket updates, and sends one sample manual
activity update to the first available zone.

Use this when developing or debugging behavior that needs a live Carrier
account, such as captured GraphQL payloads, websocket reconciliation, manual
activity mutations, or field changes that are hard to represent from stored
fixtures alone. Do not use it as a substitute for adding deterministic tests in
``tests/``; any fixed behavior should still be covered by pytest fixtures or
unit tests where practical.

The script intentionally prints raw inspected state to the console and mutates
``sys.path`` so it can be run directly from a source checkout without installing
the package first. It may change a thermostat's active settings because it calls
``set_config_manual_activity`` with sample heat, cool, and fan values.

Run it through the repository helper script so it starts from the project root
and uses the repository virtual environment:
``scripts/live_smoke_test``.
"""

from argparse import ArgumentParser, Namespace
import asyncio
from asyncio import CancelledError, Task, sleep
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
from getpass import getpass
import json
import logging
import os
from pathlib import Path
import sys
import tomllib
import traceback as traceback_module
from types import TracebackType
from typing import Any, TextIO

from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
from gql.transport.exceptions import TransportServerError
from graphql import get_introspection_query

path_src = Path(__file__).parents[1]
sys.path.append(str(path_src))

from carrier_api.api_connection_graphql import GRAPHQL_EXECUTE_TIMEOUT_SECONDS, ApiConnectionGraphql
from carrier_api.api_websocket_data_updater import WebsocketDataUpdater
from carrier_api.const import FanModes

logger = logging.getLogger("carrier_api")
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)

SMOKE_TEST_WAIT_SECONDS = 300
USERNAME_KEYS = ("CARRIER_USERNAME", "CARRIER_EMAIL", "username", "email", "name")
PASSWORD_KEYS = ("CARRIER_PASSWORD", "password")

INTRO_TEXT = """\
This smoke test connects to the live Carrier API.
It loads your configured systems, prints their current state, starts websocket
updates, sends one sample manual activity update to the first available zone,
and then waits so incoming realtime messages can be observed.

Unless ``--read-only`` is provided, this script will change thermostat settings
on the first available zone: it sets the heat set point to 73, the cool set
point to 80, and the fan mode to low. After that update, it waits 5 minutes, so
the terminal will appear to pause while it listens for websocket messages.

Enter the Carrier or Bryant account email address and password that you
use for the official thermostat app. These credentials are read from this
terminal session only; the script does not store them.
"""


@dataclass(frozen=True)
class CredentialSource:
    """Carrier credentials loaded from a non-interactive source.

    Args:
        username: Carrier or Bryant account email address.
        password: Carrier or Bryant account password.
        description: Human-readable source description for console output.
    """

    username: str
    password: str
    description: str


@dataclass(frozen=True)
class SmokeTestOptions:
    """Parsed smoke-test command-line options.

    Args:
        credentials_file: Optional file to read Carrier credentials from.
        output_file: Optional file to write a full smoke-test transcript to.
        schema_output_file: Optional file to write captured GraphQL schema to.
        read_only: Whether to skip the sample thermostat mutation.
    """

    credentials_file: Path | None = None
    output_file: Path | None = None
    schema_output_file: Path | None = None
    read_only: bool = False


class TeeTextIO:
    """Text stream that writes to a console stream and a transcript file."""

    def __init__(self, console: TextIO, transcript: TextIO) -> None:
        """Initialize the tee stream.

        Args:
            console: Original console stream.
            transcript: Output transcript stream.
        """
        self._console = console
        self._transcript = transcript
        self.encoding = getattr(console, "encoding", None)

    def write(self, text: str) -> int:
        """Write text to both wrapped streams.

        Args:
            text: Text to write.

        Returns:
            The number of characters accepted by the console stream.
        """
        written = self._console.write(text)
        self._transcript.write(text)
        return written

    def flush(self) -> None:
        """Flush both wrapped streams."""
        self._console.flush()
        self._transcript.flush()

    def isatty(self) -> bool:
        """Return whether the console stream is attached to a terminal.

        Returns:
            True when the original console stream is a TTY.
        """
        return self._console.isatty()


class SmokeTestTranscript:
    """Context manager that tees console and log output to a file."""

    def __init__(self, output_file: Path) -> None:
        """Initialize transcript capture.

        Args:
            output_file: File that should receive the captured transcript.
        """
        self._output_file = output_file
        self._transcript: TextIO | None = None
        self._stdout: TextIO | None = None
        self._stderr: TextIO | None = None
        self._original_handler_streams: list[tuple[logging.StreamHandler, TextIO]] = []

    def __enter__(self) -> None:
        """Start teeing stdout, stderr, and logger streams."""
        self._output_file.parent.mkdir(parents=True, exist_ok=True)
        self._transcript = self._output_file.open("w", encoding="utf-8")
        self._stdout = sys.stdout
        self._stderr = sys.stderr
        sys.stdout = TeeTextIO(sys.stdout, self._transcript)
        sys.stderr = TeeTextIO(sys.stderr, self._transcript)
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                self._original_handler_streams.append((handler, handler.stream))
                handler.setStream(sys.stderr)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stop teeing output and close the transcript file.

        Args:
            exc_type: Exception type raised inside the context, if any.
            exc_value: Exception raised inside the context, if any.
            traceback: Traceback raised inside the context, if any.
        """
        for handler, stream in self._original_handler_streams:
            handler.setStream(stream)
        if self._stdout is not None:
            sys.stdout = self._stdout
        if self._stderr is not None:
            sys.stderr = self._stderr
        if exc_type is not None and self._transcript is not None:
            traceback_module.print_exception(
                exc_type,
                exc_value,
                traceback,
                file=self._transcript,
            )
        if self._transcript is not None:
            self._transcript.close()


def parse_args(argv: list[str] | None = None) -> SmokeTestOptions:
    """Parse command-line arguments for the live smoke test.

    Args:
        argv: Optional argument list. Uses process arguments when omitted.

    Returns:
        Parsed smoke-test options.
    """
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--credentials-file",
        type=Path,
        help=(
            "Read credentials from a .env, TOML, or JSON file. Supported keys "
            "include CARRIER_USERNAME/CARRIER_PASSWORD and username/password."
        ),
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        help="Write stdout, stderr, and smoke-test logs to this transcript file.",
    )
    parser.add_argument(
        "--schema-output-file",
        type=Path,
        help="Write the authenticated GraphQL introspection schema to this JSON file.",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Skip the sample thermostat mutation while leaving other smoke-test steps enabled.",
    )
    namespace: Namespace = parser.parse_args(argv)
    return SmokeTestOptions(
        credentials_file=resolve_invocation_path(namespace.credentials_file),
        output_file=resolve_invocation_path(namespace.output_file),
        schema_output_file=resolve_invocation_path(namespace.schema_output_file),
        read_only=namespace.read_only,
    )


def resolve_invocation_path(path: Path | None) -> Path | None:
    """Resolve a command-line path relative to the launcher invocation directory.

    Args:
        path: Optional path from a command-line argument.

    Returns:
        Absolute path when a relative path was supplied through the launcher.
    """
    if path is None or path.is_absolute():
        return path
    invocation_cwd = os.environ.get("CARRIER_API_LIVE_SMOKE_CWD")
    if invocation_cwd is None:
        return path
    return Path(invocation_cwd) / path


def strip_env_value(value: str) -> str:
    """Normalize a dotenv value by trimming whitespace and quotes.

    Args:
        value: Raw value read from a dotenv line.

    Returns:
        Normalized dotenv value.
    """
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    return stripped


def read_dotenv_credentials(credentials_file: Path) -> dict[str, str]:
    """Read key-value credentials from a dotenv-style file.

    Args:
        credentials_file: File containing one ``KEY=value`` entry per line.

    Returns:
        Parsed dotenv key-value mapping.
    """
    credentials: dict[str, str] = {}
    for line in credentials_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", maxsplit=1)
        credentials[key.strip()] = strip_env_value(value)
    return credentials


def read_credentials_file(credentials_file: Path) -> dict[str, Any]:
    """Read Carrier credentials from a supported config file format.

    Args:
        credentials_file: .env, TOML, or JSON credential file.

    Returns:
        Parsed credential mapping.
    """
    if credentials_file.suffix == ".json":
        with credentials_file.open(encoding="utf-8") as file:
            data = json.load(file)
        if isinstance(data, dict):
            return {str(key): value for key, value in data.items()}
        raise ValueError("JSON credentials file must contain an object")
    if credentials_file.suffix == ".toml":
        with credentials_file.open("rb") as file:
            data = tomllib.load(file)
        carrier_data = data.get("carrier")
        if isinstance(carrier_data, dict):
            return {str(key): value for key, value in carrier_data.items()}
        return {str(key): value for key, value in data.items()}
    return read_dotenv_credentials(credentials_file)


def find_first_value(credentials: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    """Find the first non-empty credential value among supported keys.

    Args:
        credentials: Credential mapping to inspect.
        keys: Ordered candidate key names.

    Returns:
        First matching non-empty value, or None.
    """
    for key in keys:
        value = credentials.get(key)
        if value is None:
            continue
        value_text = str(value)
        if value_text:
            return value_text
    return None


def credential_source_from_mapping(
    credentials: Mapping[str, Any],
    description: str,
) -> CredentialSource | None:
    """Build a credential source from a mapping when both values are present.

    Args:
        credentials: Mapping that may contain username and password values.
        description: Source description for console output.

    Returns:
        Credential source when both username and password are present.
    """
    username = find_first_value(credentials, USERNAME_KEYS)
    password = find_first_value(credentials, PASSWORD_KEYS)
    if username is None or password is None:
        return None
    return CredentialSource(username=username, password=password, description=description)


def load_credentials(options: SmokeTestOptions) -> CredentialSource | None:
    """Load Carrier credentials from file or environment when available.

    Args:
        options: Smoke-test command-line options.

    Returns:
        Non-interactive credential source when both credentials are found.
    """
    if options.credentials_file is not None:
        credentials = read_credentials_file(options.credentials_file)
        credential_source = credential_source_from_mapping(
            credentials,
            str(options.credentials_file),
        )
        if credential_source is None:
            raise ValueError("Credentials file must include both username and password")
        return credential_source
    return credential_source_from_mapping(os.environ, "environment variables")


def write_schema_output(schema_output_file: Path, schema_data: dict[str, Any]) -> None:
    """Write captured GraphQL schema data to an inspectable JSON file.

    Args:
        schema_output_file: File that should receive the schema JSON.
        schema_data: GraphQL introspection response data.
    """
    schema_output_file.parent.mkdir(parents=True, exist_ok=True)
    schema_output_file.write_text(json.dumps(schema_data, indent=2), encoding="utf-8")


async def write_captured_schema(
    api_connection: ApiConnectionGraphql,
    schema_output_file: Path,
) -> None:
    """Capture and write the authenticated Carrier GraphQL schema.

    Args:
        api_connection: Authenticated Carrier API connection.
        schema_output_file: File that should receive the schema JSON.

    Raises:
        RuntimeError: If Carrier returns no introspection schema data.
    """
    await api_connection.check_auth_expiration()
    transport = AIOHTTPTransport(
        url="https://dataservice.infinity.iot.carrier.com/graphql",
        headers={"Authorization": f"{api_connection.token_type} {api_connection.access_token}"},
        ssl=True,
    )
    async with Client(
        transport=transport,
        fetch_schema_from_transport=False,
        execute_timeout=GRAPHQL_EXECUTE_TIMEOUT_SECONDS,
    ) as session:
        introspection_query = get_introspection_query(**session.client.introspection_args)
        schema_data = await session.execute(gql(introspection_query))
    if not schema_data:
        raise RuntimeError("Carrier GraphQL introspection returned no schema data")
    write_schema_output(schema_output_file, schema_data)


@contextmanager
def capture_output(output_file: Path | None) -> Iterator[None]:
    """Optionally tee smoke-test output to a transcript file.

    Args:
        output_file: Transcript file path, if capture is requested.

    Yields:
        Control while output capture is active.
    """
    if output_file is None:
        yield
        return
    with SmokeTestTranscript(output_file):
        yield


async def read_input(prompt: str) -> str:
    """Read terminal input without blocking the event loop.

    Args:
        prompt: Prompt to display to the user.

    Returns:
        The entered input text.
    """
    return await asyncio.to_thread(input, prompt)


async def read_password() -> str:
    """Read a password without blocking the event loop.

    Returns:
        The password entered by the user.
    """
    return await asyncio.to_thread(getpass)


def current_timestamp() -> str:
    """Return the current local date and time for console output.

    Returns:
        Local timestamp formatted for human-readable smoke-test logs.
    """
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


async def wait_for_cancelled_task(task: Task[None] | None) -> None:
    """Cancel and await a background task if it is still running.

    Args:
        task: Background task to cancel and drain.
    """
    if task is None:
        return
    if not task.done():
        task.cancel()
    with suppress(CancelledError):
        await task


async def shutdown_websocket_listener(api_connection: ApiConnectionGraphql) -> None:
    """Stop websocket background tasks before closing the aiohttp session.

    Args:
        api_connection: API connection whose websocket listener should be
            stopped before the underlying HTTP session is closed.
    """
    api_websocket = api_connection.api_websocket
    if api_websocket is None:
        return

    api_websocket.running = False
    if api_websocket.websocket is not None and not api_websocket.websocket.closed:
        await api_websocket.websocket.close()
    await wait_for_cancelled_task(api_websocket.task_listener)
    await wait_for_cancelled_task(api_websocket.task_heartbeat)
    api_websocket.task_listener = None
    api_websocket.task_heartbeat = None


async def send_sample_manual_activity_update(
    api_connection: ApiConnectionGraphql,
    systems: list[Any],
) -> bool:
    """Send the sample manual activity update used by the live smoke test.

    Args:
        api_connection: API connection used to send the mutation.
        systems: Loaded Carrier system objects.

    Returns:
        True when Carrier accepts the mutation, otherwise False for captured
        Carrier gateway failures.

    Raises:
        RuntimeError: If no system or zone is available to update.
    """
    if not systems:
        raise RuntimeError("No systems available")
    zones = systems[0].config.zones
    if not zones:
        raise RuntimeError("No config zones available")

    try:
        await api_connection.set_config_manual_activity(
            system_serial=systems[0].profile.serial,
            zone_id=zones[0].api_id,
            heat_set_point="73",
            cool_set_point="80",
            fan_mode=FanModes.LOW,
        )
    except TransportServerError as err:
        if err.code != 504:
            raise
        print(f"Manual activity update failed: {err}")
        return False
    return True


async def maybe_send_sample_manual_activity_update(
    api_connection: ApiConnectionGraphql,
    systems: list[Any],
    *,
    read_only: bool,
) -> bool:
    """Send the sample mutation unless the smoke test is in read-only mode.

    Args:
        api_connection: API connection used to send the mutation.
        systems: Loaded Carrier system objects.
        read_only: Whether to skip mutation calls.

    Returns:
        True when the mutation is sent successfully, otherwise False.
    """
    if read_only:
        print("Read-only mode enabled; skipping sample manual activity update.")
        return False
    return await send_sample_manual_activity_update(api_connection, systems)


async def main(options: SmokeTestOptions) -> None:
    """Log in, load systems, start websocket updates, and send one manual update.

    Args:
        options: Parsed smoke-test command-line options.
    """
    print(INTRO_TEXT)
    print()
    credentials = load_credentials(options)
    if credentials is None:
        username = await read_input("Carrier or Bryant account email address: ")
        password = await read_password()
    else:
        username = credentials.username
        password = credentials.password
        print(f"Using Carrier credentials from {credentials.description}.")
    api_connection = None
    completed = False
    print()
    print(f"Starting Smoke Test at {current_timestamp()}")
    print("--------------------------------------------------------------------------")
    print()
    try:
        api_connection = ApiConnectionGraphql(username=username, password=password)
        if options.schema_output_file is not None:
            await write_captured_schema(api_connection, options.schema_output_file)
            print(f"Wrote captured GraphQL schema to {options.schema_output_file}")
        systems = await api_connection.load_data()
        print([system.as_dict() for system in systems])

        async def listener() -> None:
            """Register websocket callbacks and start the listener task."""

            async def output(message: str) -> None:
                """Print current in-memory systems after a websocket message.

                Args:
                    message: Raw websocket message text. The callback does not
                        inspect the payload because the data updater callback has
                        already merged it into the shared system objects.
                """
                print([system.as_dict() for system in systems])

            ws_data_updater = WebsocketDataUpdater(systems=systems)
            api_websocket = api_connection.api_websocket
            if api_websocket is None:
                raise RuntimeError("api_websocket was not initialized")
            api_websocket.callback_add(ws_data_updater.message_handler)
            api_websocket.callback_add(output)
            await api_websocket.create_task_listener()

        await listener()
        logger.debug("started websocket listener task")

        await maybe_send_sample_manual_activity_update(
            api_connection,
            systems,
            read_only=options.read_only,
        )
        print()
        print("--------------------------------------------------------------------------")
        print("The script will now wait 5 minutes, so websocket messages can be observed")
        print("--------------------------------------------------------------------------")
        print()
        await sleep(SMOKE_TEST_WAIT_SECONDS)
        completed = True
    finally:
        if api_connection is not None:
            await shutdown_websocket_listener(api_connection)
            await api_connection.cleanup()
        if completed:
            print()
            print("--------------------------------------------------------------------------")
            print(f"Smoke test complete at {current_timestamp()}")


if __name__ == "__main__":
    smoke_test_options = parse_args()
    with capture_output(smoke_test_options.output_file):
        asyncio.run(main(smoke_test_options))
