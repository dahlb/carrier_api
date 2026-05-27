"""Energy configuration and usage models for Carrier systems."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .util import safely_get_json_value

EnergyUsageValue = int | float | None


class EnergyPeriod(StrEnum):
    """Carrier energy reporting period identifiers."""

    DAY_1 = "day1"
    DAY_2 = "day2"
    MONTH_1 = "month1"
    MONTH_2 = "month2"
    YEAR_1 = "year1"
    YEAR_2 = "year2"


class EnergyUsageMetric(StrEnum):
    """Normalized Carrier energy usage metric names."""

    COOLING = "cooling"
    HP_HEAT = "hp_heat"
    FAN = "fan"
    ELECTRIC_HEAT = "electric_heat"
    REHEAT = "reheat"
    FAN_GAS = "fan_gas"
    GAS = "gas"
    LOOP_PUMP = "loop_pump"

    @property
    def label(self) -> str:
        """Return the human-readable label for the usage metric.

        Returns:
            Display label suitable for sensor names.
        """
        return _ENERGY_METRICS[self].label


@dataclass(frozen=True)
class _EnergyMetricSpec:
    """Carrier field mapping for a normalized energy usage metric."""

    label: str
    config_key: str
    period_key: str


_ENERGY_METRICS: dict[EnergyUsageMetric, _EnergyMetricSpec] = {
    EnergyUsageMetric.COOLING: _EnergyMetricSpec("Cooling", "cooling", "coolingKwh"),
    EnergyUsageMetric.HP_HEAT: _EnergyMetricSpec("Heat Pump Heat", "hpheat", "hPHeatKwh"),
    EnergyUsageMetric.FAN: _EnergyMetricSpec("Fan", "fan", "fanKwh"),
    EnergyUsageMetric.ELECTRIC_HEAT: _EnergyMetricSpec("Electric Heat", "eheat", "eHeatKwh"),
    EnergyUsageMetric.REHEAT: _EnergyMetricSpec("Reheat", "reheat", "reheatKwh"),
    EnergyUsageMetric.FAN_GAS: _EnergyMetricSpec("Fan Gas", "fangas", "fanGasKwh"),
    EnergyUsageMetric.GAS: _EnergyMetricSpec("Gas", "gas", "gasKwh"),
    EnergyUsageMetric.LOOP_PUMP: _EnergyMetricSpec("Loop Pump", "looppump", "loopPumpKwh"),
}

# Human-readable labels for sensor-facing Carrier energy usage metrics.
ENERGY_USAGE_METRIC_LABELS: dict[EnergyUsageMetric, str] = {
    metric: spec.label for metric, spec in _ENERGY_METRICS.items()
}


def _coerce_energy_usage_metric(metric: EnergyUsageMetric | str) -> EnergyUsageMetric | None:
    """Return the normalized usage metric, if the input names one.

    Args:
        metric: Normalized metric enum or string.

    Returns:
        Matching usage metric, or ``None`` when the input is not supported.
    """
    try:
        return EnergyUsageMetric(metric)
    except ValueError:
        return None


def _energy_config_metric_enabled(raw: dict[str, Any], metric: EnergyUsageMetric) -> bool:
    """Return whether Carrier marks a usage metric displayable and enabled.

    Args:
        raw: Raw ``infinityEnergy`` object returned by the Carrier GraphQL API.
        metric: Normalized usage metric to inspect.

    Returns:
        ``True`` when the matching Carrier energy config entry is displayable
        and enabled.
    """
    config_key = _ENERGY_METRICS[metric].config_key
    return (
        safely_get_json_value(raw, f"energyConfig.{config_key}.display", bool) is True
        and safely_get_json_value(raw, f"energyConfig.{config_key}.enabled", bool) is True
    )


def _energy_usage_value(raw: dict[str, Any], key: str) -> EnergyUsageValue:
    """Return an energy usage value while preserving whole numbers as ints.

    Args:
        raw: Raw energy period payload.
        key: Carrier energy period usage key.

    Returns:
        Integer usage for whole-number payloads, fractional usage as a float,
        or ``None`` when the payload value is absent or invalid.
    """
    value = safely_get_json_value(raw, key, float)
    if value is None:
        return None
    if value.is_integer():
        return int(value)
    return value


class EnergyMeasurement:
    """Energy usage totals for a single Carrier reporting period."""

    api_id: str | None = None
    cooling: EnergyUsageValue = None
    hp_heat: EnergyUsageValue = None
    fan: EnergyUsageValue = None
    electric_heat: EnergyUsageValue = None
    reheat: EnergyUsageValue = None
    fan_gas: EnergyUsageValue = None
    gas: EnergyUsageValue = None
    loop_pump: EnergyUsageValue = None

    def __init__(self, energy_measurement_json: dict[str, Any]) -> None:
        """Build an energy measurement from a Carrier energy period payload.

        Args:
            energy_measurement_json: Raw ``energyPeriods`` entry from the Carrier
                GraphQL API.
        """
        self.api_id = safely_get_json_value(energy_measurement_json, "energyPeriodType")
        for metric, spec in _ENERGY_METRICS.items():
            setattr(
                self,
                metric.value,
                _energy_usage_value(energy_measurement_json, spec.period_key),
            )

    def value_for_metric(self, metric: EnergyUsageMetric | str) -> EnergyUsageValue:
        """Return the energy total for a normalized metric name.

        Args:
            metric: Normalized metric enum or string such as ``gas`` or
                ``hp_heat``.

        Returns:
            The energy total for the metric, or ``None`` when the
            metric is not known.
        """
        energy_metric = _coerce_energy_usage_metric(metric)
        if energy_metric is None:
            return None
        return getattr(self, energy_metric.value, None)

    def as_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the usage measurement.

        Returns:
            A dictionary containing kWh usage by energy category.
        """
        return {"id": self.api_id} | {
            metric.value: self.value_for_metric(metric) for metric in _ENERGY_METRICS
        }

    def __repr__(self) -> str:
        """Return a developer-readable representation of the usage measurement.

        Returns:
            The usage measurement dictionary representation converted to a string.
        """
        return str(self.as_dict())

    def __str__(self) -> str:
        """Return a readable string representation of the usage measurement.

        Returns:
            The measurement representation converted to a string.
        """
        return str(self.as_dict())


class Energy:
    """Energy feature flags and usage periods for a Carrier system."""

    seer: float | None = None
    hspf: float | None = None
    cooling: bool | None = None
    hp_heat: bool | None = None
    fan: bool | None = None
    electric_heat: bool | None = None
    reheat: bool | None = None
    fan_gas: bool | None = None
    gas: bool | None = None
    loop_pump: bool | None = None
    periods: list[EnergyMeasurement]

    def __init__(
        self,
        raw: dict[str, Any],
    ) -> None:
        """Build energy state from a Carrier energy GraphQL response.

        Args:
            raw: Raw ``infinityEnergy`` object returned by the Carrier GraphQL API.
        """
        self.raw = raw
        self.seer: float = safely_get_json_value(self.raw, "energyConfig.seer", float)
        self.hspf: float = safely_get_json_value(self.raw, "energyConfig.hspf", float)
        for metric in _ENERGY_METRICS:
            setattr(self, metric.value, _energy_config_metric_enabled(self.raw, metric))
        self.periods = []
        for period_json in self.raw["energyPeriods"]:
            self.periods.append(EnergyMeasurement(period_json))

    def measurement_for_period(self, period_id: EnergyPeriod | str) -> EnergyMeasurement | None:
        """Find energy totals for a Carrier reporting period.

        Args:
            period_id: Carrier reporting period identifier such as ``year1``.

        Returns:
            The measurement whose Carrier period identifier matches, or
            ``None`` when the payload does not contain that period.
        """
        period_value = period_id.value if isinstance(period_id, EnergyPeriod) else period_id
        for period in self.periods or []:
            if period.api_id == period_value:
                return period
        return None

    def current_day_measurements(self) -> EnergyMeasurement | None:
        """Find the energy totals for the current-day reporting period.

        Returns:
            The measurement whose Carrier period identifier is ``day1``, or
            ``None`` when the payload does not contain that period.
        """
        return self.measurement_for_period(EnergyPeriod.DAY_1)

    def current_month_measurements(self) -> EnergyMeasurement | None:
        """Find the energy totals for the current-month reporting period.

        Returns:
            The measurement whose Carrier period identifier is ``month1``, or
            ``None`` when the payload does not contain that period.
        """
        return self.measurement_for_period(EnergyPeriod.MONTH_1)

    def current_year_measurements(self) -> EnergyMeasurement | None:
        """Find the energy totals for the current-year reporting period.

        Returns:
            The measurement whose Carrier period identifier is ``year1``, or
            ``None`` when the payload does not contain that period.
        """
        return self.measurement_for_period(EnergyPeriod.YEAR_1)

    def value_for_period_metric(
        self, period_id: EnergyPeriod | str, metric: EnergyUsageMetric | str
    ) -> EnergyUsageValue:
        """Return an energy total for a reporting period and usage metric.

        Args:
            period_id: Carrier reporting period identifier such as ``year1``.
            metric: Normalized metric enum or string such as ``gas`` or
                ``hp_heat``.

        Returns:
            The energy total for the period and metric, or ``None`` when either
            the period or metric is not known.
        """
        measurement = self.measurement_for_period(period_id)
        if measurement is None:
            return None
        return measurement.value_for_metric(metric)

    def is_usage_metric_enabled(self, metric: EnergyUsageMetric | str) -> bool:
        """Return whether an energy usage metric is enabled for this system.

        Args:
            metric: Normalized metric enum or string such as ``gas`` or
                ``cooling``.

        Returns:
            ``True`` when Carrier reports the metric as both displayable and
            enabled, otherwise ``False``.
        """
        energy_metric = _coerce_energy_usage_metric(metric)
        if energy_metric is None:
            return False
        return getattr(self, energy_metric.value, False) is True

    def enabled_usage_metrics(self) -> tuple[EnergyUsageMetric, ...]:
        """Return energy usage metrics enabled for this system.

        Returns:
            Enabled metrics in the canonical Carrier API iteration order.
        """
        return tuple(metric for metric in _ENERGY_METRICS if self.is_usage_metric_enabled(metric))

    def as_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of energy configuration and usage.

        Returns:
            A dictionary containing energy feature availability and period totals.
        """
        return {
            "seer": self.seer,
            "hspf": self.hspf,
            "cooling": self.cooling,
            "hp_heat": self.hp_heat,
            "fan": self.fan,
            "electric_heat": self.electric_heat,
            "reheat": self.reheat,
            "fan_gas": self.fan_gas,
            "gas": self.gas,
            "loop_pump": self.loop_pump,
            "periods": [periods.as_dict() for periods in self.periods or []],
        }

    def __repr__(self) -> str:
        """Return a developer-readable representation of the energy model.

        Returns:
            The energy dictionary representation converted to a string.
        """
        return str(self.as_dict())

    def __str__(self) -> str:
        """Return a readable string representation of the energy model.

        Returns:
            The energy representation converted to a string.
        """
        return str(self.as_dict())
