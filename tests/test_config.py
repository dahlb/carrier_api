"""Tests for configuration schedule behavior."""

from carrier_api.config import ConfigZone


def test_current_activity_returns_none_when_no_periods_are_active() -> None:
    """Return no current activity when today and yesterday have no active periods."""
    zone = ConfigZone(
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
            "program": {
                "day": [
                    {
                        "period": [
                            {
                                "enabled": "off",
                                "time": "00:00",
                                "activity": "home",
                            }
                        ]
                    }
                    for _ in range(7)
                ]
            },
        },
        vacation_json={
            "type": "vacation",
            "fan": None,
            "htsp": None,
            "clsp": None,
        },
    )

    assert zone.current_activity() is None
