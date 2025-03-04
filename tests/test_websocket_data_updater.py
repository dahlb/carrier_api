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

from src.carrier_api import Profile, Status, Config, Energy, System, WebsocketDataUpdater, ActivityTypes # noqa: E402


class WebsocketDataUpdaterTestBase(IsolatedAsyncioTestCase):
    def setUp(self):
        self.system_response = json.loads(open(resources.files().joinpath('graphql/systems.json')).read())
        energy_response = json.loads(open(resources.files().joinpath('graphql/energy.json')).read())
        systems = []
        for system_response in self.system_response["infinitySystems"]:
            profile = Profile(raw=system_response["profile"])
            status = Status(raw=system_response["status"])
            config = Config(raw=system_response["config"])
            energy = Energy(raw=energy_response["infinityEnergy"])
            systems.append(System(profile=profile, status=status, config=config, energy=energy))
        self.data_updater = WebsocketDataUpdater(systems)
        self.websocket_message_str = open(resources.files().joinpath(self.websocket_message_path)).read()
        self.carrier_system = systems[0]

class MessageIduCfm(WebsocketDataUpdaterTestBase):
    websocket_message_path = 'messages/status_idu_cfm.json'

    async def test_setup(self):
        assert self.carrier_system.status.raw == self.system_response["infinitySystems"][0]["status"]

    async def test_message_handler(self):
        assert self.carrier_system.status.airflow_cfm == 1239
        await self.data_updater.message_handler(self.websocket_message_str)
        assert self.carrier_system.status.airflow_cfm == 525
        assert Status(raw=self.carrier_system.status.raw).airflow_cfm == 525

class MessageOduOpmode(WebsocketDataUpdaterTestBase):
    websocket_message_path = 'messages/status_odu_opmode.json'

    async def test_message_handler(self):
        assert self.carrier_system.status.mode == "heat"
        await self.data_updater.message_handler(self.websocket_message_str)
        assert self.carrier_system.status.mode == "heat"
        assert Status(raw=self.carrier_system.status.raw).mode == "heat"

class MessageZoneRh(WebsocketDataUpdaterTestBase):
    websocket_message_path = 'messages/status_zone_rh.json'

    async def test_message_handler(self):
        assert self.carrier_system.status.zones[0].humidity == 32
        await self.data_updater.message_handler(self.websocket_message_str)
        assert self.carrier_system.status.zones[0].humidity == 34
        assert Status(raw=self.carrier_system.status.raw).zones[0].humidity == 34

class MessageZoneConditioning(WebsocketDataUpdaterTestBase):
    websocket_message_path = 'messages/status_zone_conditioning.json'

    async def test_message_handler(self):
        assert self.carrier_system.status.zones[0].conditioning == "active_heat"
        await self.data_updater.message_handler(self.websocket_message_str)
        assert self.carrier_system.status.zones[0].conditioning == "idle"
        assert Status(raw=self.carrier_system.status.raw).zones[0].conditioning == "idle"

class MessageZoneActivity(WebsocketDataUpdaterTestBase):
    websocket_message_path = 'messages/status_zone_activity.json'

    async def test_message_handler(self):
        assert self.carrier_system.status.zones[0].current_activity == ActivityTypes.WAKE
        assert self.carrier_system.status.zones[0].heat_set_point == 74
        assert self.carrier_system.status.zones[0].cool_set_point == 78
        await self.data_updater.message_handler(self.websocket_message_str)
        assert self.carrier_system.status.zones[0].current_activity == ActivityTypes.HOME
        assert self.carrier_system.status.zones[0].heat_set_point == 77
        assert self.carrier_system.status.zones[0].cool_set_point == 79
        reprocessed_status = Status(raw=self.carrier_system.status.raw)
        assert reprocessed_status.zones[0].current_activity == ActivityTypes.HOME
        assert reprocessed_status.zones[0].heat_set_point == 77
        assert reprocessed_status.zones[0].cool_set_point == 79
