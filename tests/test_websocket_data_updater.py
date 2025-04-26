"""Tests for WebsocketDataUpdater.

Here is one way to run it:

Then use pytest to drive the tests

    $ pytest tests
"""
from importlib import resources
import json
from unittest import IsolatedAsyncioTestCase
from pathlib import Path
import sys


path_root = Path(__file__).parents[1]
sys.path.append(str(path_root))

from src.carrier_api import Status, Config, InfinityEnergy, System, Systems, WebsocketDataUpdater, ActivityTypes, FanModes # noqa: E402


class WebsocketDataUpdaterTestBase(IsolatedAsyncioTestCase):
    def setUp(self):
        self.systems_response = json.loads(open(resources.files().joinpath('graphql/systems.json')).read())
        energy_response = json.loads(open(resources.files().joinpath('graphql/energy.json')).read())
        System.from_dict(self.systems_response["infinitySystems"][0])
        systems = Systems.from_dict(self.systems_response)
        for system in systems.systems:
            energy = InfinityEnergy.from_dict(energy_response["infinityEnergy"])
            system.energy = energy
        self.data_updater = WebsocketDataUpdater(systems)
        self.websocket_message_str = open(resources.files().joinpath(self.websocket_message_path)).read()
        self.carrier_system = systems.systems[0]

class MessageStatusIduCfm(WebsocketDataUpdaterTestBase):
    websocket_message_path = 'messages/status_idu_cfm.json'

    async def test_setup(self):
        reprocessed_status = Status.from_dict(Status.to_dict(self.carrier_system.status))
        assert self.carrier_system.status == reprocessed_status

    async def test_message_handler(self):
        assert self.carrier_system.status.indoor_unit.airflow_cfm == 1239
        await self.data_updater.message_handler(self.websocket_message_str)
        assert self.carrier_system.status.indoor_unit.airflow_cfm == 525
        reprocessed_status = Status.from_dict(Status.to_dict(self.carrier_system.status))
        assert reprocessed_status.indoor_unit.airflow_cfm == 525

class MessageStatusOduOpmode(WebsocketDataUpdaterTestBase):
    websocket_message_path = 'messages/status_odu_opmode.json'

    async def test_message_handler(self):
        assert self.carrier_system.status.mode == "heat"
        await self.data_updater.message_handler(self.websocket_message_str)
        assert self.carrier_system.status.mode == "heat"
        reprocessed_status = Status.from_dict(Status.to_dict(self.carrier_system.status))
        assert reprocessed_status.mode == "heat"

class MessageStatusZoneRh(WebsocketDataUpdaterTestBase):
    websocket_message_path = 'messages/status_zone_rh.json'

    async def test_message_handler(self):
        assert self.carrier_system.status.zones[0].humidity == 32
        await self.data_updater.message_handler(self.websocket_message_str)
        assert self.carrier_system.status.zones[0].humidity == 34
        reprocessed_status = Status.from_dict(Status.to_dict(self.carrier_system.status))
        assert reprocessed_status.zones[0].humidity == 34

class MessageStatusZoneConditioning(WebsocketDataUpdaterTestBase):
    websocket_message_path = 'messages/status_zone_conditioning.json'

    async def test_message_handler(self):
        assert self.carrier_system.status.zones[0].conditioning == "active_heat"
        await self.data_updater.message_handler(self.websocket_message_str)
        assert self.carrier_system.status.zones[0].conditioning == "idle"
        reprocessed_status = Status.from_dict(Status.to_dict(self.carrier_system.status))
        assert reprocessed_status.zones[0].conditioning == "idle"

class MessageStatusZoneActivity(WebsocketDataUpdaterTestBase):
    websocket_message_path = 'messages/status_zone_activity.json'

    async def test_message_handler(self):
        assert self.carrier_system.status.zones[0].current_activity == ActivityTypes.WAKE
        assert self.carrier_system.status.zones[0].heat_set_point == 74
        assert self.carrier_system.status.zones[0].cool_set_point == 78
        await self.data_updater.message_handler(self.websocket_message_str)
        assert self.carrier_system.status.zones[0].current_activity == ActivityTypes.HOME
        assert self.carrier_system.status.zones[0].heat_set_point == 77
        assert self.carrier_system.status.zones[0].cool_set_point == 79
        reprocessed_status = Status.from_dict(Status.to_dict(self.carrier_system.status))
        assert reprocessed_status.zones[0].current_activity == ActivityTypes.HOME
        assert reprocessed_status.zones[0].heat_set_point == 77
        assert reprocessed_status.zones[0].cool_set_point == 79


class MessageStatusZoneActivityOnly(WebsocketDataUpdaterTestBase):
    websocket_message_path = 'messages/status_zone_activity_only.json'

    async def test_message_handler(self):
        assert self.carrier_system.status.zones[0].current_activity == ActivityTypes.WAKE
        assert self.carrier_system.status.zones[0].fan == FanModes.MED
        await self.data_updater.message_handler(self.websocket_message_str)
        assert self.carrier_system.status.zones[0].current_activity == ActivityTypes.SLEEP
        assert self.carrier_system.status.zones[0].fan == FanModes.MED
        reprocessed_status = Status.from_dict(Status.to_dict(self.carrier_system.status))
        assert reprocessed_status.zones[0].current_activity == ActivityTypes.SLEEP
        assert self.carrier_system.status.zones[0].fan == FanModes.MED


class MessageStatusZoneHold(WebsocketDataUpdaterTestBase):
    websocket_message_path = 'messages/status_zone_hold.json'

    async def test_message_handler(self):
        assert self.carrier_system.status.zones[0].current_activity == ActivityTypes.WAKE
        await self.data_updater.message_handler(self.websocket_message_str)
        assert self.carrier_system.status.zones[0].current_activity == ActivityTypes.MANUAL
        reprocessed_status = Status.from_dict(Status.to_dict(self.carrier_system.status))
        assert reprocessed_status.zones[0].current_activity == ActivityTypes.MANUAL

class MessageStatusZoneHtsp(WebsocketDataUpdaterTestBase):
    websocket_message_path = 'messages/status_zone_htsp.json'

    async def test_message_handler(self):
        assert self.carrier_system.status.zones[0].heat_set_point == 74
        assert self.carrier_system.status.zones[0].cool_set_point == 78
        await self.data_updater.message_handler(self.websocket_message_str)
        assert self.carrier_system.status.zones[0].heat_set_point == 72
        assert self.carrier_system.status.zones[0].cool_set_point == 85
        reprocessed_status = Status.from_dict(Status.to_dict(self.carrier_system.status))
        assert reprocessed_status.zones[0].heat_set_point == 72
        assert reprocessed_status.zones[0].cool_set_point == 85

class MessageConfigZoneHold(WebsocketDataUpdaterTestBase):
    websocket_message_path = 'messages/config_zone_hold.json'

    async def test_message_handler(self):
        assert self.carrier_system.config.zones[0].hold_activity is None
        await self.data_updater.message_handler(self.websocket_message_str)
        assert self.carrier_system.config.zones[0].hold_activity == ActivityTypes.MANUAL
        reprocessed_config = Config.from_dict(Config.to_dict(self.carrier_system.config))
        assert reprocessed_config.zones[0].hold_activity == ActivityTypes.MANUAL

class MessageConfigZoneProgram(WebsocketDataUpdaterTestBase):
    websocket_message_path = 'messages/config_zone_program.json'

    async def test_message_handler(self):
        await self.data_updater.message_handler(self.websocket_message_str)
        reprocessed_config = Config.from_dict(Config.to_dict(self.carrier_system.config))
        assert self.carrier_system.config.zones[0].program == reprocessed_config.zones[0].program
