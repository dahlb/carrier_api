from logging import getLogger

from dateutil.parser import isoparse
import datetime

from .util import safely_get_json_value

_LOGGER = getLogger(__name__)


class EnergyMeasurement:
    def __init__(self, energy_measurement_json: dict):
        self.api_id = safely_get_json_value(energy_measurement_json, "$.id")
        self.cooling: int = safely_get_json_value(energy_measurement_json, "cooling", int)
        self.hp_heat: int = safely_get_json_value(energy_measurement_json, "hpheat", int)
        self.fan: int = safely_get_json_value(energy_measurement_json, "fan", int)
        self.electric_heat: int = safely_get_json_value(energy_measurement_json, "eheat", int)
        self.reheat: int = safely_get_json_value(energy_measurement_json, "reheat", int)
        self.fan_gas: int = safely_get_json_value(energy_measurement_json, "fangas", int)
        self.gas: int = safely_get_json_value(energy_measurement_json, "gas", int)
        self.loop_pump: int = safely_get_json_value(energy_measurement_json, "looppump", int)

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
    seer: int = None
    hspf: float = None
    cooling: bool = None
    hp_heat: bool = None
    fan: bool = None
    electric_heat: bool = None
    reheat: bool = None
    fan_gas: bool = None
    gas: bool = None
    loop_pump: bool = None
    time_stamp: datetime = None
    periods: [EnergyMeasurement] = None
    raw_energy_json: dict = None

    def __init__(
        self,
        system,
    ):
        self.system = system
        self.refresh()

    def refresh(self):
        self.raw_energy_json = self.system.api_connection.get_energy(
            system_serial=self.system.serial
        )
        _LOGGER.debug(f"raw_energy_json:{self.raw_energy_json}")
        self.seer: int = safely_get_json_value(self.raw_energy_json, "seer", int)
        self.hspf: float = safely_get_json_value(self.raw_energy_json, "hspf", float)
        self.cooling: bool = safely_get_json_value(self.raw_energy_json, "cooling.$.display") == "on" and safely_get_json_value(self.raw_energy_json, "cooling.$.enabled") == "on"
        self.hp_heat: bool = safely_get_json_value(self.raw_energy_json, "hpheat.$.display") == "on" and safely_get_json_value(self.raw_energy_json, "hpheat.$.enabled") == "on"
        self.fan: bool = safely_get_json_value(self.raw_energy_json, "fan.$.display") == "on" and safely_get_json_value(self.raw_energy_json, "fan.$.enabled") == "on"
        self.electric_heat: bool = safely_get_json_value(self.raw_energy_json, "eheat.$.display") == "on" and safely_get_json_value(self.raw_energy_json, "eheat.$.enabled") == "on"
        self.reheat: bool = safely_get_json_value(self.raw_energy_json, "reheat.$.display") == "on" and safely_get_json_value(self.raw_energy_json, "reheat.$.enabled") == "on"
        self.fan_gas: bool = safely_get_json_value(self.raw_energy_json, "fangas.$.display") == "on" and safely_get_json_value(self.raw_energy_json, "fangas.$.enabled") == "on"
        self.gas: bool = safely_get_json_value(self.raw_energy_json, "gas.$.display") == "on" and safely_get_json_value(self.raw_energy_json, "gas.$.enabled") == "on"
        self.loop_pump: bool = safely_get_json_value(self.raw_energy_json, "looppump.$.display") == "on" and safely_get_json_value(self.raw_energy_json, "looppump.$.enabled") == "on"
        self.time_stamp = isoparse(safely_get_json_value(self.raw_energy_json, "timestamp"))
        self.periods = []
        for period_json in self.raw_energy_json["usage"]["period"]:
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
