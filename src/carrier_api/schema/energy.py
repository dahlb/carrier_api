"""Schema for energy."""

from dataclasses import dataclass
from typing import List

from marshmallow import Schema, EXCLUDE, fields, post_load


@dataclass(kw_only=True)
class EnergyMeasurement:
    api_id: str
    cooling: int
    hp_heat: int
    fan: int
    electric_heat: int
    reheat: int
    fan_gas: int
    gas: int
    loop_pump: int


class EnergyMeasurementSchema(Schema):
    class Meta:
        unknown = EXCLUDE
    api_id = fields.String(data_key="energyPeriodType")
    cooling = fields.Integer(data_key="coolingKwh")
    hp_heat = fields.Integer(data_key="hPHeatKwh")
    fan = fields.Integer(data_key="fanKwh")
    electric_heat = fields.Integer(data_key="eHeatKwh")
    reheat = fields.Integer(data_key="reheatKwh")
    fan_gas = fields.Integer(data_key="fanGasKwh")
    gas = fields.Integer(data_key="gasKwh")
    loop_pump = fields.Integer(data_key="loopPumpKwh")

    @post_load
    def make(self, data, **kwargs):
        return EnergyMeasurement(**data)

@dataclass(kw_only=True)
class EnergyConfigOptions:
    display: bool
    enabled: bool

    def show(self) -> bool:
        return self.display and self.enabled


class EnergyConfigOptionsSchema(Schema):
    class Meta:
        unknown = EXCLUDE
    display = fields.Boolean()
    enabled = fields.Boolean()

    @post_load
    def make(self, data, **kwargs):
        return EnergyConfigOptions(**data)


@dataclass(kw_only=True)
class EnergyConfig:
    seer: int
    hspf: float
    cooling: EnergyConfigOptions
    hp_heat: EnergyConfigOptions
    fan: EnergyConfigOptions
    electric_heat: EnergyConfigOptions
    reheat: EnergyConfigOptions
    fan_gas: EnergyConfigOptions
    gas: EnergyConfigOptions
    loop_pump: EnergyConfigOptions


class EnergyConfigSchema(Schema):
    class Meta:
        unknown = EXCLUDE
    seer = fields.Integer()
    hspf = fields.Float()
    cooling = fields.Nested(EnergyConfigOptionsSchema)
    hp_heat = fields.Nested(EnergyConfigOptionsSchema, data_key="hpheat")
    fan = fields.Nested(EnergyConfigOptionsSchema)
    electric_heat = fields.Nested(EnergyConfigOptionsSchema, data_key="eheat")
    reheat = fields.Nested(EnergyConfigOptionsSchema)
    fan_gas = fields.Nested(EnergyConfigOptionsSchema, data_key="fangas")
    gas = fields.Nested(EnergyConfigOptionsSchema)
    loop_pump = fields.Nested(EnergyConfigOptionsSchema, data_key="looppump")

    @post_load
    def make(self, data, **kwargs):
        return EnergyConfig(**data)


@dataclass(kw_only=True)
class InfinityEnergy:
    config: EnergyConfig
    periods: List[EnergyMeasurement]

    def current_year_measurements(self):
        for period in self.periods:
            if period.api_id == "year1":
                return period

class InfinityEnergySchema(Schema):
    class Meta:
        unknown = EXCLUDE
    config = fields.Nested(EnergyConfigSchema, data_key="energyConfig")
    periods = fields.List(fields.Nested(EnergyMeasurementSchema), data_key="energyPeriods")

    @post_load
    def make(self, data, **kwargs):
        return InfinityEnergy(**data)
