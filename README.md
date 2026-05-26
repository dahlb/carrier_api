[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![Coverage][coverage-shield]][coverage]
[![License][license-shield]](LICENSE)

![Project Maintenance][maintenance-shield]
[![BuyMeCoffee][buymecoffeebadge]][buymecoffee]

[![PyPI][pypi-logo]][pypi]

# carrier_api

Async Python client for Carrier Infinity and Bryant Evolution HVAC systems.

This package wraps the Carrier Infinity GraphQL API, exposes typed model objects for system profile, status, configuration, and energy data, and includes helper methods for common thermostat updates. It is intended for integrations and local automation code that need a lightweight API client rather than a full
application.

The client is unofficial and depends on Carrier's private web and mobile API behavior. Carrier can change that API without notice.

## Requirements

- Python 3.14 or newer
- A Carrier or Bryant account that works in the official app
- Network access to Carrier's cloud API

## Installation

Install the published package in a virtual environment:

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install carrier_api
```

## Live Smoke Test

The live smoke test connects to a real Carrier account, prints loaded system state, starts websocket listeners, and sends one sample manual activity update to the first available zone.

```bash
scripts/live_smoke_test
```

Use it only when you want to exercise the live Carrier API. It can change thermostat settings.

To run non-interactively, put credentials in a local `env` file and pass it with `--credentials-file`. Supported keys are `CARRIER_USERNAME`/`CARRIER_PASSWORD`.

```bash
scripts/live_smoke_test --credentials-file scripts/carrier_api.env --output-file /private/tmp/carrier_api.txt --schema-output-file /private/tmp/carrier_api_schema.json --read-only
```

Use `--output-file` when you want a full transcript for later API debugging or fixture updates. Use `--schema-output-file` to also capture the authenticated GraphQL introspection schema without temporarily editing the client. Use `--read-only` to skip the sample thermostat mutation while still loading systems, capturing schema, and listening for websocket messages.

## Basic Usage

```python
import asyncio

from carrier_api import ApiConnectionGraphql


async def main() -> None:
    api = ApiConnectionGraphql(
        username="your-account@example.com",
        password="your-password",
    )
    try:
        systems = await api.load_data()
        for system in systems:
            print(system.profile.name)
            print(system.status.mode)
            print(system.as_dict())
    finally:
        await api.cleanup()


asyncio.run(main())
```

`load_data()` authenticates when needed and returns a list of `System` objects. Each `System` includes:

- `profile`: system identity and location metadata
- `status`: current mode, temperature, humidity, zone, and equipment state
- `config`: configured zones, activities, schedules, and holds
- `energy`: reported energy usage data

Model objects provide `as_dict()` for structured serialization. Their string and repr forms are intended for readable debugging output.

`System` also exposes HVAC capability helpers:

- `supports_heat()`
- `supports_cool()`
- `supports_fan()`
- `supported_hvac_capabilities()`

For zone-level profile resolution, call `ConfigZone.current_status_activity(status_zone)` with the matching `StatusZone`. This uses Carrier's reported current activity when the zone is not held, and the configured hold activity when a hold is active.

`System.as_dict()` includes `supported_hvac_capabilities` and passes status-zone context into config serialization so each zone dictionary includes `current_status_activity`.

## Updating Thermostat Settings

Mutation helpers send Carrier configuration updates and then request websocket reconciliation when a websocket manager is available.

```python
import asyncio

from carrier_api import ActivityTypes, ApiConnectionGraphql, FanModes, SystemModes


async def main() -> None:
    api = ApiConnectionGraphql(
        username="your-account@example.com",
        password="your-password",
    )
    try:
        systems = await api.load_data()
        system = systems[0]
        zone = system.config.zones[0]

        await api.set_config_mode(system.profile.serial, SystemModes.AUTO)
        await api.update_fan(
            system_serial=system.profile.serial,
            zone_id=zone.api_id,
            activity_type=ActivityTypes.HOME,
            fan_mode=FanModes.LOW,
        )
        await api.set_config_manual_activity(
            system_serial=system.profile.serial,
            zone_id=zone.api_id,
            heat_set_point="68",
            cool_set_point="74",
            fan_mode=FanModes.LOW,
        )
    finally:
        await api.cleanup()


asyncio.run(main())
```

Available update helpers include:

- `set_config_mode(...)`
- `set_config_heat_humidity(...)`
- `set_heat_source(...)`
- `set_humidifier(...)`
- `update_fan(...)`
- `set_config_hold(...)`
- `resume_schedule(...)`
- `set_config_manual_activity(...)`

These methods can change real HVAC settings. Validate the selected system, zone, mode, and set points before calling them from automation.

## Realtime Updates

`ApiWebsocket` manages Carrier realtime messages. `WebsocketDataUpdater` can merge incoming websocket messages into the `System` objects returned by `load_data()`.

```python
import asyncio

from carrier_api import ApiConnectionGraphql, WebsocketDataUpdater


async def main() -> None:
    api = ApiConnectionGraphql(
        username="your-account@example.com",
        password="your-password",
    )
    try:
        systems = await api.load_data()
        updater = WebsocketDataUpdater(systems)

        if api.api_websocket is None:
            raise RuntimeError("websocket manager was not initialized")

        api.api_websocket.callback_add(updater.message_handler)
        await api.api_websocket.create_task_listener()
    finally:
        await api.cleanup()


asyncio.run(main())
```

Callbacks receive the raw websocket message text. Register `WebsocketDataUpdater.message_handler` first when later callbacks need to read the updated in-memory system state.

## Development

Clone this repository and install the development environment:

```bash
git clone https://github.com/dahlb/carrier_api.git
cd carrier_api
scripts/setup
```

Use the repository scripts so commands run through the local `.venv`.

```bash
scripts/setup
scripts/test
scripts/lint
```

The underlying commands are:

```bash
./.venv/bin/pytest
./.venv/bin/prek run --all-files
./.venv/bin/mypy .
```

Add or update deterministic pytest coverage for behavior changes. Fixture data for GraphQL and websocket responses lives under `tests/graphql` and
`tests/messages`.

## Updating the Captured Schema

To refresh captured GraphQL schema data, run the live smoke test with `--schema-output-file`:

```bash
scripts/live_smoke_test --credentials-file scripts/carrier_api.env --schema-output-file /private/tmp/carrier_api_schema.json --read-only
```

The command authenticates with Carrier, runs the GraphQL introspection query, and writes the schema JSON to the path you provide. Add `--output-file /private/tmp/carrier_api.txt` when you also want the full live smoke-test transcript.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidance. Please open bugs and feature requests in the
[issue tracker](https://github.com/dahlb/carrier_api/issues).

[carrier_api]: https://github.com/dahlb/carrier_api
[commits-shield]: https://img.shields.io/github/commit-activity/y/dahlb/carrier_api.svg?style=for-the-badge
[commits]: https://github.com/dahlb/carrier_api/commits/main
[license-shield]: https://img.shields.io/github/license/dahlb/carrier_api.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-Bren%20Dahl%20%40dahlb-blue.svg?style=for-the-badge
[pypi-logo]: https://img.shields.io/badge/PyPI-3775A9?logo=pypi&logoColor=fff&style=for-the-badge
[pypi]: https://pypi.org/project/carrier_api/
[coverage]: https://htmlpreview.github.io/?https://github.com/dahlb/carrier_api/blob/python-coverage-comment-action-data/htmlcov/index.html
[coverage-shield]: https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fdahlb%2Fcarrier_api%2Fpython-coverage-comment-action-data%2Fendpoint.json&style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/dahlb/carrier_api.svg?style=for-the-badge
[releases]: https://github.com/dahlb/carrier_api/releases
[buymecoffee]: https://www.buymeacoffee.com/dahlb
[buymecoffeebadge]: https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=for-the-badge
