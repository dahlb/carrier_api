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
    seer: float = None
    hspf: float = None
    cooling: bool = None
    hp_heat: bool = None
    fan: bool = None
    electric_heat: bool = None
    reheat: bool = None
    fan_gas: bool = None
    gas: bool = None
    loop_pump: bool = None
    periods: [EnergyMeasurement] = None
    raw: dict = None

    def __init__(
        self,
        raw,
    ):
        self.raw = raw
        _LOGGER.debug(f"raw_energy:{self.raw}")
        self.seer: int = safely_get_json_value(self.raw, "energyConfig.seer", float)
        self.hspf: float = safely_get_json_value(self.raw, "energyConfig.hspf", float)
        self.cooling: bool = safely_get_json_value(self.raw, "energyConfig.cooling.display") == "on" and safely_get_json_value(self.raw, "energyConfig.cooling.enabled") == "on"
        self.hp_heat: bool = safely_get_json_value(self.raw, "energyConfig.hpheat.display") == "on" and safely_get_json_value(self.raw, "energyConfig.hpheat.enabled") == "on"
        self.fan: bool = safely_get_json_value(self.raw, "energyConfig.fan.display") == "on" and safely_get_json_value(self.raw, "energyConfig.fan.enabled") == "on"
        self.electric_heat: bool = safely_get_json_value(self.raw, "energyConfig.eheat.display") == "on" and safely_get_json_value(self.raw, "energyConfig.eheat.enabled") == "on"
        self.reheat: bool = safely_get_json_value(self.raw, "energyConfig.reheat.display") == "on" and safely_get_json_value(self.raw, "energyConfig.reheat.enabled") == "on"
        self.fan_gas: bool = safely_get_json_value(self.raw, "energyConfig.fangas.display") == "on" and safely_get_json_value(self.raw, "energyConfig.fangas.enabled") == "on"
        self.gas: bool = safely_get_json_value(self.raw, "energyConfig.gas.display") == "on" and safely_get_json_value(self.raw, "energyConfig.gas.enabled") == "on"
        self.loop_pump: bool = safely_get_json_value(self.raw, "energyConfig.looppump.display") == "on" and safely_get_json_value(self.raw, "energyConfig.looppump.enabled") == "on"
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
