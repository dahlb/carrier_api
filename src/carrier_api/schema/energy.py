"""Schema for energy."""

from dataclasses import dataclass
from typing import Annotated

from mashumaro.types import Alias

from . import _BaseModel


@dataclass(kw_only=True)
class EnergyMeasurement(_BaseModel):
    api_id: Annotated[str, Alias("energyPeriodType")]
    cooling: Annotated[int, Alias("coolingKwh")]
    hp_heat: Annotated[int, Alias("hPHeatKwh")]
    fan: Annotated[int, Alias("fanKwh")]
    electric_heat: Annotated[int, Alias("eHeatKwh")]
    reheat: Annotated[int, Alias("reheatKwh")]
    fan_gas: Annotated[int, Alias("fanGasKwh")]
    gas: Annotated[int, Alias("gasKwh")]
    loop_pump: Annotated[int, Alias("loopPumpKwh")]


@dataclass(kw_only=True)
class EnergyConfigOptions(_BaseModel):
    display: bool
    enabled: bool

    def show(self) -> bool:
        return self.display and self.enabled


@dataclass(kw_only=True)
class EnergyConfig(_BaseModel):
    seer: int
    hspf: float
    cooling: EnergyConfigOptions
    hp_heat: Annotated[EnergyConfigOptions, Alias("hpheat")]
    fan: EnergyConfigOptions
    electric_heat: Annotated[EnergyConfigOptions, Alias("eheat")]
    reheat: EnergyConfigOptions
    fan_gas: Annotated[EnergyConfigOptions, Alias("fangas")]
    gas: EnergyConfigOptions
    loop_pump: Annotated[EnergyConfigOptions, Alias("looppump")]


@dataclass(kw_only=True)
class InfinityEnergy(_BaseModel):
    config: Annotated[EnergyConfig, Alias("energyConfig")]
    periods: Annotated[list[EnergyMeasurement], Alias("energyPeriods")]
    raw: dict | None = None

    def current_year_measurements(self):
        for period in self.periods:
            if period.api_id == "year1":
                return period
