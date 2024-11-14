# run with "python3 src/carrier_api/stub.py"
import logging
import asyncio
from threading import Event

from getpass import getpass
from pathlib import Path
import sys

import asyncio

path_root = Path(__file__).parents[2]
sys.path.append(str(path_root))


logger = logging.getLogger("src.carrier_api")
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)

# logging.basicConfig()
# logging.getLogger().setLevel(logging.DEBUG)
# requests_log = logging.getLogger("requests.packages.urllib3")
# requests_log.setLevel(logging.DEBUG)
# requests_log.propagate = True


from src.carrier_api.api_connection import ApiConnection
from src.carrier_api.config import Config, ConfigZone, ConfigZoneActivity
from src.carrier_api.const import SystemModes, ActivityNames, FanModes


username = input("username: ")
password = getpass()
connection = ApiConnection(username=username, password=password)
connection.activate()
system = connection.get_systems()[0]
zone: ConfigZone = system.config.zones[0]
logger.debug(system)
# connection.set_config_hold(system_serial=system.serial, zone_id=zone.api_id, activity_name=ActivityNames.MANUAL, hold_until=None)
# logger.debug(zone.current_activity())
# connection.resume_schedule(
#     system_serial=system.serial, zone_id=system.config.zones[0].api_id
# )
# hold_until = zone.next_activity_time()
# logger.debug(hold_until)
# logger.debug(zone.next_activity_time())
# connection.set_config_mode(system_serial, SystemModes.HEAT.value)
# connection.set_config_manual_activity(system_serial=system.serial, zone_id=zone.api_id, heat_set_point=71, cool_set_point=80, fan_mode=FanModes.LOW)
