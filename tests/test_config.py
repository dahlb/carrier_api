"""Tests for configuration schedule behavior."""

from datetime import datetime, tzinfo
from typing import Self

import pytest

from carrier_api import config as config_module
from carrier_api.config import ConfigZone
from carrier_api.const import ActivityTypes


class FixedDateTime(datetime):
    """Fixed datetime provider for schedule boundary tests."""

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> Self:
        """Return a stable local schedule time.

        Args:
            tz: Optional timezone requested by production code.

        Returns:
            A fixed datetime whose local wall-clock time is 08:30 after
            production converts it through ``astimezone()``.
        """
        timestamp = datetime(2026, 5, 26, 8, 30).astimezone().timestamp()
        return cls.fromtimestamp(timestamp, tz)


def build_zone_with_periods(periods: list[dict[str, str]]) -> ConfigZone:
    """Build a config zone with the same periods on every schedule day.

    Args:
        periods: Schedule periods to repeat across all seven days.

    Returns:
        A config zone using the supplied schedule periods.
    """
    return ConfigZone(
        zone_json={
            "id": "1",
            "name": "Zone 1",
            "holdActivity": "home",
            "hold": "off",
            "otmr": None,
            "occEnabled": "off",
            "activities": [
                {
                    "type": "home",
                    "id": "1",
                    "fan": "low",
                    "htsp": "68",
                    "clsp": "72",
                }
            ],
            "program": {"day": [{"period": periods} for _ in range(7)]},
        },
        vacation_json={
            "type": "vacation",
            "fan": None,
            "htsp": None,
            "clsp": None,
        },
    )


def test_current_scheduled_activity_returns_none_when_no_periods_are_active() -> None:
    """Return no scheduled activity when today and yesterday have no active periods."""
    zone = build_zone_with_periods(
        [
            {
                "enabled": "off",
                "time": "00:00",
                "activity": "home",
            }
        ]
    )

    assert zone.current_scheduled_activity() is None


def test_current_scheduled_activity_includes_period_start_minute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use the starting activity when the current time equals a period time."""
    monkeypatch.setattr(config_module, "datetime", FixedDateTime)
    zone = build_zone_with_periods(
        [
            {
                "enabled": "on",
                "time": "08:30",
                "activity": "home",
            }
        ]
    )

    current_scheduled_activity = zone.current_scheduled_activity()

    assert current_scheduled_activity is not None
    assert current_scheduled_activity.type == ActivityTypes.HOME
