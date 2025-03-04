from logging import getLogger

from .util import safely_get_json_value

_LOGGER = getLogger(__name__)


class EnergyMeasurement:
    def __init__(self, energy_measurement_json: dict):
        self.api_id = safely_get_json_value(energy_measurement_json, "energyPeriodType")
        self.cooling: int = safely_get_json_value(energy_measurement_json, "coolingKwh", int)
        self.hp_heat: int = safely_get_json_value(energy_measurement_json, "hPHeatKwh", int)
        self.fan: int = safely_get_json_value(energy_measurement_json, "fanKwh", int)
        self.electric_heat: int = safely_get_json_value(energy_measurement_json, "eHeatKwh", int)
        self.reheat: int = safely_get_json_value(energy_measurement_json, "reheatKwh", int)
        self.fan_gas: int = safely_get_json_value(energy_measurement_json, "fanGasKwh", int)
        self.gas: int = safely_get_json_value(energy_measurement_json, "gasKwh", int)
        self.loop_pump: int = safely_get_json_value(energy_measurement_json, "loopPumpKwh", int)

    def __repr__(self):
        return {
            "id": self.api_id,
            "cooling": self.cooling,
            "hp_heat": self.hp_heat,
            "fan": self.fan,
            "electric_heat": self.electric_heat,
            "reheat": self.reheat,
            "fan_gas": self.fan_gas,
            "gas": self.gas,
            "loop_pump": self.loop_pump,
        }

    def __str__(self):
        return str(self.__repr__())


class Energy:
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
    periods: list[EnergyMeasurement] | None = None

    def __init__(
        self,
        raw: dict,
    ):
        self.raw = raw
        self.seer: int = safely_get_json_value(self.raw, "energyConfig.seer", float)
        self.hspf: float = safely_get_json_value(self.raw, "energyConfig.hspf", float)
        self.cooling: bool = safely_get_json_value(self.raw, "energyConfig.cooling.display", bool) and safely_get_json_value(self.raw, "energyConfig.cooling.enabled", bool)
        self.hp_heat: bool = safely_get_json_value(self.raw, "energyConfig.hpheat.display", bool) and safely_get_json_value(self.raw, "energyConfig.hpheat.enabled", bool)
        self.fan: bool = safely_get_json_value(self.raw, "energyConfig.fan.display", bool) and safely_get_json_value(self.raw, "energyConfig.fan.enabled", bool)
        self.electric_heat: bool = safely_get_json_value(self.raw, "energyConfig.eheat.display", bool) and safely_get_json_value(self.raw, "energyConfig.eheat.enabled", bool)
        self.reheat: bool = safely_get_json_value(self.raw, "energyConfig.reheat.display", bool) and safely_get_json_value(self.raw, "energyConfig.reheat.enabled", bool)
        self.fan_gas: bool = safely_get_json_value(self.raw, "energyConfig.fangas.display", bool) and safely_get_json_value(self.raw, "energyConfig.fangas.enabled", bool)
        self.gas: bool = safely_get_json_value(self.raw, "energyConfig.gas.display", bool) and safely_get_json_value(self.raw, "energyConfig.gas.enabled", bool)
        self.loop_pump: bool = safely_get_json_value(self.raw, "energyConfig.looppump.display", bool) and safely_get_json_value(self.raw, "energyConfig.looppump.enabled", bool)
        self.periods = []
        for period_json in self.raw["energyPeriods"]:
            self.periods.append(EnergyMeasurement(period_json))

    def current_year_measurements(self):
        for period in self.periods:
            if period.api_id == "year1":
                return period

    def __repr__(self):
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
            "periods": [periods.__repr__() for periods in self.periods],
        }

    def __str__(self):
        return str(self.__repr__())
