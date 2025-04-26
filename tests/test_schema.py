"""Tests for WebsocketDataUpdater.

Here is one way to run it:

Then use pytest to drive the tests

    $ pytest tests
"""
from datetime import datetime, UTC, time
from importlib import resources
import json
from logging import getLogger
from unittest import IsolatedAsyncioTestCase
from pathlib import Path
import sys

path_root = Path(__file__).parents[1]
sys.path.append(str(path_root))

from src.carrier_api import InfinityEnergy, Profile, Status, Config, ConfigZone, TemperatureUnits, ActivityTypes, FanModes, SystemModes # noqa: E402
from src.carrier_api.schema.profile import ProfileSchema # noqa: E402
from src.carrier_api.schema.energy import InfinityEnergySchema # noqa: E402
from src.carrier_api.schema.status import StatusSchema, StatusZoneSchema # noqa: E402

_LOGGER = getLogger(__name__)


class SchemaTestBase(IsolatedAsyncioTestCase):
    def setUp(self):
        self.system_response = json.loads(open(resources.files().joinpath('graphql/systems.json')).read())
        self.energy_response = json.loads(open(resources.files().joinpath('graphql/energy.json')).read())

class InfinityEnergyTest(SchemaTestBase):
    def setUp(self):
        super().setUp()
        self.schema = InfinityEnergySchema()
        self.instance: InfinityEnergy = self.schema.load(self.energy_response["infinityEnergy"])

    async def test_energy_raw(self):
        assert self.schema.load(self.schema.dump(self.instance)) == self.instance

    async def test_energy_fan_show(self):
        assert self.instance.config.fan.show() == False

    async def test_energy_gas_show(self):
        assert self.instance.config.gas.show() == True

    async def test_energy_seer(self):
        assert self.instance.config.seer == 15

    async def test_energy_hspf(self):
        assert self.instance.config.hspf == 8.80078125

    async def test_energy_current_year_measurements(self):
        assert self.instance.current_year_measurements().api_id == "year1"
        assert self.instance.current_year_measurements().gas == 25905

class ProfileTest(SchemaTestBase):
    def setUp(self):
        super().setUp()
        self.schema = ProfileSchema()
        self.instance: Profile = self.schema.load(self.system_response["infinitySystems"][0]["profile"])

    async def test_profile_raw(self):
        assert self.schema.load(self.schema.dump(self.instance)) == self.instance

    async def test_profile_attributes(self):
        assert self.instance.name == "HVAC"
        assert self.instance.serial == "SERIALXXX"
        assert self.instance.model == "SYSTXCCWIC01-B"
        assert self.instance.brand == "Carrier"
        assert self.instance.firmware == "CESR131626-04.70"
        assert self.instance.indoor_model == "59TN6A100V211122"
        assert self.instance.indoor_serial == "SERIALXXXX"
        assert self.instance.indoor_unit_type == "furnace"
        assert self.instance.indoor_unit_source == "gas"
        assert self.instance.outdoor_model == "24ANB736A00310"
        assert self.instance.outdoor_serial == "SERIALXXXXX"
        assert self.instance.outdoor_unit_type == "ac2stg"

class StatusTest(SchemaTestBase):
    def setUp(self):
        super().setUp()
        self.schema = StatusSchema()
        self.instance: Status = self.schema.load(self.system_response["infinitySystems"][0]["status"])

    async def test_status_raw(self):
        _LOGGER.error(self.instance)
        dump = self.schema.dump(self.instance)
        _LOGGER.error(dump)
#        assert dump == self.system_response["infinitySystems"][0]["status"]
        assert self.schema.load(dump) == self.instance

    async def test_status_attributes(self):
        assert self.instance.outdoor_temperature == 30.0
        assert self.instance.mode == "heat"
        assert self.instance.temperature_unit == TemperatureUnits.FAHRENHEIT
        assert self.instance.filter_used == 0
        assert self.instance.humidity_level == 19
        assert self.instance.humidifier_on == True
        assert self.instance.uv_lamp_level == 100
        assert self.instance.is_disconnected == False
        assert self.instance.time_stamp == datetime(2025, 3, 3, 13, 42, 34, 328000, tzinfo=UTC)
        assert len(self.instance.zones) == 1
        assert self.instance.zones[0].api_id == "1"
        assert self.instance.zones[0].current_activity == ActivityTypes.WAKE
        assert self.instance.zones[0].temperature == 74.0
        assert self.instance.zones[0].humidity == 32
        assert self.instance.zones[0].occupancy == False
        assert self.instance.zones[0].fan == FanModes.MED
        assert self.instance.zones[0].hold == False
        assert self.instance.zones[0].hold_until is None
        assert self.instance.zones[0].heat_set_point == 74.0
        assert self.instance.zones[0].cool_set_point == 78.0
        assert self.instance.zones[0].conditioning == "active_heat"
        assert self.instance.zones[0].zone_conditioning_const == SystemModes.HEAT


class ConfigTest(SchemaTestBase):
    def setUp(self):
        super().setUp()
        self.schema = Config
        ConfigZone.from_dict(self.system_response["infinitySystems"][0]["config"]["zones"][0])
        self.instance: Config = self.schema.from_dict(self.system_response["infinitySystems"][0]["config"])

    async def test_raw(self):
        assert self.schema.from_dict(self.instance.to_dict()) == self.instance
#        assert self.system_response["infinitySystems"][0]["status"] == self.instance.to_dict() # used for debug

    async def test_attributes(self):
        assert self.instance.temperature_unit == TemperatureUnits.FAHRENHEIT
        assert self.instance.mode == "heat"
        assert self.instance.heat_source == "system"
        assert self.instance.etag == "14b685b54f679cedf5e34313"
        assert self.instance.fuel_type == "gas"
        assert self.instance.gas_unit == "therm"
        assert self.instance.uv_enabled is False
        assert self.instance.humidifier_enabled is True
        assert self.instance.vacation_cool_set_point == 80
        assert self.instance.vacation_heat_set_point == 60.0
        assert self.instance.vacation_fan == FanModes.OFF
        assert self.instance.zones[0].api_id == "1"
        assert self.instance.zones[0].name == "ZONE 1"
        assert self.instance.zones[0].hold_activity is None
        assert self.instance.zones[0].hold is False
        assert self.instance.zones[0].hold_until is None
        assert self.instance.zones[0].occupancy_enabled is False
        assert self.instance.zones[0].activities[0].api_id == "1"
        assert self.instance.zones[0].activities[0].type == ActivityTypes.AWAY
        assert self.instance.zones[0].activities[0].fan == FanModes.OFF
        assert self.instance.zones[0].activities[0].cool_set_point == 85
        assert self.instance.zones[0].activities[0].heat_set_point == 68
        assert self.instance.zones[0].program.api_id == "1"
        assert self.instance.zones[0].program.days[0].api_id == "0"
        assert self.instance.zones[0].program.days[0].zone_id == self.instance.zones[0].api_id
        assert self.instance.zones[0].program.days[0].periods[0].api_id == "2"
        assert self.instance.zones[0].program.days[0].periods[0].zone_id == self.instance.zones[0].api_id
        assert self.instance.zones[0].program.days[0].periods[0].day_id == "0"
        assert self.instance.zones[0].program.days[0].periods[0].time == time(7, 45)
        assert self.instance.zones[0].program.days[0].periods[0].activity == ActivityTypes.WAKE

    async def test_find_activity(self):
        wake = self.instance.zones[0].find_activity(ActivityTypes.WAKE)
        assert wake.type == ActivityTypes.WAKE
        assert wake.api_id == "1"
        assert wake.heat_set_point == 75.0
        assert wake.cool_set_point == 77.0
        assert wake.fan == FanModes.MED
        sleep = self.instance.zones[0].find_activity(ActivityTypes.SLEEP)
        assert sleep.type == ActivityTypes.SLEEP
        assert sleep.api_id == "1"
        assert sleep.heat_set_point == 74.0
        assert sleep.cool_set_point == 78.0
        assert sleep.fan == FanModes.LOW