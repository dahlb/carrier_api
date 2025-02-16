from datetime import datetime, timedelta
from json import dumps
from logging import getLogger
from typing import Any, Union, Dict, List

from aiohttp import ClientSession
from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
from graphql import ExecutionResult, get_introspection_query, parse

from .const import (
    FanModes,
    ActivityTypes,
    HeatSourceTypes, SystemModes,
)
from .energy import Energy
from .profile import Profile
from .status import Status
from .config import Config
from .errors import AuthError
from .system import System

_LOGGER = getLogger(__name__)


class ApiConnectionGraphql:
    expires_at: datetime = datetime.now()
    refresh_token: str = None
    token_type: str = None
    access_token: str = None

    def __init__(
            self,
            username: str,
            password: str,
            client_session: ClientSession | None = None,
    ):
        self.username = username
        self.password = password
        if client_session is None:
            self.api_session = ClientSession(raise_for_status=False)
        else:
            self.api_session = client_session

    async def cleanup(self) -> None:
        await self.api_session.close()

    async def login(self) -> None:
        transport = AIOHTTPTransport(url="https://dataservice.infinity.iot.carrier.com/graphql-no-auth")
        async with Client(
                transport=transport,
                fetch_schema_from_transport=True,
        ) as session:
            query = gql(
                """
                mutation assistedLogin($input: AssistedLoginInput!) {
                    assistedLogin(input: $input) {
                        success
                        status
                        errorMessage
                        data {
                            token_type
                            expires_in
                            access_token
                            scope
                            refresh_token
                        }
                    }
                }
            """
            )

            result = await session.execute(query,
                                           variable_values={"input": {"password": self.password, "username": self.username}},
                                           operation_name="assistedLogin")
            success = result["assistedLogin"]["success"]
            _LOGGER.debug(result)
            if success:
                self.expires_at = datetime.now() + timedelta(seconds=result["assistedLogin"]["data"]["expires_in"])
                self.token_type = result["assistedLogin"]["data"]["token_type"]
                self.access_token = result["assistedLogin"]["data"]["access_token"]
                self.refresh_token = result["assistedLogin"]["data"]["refresh_token"]
            else:
                raise AuthError(result)

    async def check_auth_expiration(self) -> None:
        if self.expires_at < datetime.now():
            await self.refresh_auth_token()

    async def refresh_auth_token(self) -> None:
        url = "https://sso.carrier.com/oauth2/default/v1/token"
        json_body = {
            "client_id": "0oa1ce7hwjuZbfOMB4x7",
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "scope": "offline_access"
        }
        response = await self.api_session.post(url=url, data=json_body)
        response.raise_for_status()
        data = await response.json()
        _LOGGER.debug(data)
        self.expires_at = datetime.now() + timedelta(seconds=data["expires_in"])
        self.token_type = data["token_type"]
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]

    async def authed_query(self, operation_name: str, query: gql, variable_values: Dict[str, Any]) -> Union[Dict[str, Any], ExecutionResult]:
        await self.check_auth_expiration()
        transport = AIOHTTPTransport(url="https://dataservice.infinity.iot.carrier.com/graphql",
                                     headers={'Authorization': f"{self.token_type} {self.access_token}"})
        async with Client(
                transport=transport,
                fetch_schema_from_transport=True,
        ) as session:
            return await session.execute(query, variable_values=variable_values, operation_name=operation_name)

    async def get_user_info(self) -> Dict[str, Any]:
        operation_name = "getUser"
        query = gql(
            """
            query getUser($userName: String!, $appVersion: String, $brand: String, $os: String, $osVersion: String) {
                user(
                    userName: $userName
                    appVersion: $appVersion
                    brand: $brand
                    os: $os
                    osVersion: $osVersion
                ) {
                    username
                    identityId
                    first
                    last
                    email
                    emailVerified
                    secondaryEmail
                    secondaryEmailVerified
                    phone1
                    promoEmail
                    acceptedTermsOfServiceDateTime
                    creationSource
                    postal
                    locations {
                        locationId
                        name
                        street1
                        street2
                        city
                        state
                        country
                        postal
                        systems {
                            config {
                                zones {
                                    id
                                    enabled
                                }
                            }
                            profile {
                                serial
                                name
                            }
                            status {
                                isDisconnected
                            }
                        }
                        devices {
                            deviceId
                            type
                            thingName
                            name
                            connectionStatus
                        }
                        entryLevels {
                            name
                            serial
                            connection {
                                isConnected
                            }
                        }
                    }
                }
            }
            """
        )
        variable_values = {"userName": self.username}
        return await self.authed_query(operation_name=operation_name, query=query, variable_values=variable_values)

    async def get_systems(self) -> Dict[str, Any]:
        operation_name = "getInfinitySystems"
        query = gql(
            """
            query getInfinitySystems($userName: String!) {
              infinitySystems(userName: $userName) {
                profile {
                  serial
                  name
                  firmware
                  model
                  brand
                  indoorModel
                  indoorSerial
                  idutype
                  idusource
                  outdoorModel
                  outdoorSerial
                  odutype
                }
                status {
                  localTime
                  localTimeOffset
                  utcTime
                  wcTime
                  isDisconnected
                  cfgem
                  mode
                  vacatrunning
                  oat
                  odu {
                    type
                    opstat
                  }
                  filtrlvl
                  idu {
                    type
                    opstat
                    cfm
                  }
                  vent
                  ventlvl
                  humid
                  humlvl
                  uvlvl
                  zones {
                    id
                    rt
                    rh
                    fan
                    htsp
                    clsp
                    hold
                    enabled
                    currentActivity
                  }
                }
                config {
                  etag
                  mode
                  cfgem
                  cfgdead
                  cfghumid
                  erate
                  grate
                  heatsource
                  vacat
                  vacstart
                  vacend
                  vacmint
                  vacmaxt
                  vacfan
                  fueltype
                  gasunit
                  cfgvent
                  cfghumid
                  cfguv
                  cfgfan
                  vacat
                  filtertype
                  filterinterval
                  humidityVacation {
                    rclgovercool
                    ventspdclg
                    ventclg
                    rhtg
                    humidifier
                    humid
                    venthtg
                    rclg
                    ventspdhtg
                  }
                  zones {
                    id
                    name
                    enabled
                    hold
                    holdActivity
                    otmr
                    program {
                      id
                      day {
                        id
                        zoneId
                        period {
                          id
                          zoneId
                          dayId
                          activity
                          time
                          enabled
                        }
                      }
                    }
                    activities {
                      id
                      zoneId
                      type
                      fan
                      previousFan
                      htsp
                      clsp
                    }
                  }
                  wholeHouse {
                    hold
                    holdActivity
                    otmr
                    activities {
                      id
                      htsp
                      clsp
                      fan
                    }
                  }
                  humidityAway {
                    humid
                    humidifier
                    rhtg
                    rclg
                    rclgovercool
                  }
                  humidityHome {
                    humid
                    humidifier
                    rhtg
                    rclg
                    rclgovercool
                  }
                }
              }
            }
            """
        )
        variable_values = {"userName": self.username}
        return await self.authed_query(operation_name=operation_name, query=query, variable_values=variable_values)

    async def get_energy(self, system_serial: str) -> Dict[str, Any]:
        operation_name = "getInfinityEnergy"
        query = gql(
            """
            query getInfinityEnergy($serial: String!) {
              infinityEnergy(serial: $serial) {
                energyConfig {
                  cooling {
                    display
                    enabled
                  }
                  eheat {
                    display
                    enabled
                  }
                  fan {
                    display
                    enabled
                  }
                  fangas {
                    display
                    enabled
                  }
                  gas {
                    display
                    enabled
                  }
                  hpheat {
                    display
                    enabled
                  }
                  looppump {
                    display
                    enabled
                  }
                  reheat {
                    display
                    enabled
                  }
                  hspf
                  seer
                }
                energyPeriods {
                  energyPeriodType
                  eHeatKwh
                  coolingKwh
                  fanGasKwh
                  fanKwh
                  hPHeatKwh
                  loopPumpKwh
                  gasKwh
                  reheatKwh
                }
              }
            }
            """
        )
        variable_values = {"serial": system_serial}
        return await self.authed_query(operation_name=operation_name, query=query, variable_values=variable_values)

    async def load_data(self) -> List[System]:
        system_response = await self.get_systems()
        systems = []
        for system_response in system_response["infinitySystems"]:
            profile = Profile(raw=system_response["profile"])
            status = Status(raw=system_response["status"])
            config = Config(raw=system_response["config"])
            energy_response = await self.get_energy(profile.serial)
            energy = Energy(raw=energy_response["infinityEnergy"])
            systems.append(System(profile=profile, status=status, config=config, energy=energy))
        return systems

    async def _update_infinity_config(self, variables: Dict[str, Any]) -> Dict[str, Any]:
        query = gql(
            """
            mutation updateInfinityConfig($input: InfinityConfigInput!) {
                updateInfinityConfig(input: $input) {
                    etag
                }
            }
            """
        )
        return await self.authed_query(operation_name="updateInfinityConfig", query=query, variable_values=variables)

    async def _update_infinity_zone_activity(self, variables: Dict[str, Any]) -> Dict[str, Any]:
        query = gql(
            """
            mutation updateInfinityZoneActivity($input: InfinityZoneActivityInput!) {
                updateInfinityZoneActivity(input: $input) {
                    etag
                }
            }
            """
        )
        return await self.authed_query(operation_name="updateInfinityZoneActivity", query=query, variable_values=variables)

    async def _update_infinity_zone_config(self, variables: Dict[str, Any]) -> Dict[str, Any]:
        query = gql(
            """
            mutation updateInfinityZoneConfig($input: InfinityZoneConfigInput!) {
                updateInfinityZoneConfig(input: $input) {
                    etag
                }
            }
            """
        )
        return await self.authed_query(operation_name="updateInfinityZoneConfig", query=query, variable_values=variables)

    async def set_config_mode(self, system_serial: str, mode: SystemModes) -> Dict[str, Any]:
        if mode not in SystemModes:
            raise ValueError(f"{mode} is not a valid system mode")
        variables = {
            "input": {
                "serial": system_serial,
                "mode": mode.value
            }
        }
        return await self._update_infinity_config(variables)

    async def set_heat_source(self, system_serial: str, heat_source: HeatSourceTypes) -> Dict[str, Any]:
        if heat_source not in HeatSourceTypes:
            raise ValueError(f"{heat_source} is not a valid heat source")
        variables = {
            "input": {
                "serial": system_serial,
                "heatsource": heat_source.value
            }
        }
        return await self._update_infinity_config(variables)

    async def set_humidifier(self, system_serial: str, humidifier_on: bool = None, over_cooling: bool = None, cooling_percent: 5|10|15|20|25|30|35|40|45 = None, heating_percent: 5|10|15|20|25|30|35|40|45 = None) -> Dict[str, Any]:
        variables = {
            "input": {
                "serial": system_serial,
                "humidityHome": {
                    "humid": "manual",
                    "humidifier": "on",
                }
            }
        }
        if humidifier_on is not None and humidifier_on is False:
            variables["input"]["humidityHome"] = {
                "humid": "off",
                "humidifier": "off",
            }
        if over_cooling is not None:
            variables["input"]["humidityHome"]["rclgovercool"] = "on" if over_cooling else "off"
        if cooling_percent is not None:
            variables["input"]["humidityHome"]["rclg"] = cooling_percent / 5
        if heating_percent is not None:
            variables["input"]["humidityHome"]["rhtg"] = heating_percent / 5
        return await self._update_infinity_config(variables)

    async def update_fan(self, system_serial: str, zone_id: str, activity_type: ActivityTypes, fan_mode: FanModes) -> Dict[str, Any]:
        if fan_mode not in FanModes:
            raise ValueError(f"{fan_mode} is not a valid fan mode")
        if activity_type not in ActivityTypes:
            raise ValueError(f"{activity_type} is not a valid activity type")
        variables = {
            "input": {
                "serial": system_serial,
                "activityType": activity_type.value,
                "fan": fan_mode.value,
                "zoneId": zone_id
            }
        }
        return await self._update_infinity_zone_activity(variables=variables)

    async def set_config_hold(
        self,
        system_serial: str,
        zone_id: str,
        activity_type: ActivityTypes,
        hold_until: str = None,
    ):
        if activity_type not in ActivityTypes:
            raise ValueError(f"{activity_type} is not a valid activity type")
        variables = {
            "input": {
                "serial": system_serial,
                "hold": "on",
                "holdActivity": activity_type.value,
                "otmr": hold_until,
                "zoneId": zone_id
            }
        }
        return await self._update_infinity_zone_config(variables=variables)

    async def resume_schedule(self, system_serial: str, zone_id: str):
        variables = {
            "input": {
                "serial": system_serial,
                "hold": "off",
                "holdActivity": None,
                "otmr": None,
                "zoneId": zone_id
            }
        }
        return await self._update_infinity_zone_config(variables=variables)

    async def set_config_manual_activity(
        self,
        system_serial: str,
        zone_id: str,
        heat_set_point: int,
        cool_set_point: int,
        fan_mode: FanModes,
    ):
        if fan_mode not in FanModes:
            raise ValueError(f"{fan_mode} is not a valid fan mode")
        variables = {
            "input": {
                "serial": system_serial,
                "activityType": "manual",
                "clsp": float(cool_set_point),
                "fan": fan_mode.value,
                "htsp": float(heat_set_point),
                "zoneId": zone_id
            }
        }
        return await self._update_infinity_zone_activity(variables=variables)
