"""GraphQL client for Carrier authentication, queries, and config updates."""

from datetime import UTC, datetime, timedelta
from logging import getLogger
from typing import Any, Literal

from aiohttp import ClientError, ClientResponseError, ClientSession
from gql import Client, GraphQLRequest, gql
from gql.transport.aiohttp import AIOHTTPTransport
from gql.transport.exceptions import (
    TransportError as GraphqlTransportError,
    TransportQueryError,
    TransportServerError,
)
from graphql import GraphQLError

from .api_websocket import ApiWebsocket
from .config import Config
from .const import ActivityTypes, FanModes, HeatSourceTypes, SystemModes
from .energy import Energy
from .entry_level import EntryLevelSystem
from .errors import (
    CarrierApiAuthError,
    CarrierApiConnectionError,
    CarrierApiGraphqlError,
    CarrierApiTokenRefreshError,
)
from .profile import Profile
from .status import Status
from .system import System

_LOGGER = getLogger(__name__)
GRAPHQL_EXECUTE_TIMEOUT_SECONDS = 60

_CONNECTION_ERRORS = (GraphqlTransportError, ClientError, TimeoutError, OSError)
_AUTH_HTTP_STATUSES = {401, 403}


def _is_auth_transport_error(error: BaseException) -> bool:
    """Return whether a transport error represents Carrier auth rejection.

    Args:
        error: Exception raised by the GraphQL transport.

    Returns:
        ``True`` when the GraphQL endpoint rejected the request with an
        authentication-related HTTP status.
    """
    return isinstance(error, TransportServerError) and error.code in _AUTH_HTTP_STATUSES


async def _response_json_object(response: Any) -> dict[str, Any]:
    """Read a JSON object response body when available.

    Args:
        response: aiohttp-like response object with an async ``json`` method.

    Returns:
        The decoded JSON object, or an empty object when the body is malformed
        or is not a JSON object.
    """
    try:
        data = await response.json()
    except ClientError, TimeoutError, OSError, TypeError, ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


class ApiConnectionGraphql:
    """Async Carrier GraphQL API connection with token and websocket support."""

    expires_at: datetime = datetime.now(UTC)
    refresh_token: str | None = None
    token_type: str | None = None
    access_token: str | None = None
    api_websocket: ApiWebsocket | None = None

    def __init__(
        self,
        username: str,
        password: str,
        client_session: ClientSession | None = None,
    ) -> None:
        """Create a Carrier GraphQL API connection.

        Args:
            username: Carrier account username.
            password: Carrier account password.
            client_session: Optional aiohttp session to reuse for token refresh
                and websocket operations. A new session is created when omitted.
        """
        self.username = username
        self.password = password
        if client_session is None:
            self.api_session = ClientSession(raise_for_status=False)
        else:
            self.api_session = client_session

    async def cleanup(self) -> None:
        """Close the underlying aiohttp session owned by the connection."""
        try:
            await self.api_session.close()
        except (ClientError, TimeoutError, OSError) as error:
            raise CarrierApiConnectionError("Carrier API session cleanup failed") from error

    async def login(self) -> None:
        """Authenticate with Carrier and initialize websocket support.

        Raises:
            CarrierApiAuthError: If the assisted login mutation reports an unsuccessful
                authentication result.
        """
        transport = AIOHTTPTransport(
            url="https://dataservice.infinity.iot.carrier.com/graphql-no-auth", ssl=True
        )
        try:
            async with Client(
                transport=transport,
                fetch_schema_from_transport=False,
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

                result = await session.execute(
                    query,
                    variable_values={
                        "input": {"password": self.password, "username": self.username}
                    },
                    operation_name="assistedLogin",
                )
                success = result["assistedLogin"]["success"]
                if success:
                    self.expires_at = datetime.now(UTC) + timedelta(
                        seconds=result["assistedLogin"]["data"]["expires_in"]
                    )
                    self.token_type = result["assistedLogin"]["data"]["token_type"]
                    self.access_token = result["assistedLogin"]["data"]["access_token"]
                    self.refresh_token = result["assistedLogin"]["data"]["refresh_token"]
                    if self.api_websocket is None:
                        self.api_websocket = ApiWebsocket(self)
                else:
                    error_message = result["assistedLogin"].get("errorMessage")
                    if isinstance(error_message, str) and error_message:
                        message = f"Carrier assistedLogin failed: {error_message}"
                    else:
                        message = "Carrier assistedLogin failed"
                    raise CarrierApiAuthError(message, payload=result)
        except TransportQueryError as error:
            raise CarrierApiGraphqlError("Carrier authentication GraphQL request failed") from error
        except _CONNECTION_ERRORS as error:
            raise CarrierApiConnectionError("Carrier authentication connection failed") from error
        except GraphQLError as error:
            raise CarrierApiGraphqlError("Carrier authentication GraphQL request failed") from error

    async def check_auth_expiration(self) -> None:
        """Ensure the connection has a valid access token before API use."""
        if self.refresh_token is None:
            await self.login()
        if self.expires_at < datetime.now(UTC):
            await self.refresh_auth_token()

    async def refresh_auth_token(self) -> None:
        """Refresh the OAuth access token using the stored refresh token.

        Raises:
            CarrierApiAuthError: If Carrier rejects the refresh token as invalid
                or unauthorized.
            CarrierApiTokenRefreshError: If token refresh fails before Carrier
                returns a valid OAuth response.
        """
        url = "https://sso.carrier.com/oauth2/default/v1/token"
        json_body = {
            "client_id": "0oa1ce7hwjuZbfOMB4x7",
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "scope": "offline_access",
        }
        response: Any | None = None
        try:
            response = await self.api_session.post(url=url, data=json_body)
            response.raise_for_status()
            data = await response.json()
        except ClientResponseError as error:
            data = {} if response is None else await _response_json_object(response)
            if error.status in {401, 403} or (
                error.status == 400 and data.get("error") == "invalid_grant"
            ):
                raise CarrierApiAuthError("Carrier token refresh was rejected") from error
            raise CarrierApiTokenRefreshError("Carrier token refresh failed") from error
        except (ClientError, TimeoutError, OSError, TypeError, ValueError) as error:
            raise CarrierApiTokenRefreshError("Carrier token refresh failed") from error
        try:
            self.expires_at = datetime.now(UTC) + timedelta(seconds=data["expires_in"])
            self.token_type = data["token_type"]
            self.access_token = data["access_token"]
            self.refresh_token = data["refresh_token"]
        except (KeyError, TypeError) as error:
            raise CarrierApiTokenRefreshError("Carrier token refresh failed") from error

    async def authed_query(
        self, operation_name: str, query: GraphQLRequest, variable_values: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute an authenticated Carrier GraphQL operation.

        Args:
            operation_name: GraphQL operation name to execute.
            query: Parsed GraphQL request.
            variable_values: Variables to send with the operation.

        Returns:
            The decoded GraphQL response data.
        """
        await self.check_auth_expiration()
        transport = AIOHTTPTransport(
            url="https://dataservice.infinity.iot.carrier.com/graphql",
            headers={"Authorization": f"{self.token_type} {self.access_token}"},
            ssl=True,
        )
        try:
            async with Client(
                transport=transport,
                fetch_schema_from_transport=False,
                execute_timeout=GRAPHQL_EXECUTE_TIMEOUT_SECONDS,
            ) as session:
                return await session.execute(
                    query, variable_values=variable_values, operation_name=operation_name
                )
        except TransportQueryError as error:
            raise CarrierApiGraphqlError(
                f"Carrier GraphQL operation failed: {operation_name}"
            ) from error
        except _CONNECTION_ERRORS as error:
            if _is_auth_transport_error(error):
                raise CarrierApiAuthError(
                    f"Carrier authorization failed during GraphQL operation: {operation_name}"
                ) from error
            raise CarrierApiConnectionError(
                f"Carrier connection failed during GraphQL operation: {operation_name}"
            ) from error
        except GraphQLError as error:
            raise CarrierApiGraphqlError(
                f"Carrier GraphQL operation failed: {operation_name}"
            ) from error

    async def get_user_info(self) -> dict[str, Any]:
        """Fetch Carrier account profile, location, and device metadata.

        Returns:
            The decoded ``getUser`` GraphQL response data.
        """
        operation_name = "getUser"
        query = gql(
            """
            query getUser(
                $userName: String!,
                $appVersion: String,
                $brand: String,
                $os: String,
                $osVersion: String
            ) {
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
                    postal
                    locations {
                        locationId
                        name
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
                    }
                }
            }
            """
        )
        variable_values = {"userName": self.username}
        return await self.authed_query(
            operation_name=operation_name, query=query, variable_values=variable_values
        )

    async def get_systems(self) -> dict[str, Any]:
        """Fetch configured Carrier Infinity systems for the current user.

        Returns:
            The decoded ``getInfinitySystems`` GraphQL response data containing
            profile, status, and config payloads.
        """
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
                    iducfm
                  }
                  filtrlvl
                  idu {
                    type
                    opstat
                    cfm
                    statpress
                    blwrpm
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
                    zoneconditioning
                  }
                }
                config {
                  etag
                  mode
                  cfgem
                  cfgdead
                  cfgvent
                  cfghumid
                  cfguv
                  cfgfan
                  heatsource
                  vacat
                  vacstart
                  vacend
                  vacmint
                  vacmaxt
                  vacfan
                  fueltype
                  gasunit
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
                    occEnabled
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
                      htsp
                      clsp
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
        return await self.authed_query(
            operation_name=operation_name, query=query, variable_values=variable_values
        )

    async def get_energy(self, system_serial: str) -> dict[str, Any]:
        """Fetch energy configuration and usage for a Carrier system.

        Args:
            system_serial: Serial number of the Carrier system to query.

        Returns:
            The decoded ``getInfinityEnergy`` GraphQL response data.
        """
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
        return await self.authed_query(
            operation_name=operation_name, query=query, variable_values=variable_values
        )

    async def load_data(self) -> list[System]:
        """Load all Carrier systems with status, config, and energy models.

        Returns:
            A list of fully constructed system aggregates for the account.
        """
        systems_response = await self.get_systems()
        systems = []
        for system_response in systems_response["infinitySystems"]:
            profile = Profile(raw=system_response["profile"])
            status = Status(raw=system_response["status"])
            config = Config(raw=system_response["config"])
            energy_response = await self.get_energy(profile.serial)
            energy = Energy(raw=energy_response["infinityEnergy"])
            systems.append(System(profile=profile, status=status, config=config, energy=energy))
        return systems

    async def get_entry_level_systems(self) -> dict[str, Any]:
        """Fetch entry-level (Smart Thermostat) systems for the current user.

        These are the non-Infinity Carrier Smart Thermostat devices, exposed by
        a separate query from ``infinitySystems``.

        Returns:
            The decoded ``getEntryLevelSystems`` GraphQL response data.
        """
        operation_name = "getEntryLevelSystems"
        query = gql(
            """
            query getEntryLevelSystems($username: String!) {
              entryLevelSystems(username: $username) {
                serial
                name
                location_id
                model
                firmware
                temp_unit_format
                connection {
                  isConnected
                  deviceId
                }
                zones {
                  index
                  mode
                  rt
                  rh
                  clsp { current min }
                  htsp { current max }
                  fan_mode
                  schedule_enabled
                  hold_end_time
                  hold_countdown
                  stage_status
                  outside_temp
                }
              }
            }
            """
        )
        variable_values = {"username": self.username}
        return await self.authed_query(
            operation_name=operation_name, query=query, variable_values=variable_values
        )

    async def load_entry_level_data(self) -> list[EntryLevelSystem]:
        """Load all entry-level systems for the account.

        Returns:
            A list of entry-level system models for the account.
        """
        response = await self.get_entry_level_systems()
        return [
            EntryLevelSystem(raw=system_response)
            for system_response in (response.get("entryLevelSystems") or [])
        ]

    async def update_entry_level_zone(
        self,
        serial: str,
        index: int = 0,
        mode: str | None = None,
        cool_set_point: float | None = None,
        heat_set_point: float | None = None,
        schedule_enabled: bool | None = None,
        hold_end_time: int | None = None,
        fan_mode: str | None = None,
    ) -> dict[str, Any]:
        """Update an entry-level zone's mode, set points, hold, or fan.

        Only the provided fields are sent. Carrier expects the cool and heat set
        points together, so pass both when changing a set point.

        Args:
            serial: Serial number of the entry-level system to update.
            index: Zone index to update (entry-level systems are single-zone).
            mode: Requested HVAC mode (``cool``/``heat``/``off``/``auto``).
            cool_set_point: Requested cool set point.
            heat_set_point: Requested heat set point.
            schedule_enabled: ``False`` holds the zone, ``True`` resumes the
                programmed schedule.
            hold_end_time: Optional Carrier hold-until value.
            fan_mode: Requested fan mode.

        Returns:
            The decoded mutation response.
        """
        query = gql(
            """
            mutation updateEntryLevelZone($input: EntryLevelZoneInput!) {
              updateEntryLevelZone(input: $input) {
                success
              }
            }
            """
        )
        zone_input: dict[str, Any] = {"serial": serial, "index": index}
        if mode is not None:
            zone_input["mode"] = mode
        if cool_set_point is not None:
            zone_input["clsp"] = {"current": cool_set_point}
        if heat_set_point is not None:
            zone_input["htsp"] = {"current": heat_set_point}
        if schedule_enabled is not None:
            zone_input["schedule_enabled"] = schedule_enabled
        if hold_end_time is not None:
            zone_input["hold_end_time"] = hold_end_time
        if fan_mode is not None:
            zone_input["fan_mode"] = fan_mode
        _LOGGER.debug("updateEntryLevelZone: %s", zone_input)
        return await self.authed_query(
            operation_name="updateEntryLevelZone",
            query=query,
            variable_values={"input": zone_input},
        )

    async def hold_entry_level_zone(
        self,
        serial: str,
        index: int = 0,
        cool_set_point: float | None = None,
        heat_set_point: float | None = None,
        hold_end_time: int | None = None,
    ) -> dict[str, Any]:
        """Hold an entry-level zone off its schedule at the given set points.

        Args:
            serial: Serial number of the entry-level system to update.
            index: Zone index to update.
            cool_set_point: Optional cool set point to apply with the hold.
            heat_set_point: Optional heat set point to apply with the hold.
            hold_end_time: Optional Carrier hold-until value.

        Returns:
            The decoded mutation response.
        """
        return await self.update_entry_level_zone(
            serial,
            index,
            cool_set_point=cool_set_point,
            heat_set_point=heat_set_point,
            schedule_enabled=False,
            hold_end_time=hold_end_time,
        )

    async def resume_entry_level_schedule(self, serial: str, index: int = 0) -> dict[str, Any]:
        """Clear an entry-level zone hold and resume its programmed schedule.

        Args:
            serial: Serial number of the entry-level system to update.
            index: Zone index to update.

        Returns:
            The decoded mutation response.
        """
        return await self.update_entry_level_zone(serial, index, schedule_enabled=True)

    async def _update_infinity_config(self, variables: dict[str, Any]) -> dict[str, Any]:
        """Run the Carrier system-level configuration mutation.

        Args:
            variables: GraphQL variables containing an ``InfinityConfigInput``.

        Returns:
            The decoded mutation response.
        """
        query = gql(
            """
            mutation updateInfinityConfig($input: InfinityConfigInput!) {
                updateInfinityConfig(input: $input) {
                    etag
                }
            }
            """
        )
        _LOGGER.debug("updateInfinityConfig: %s", variables)
        response = await self.authed_query(
            operation_name="updateInfinityConfig", query=query, variable_values=variables
        )
        if self.api_websocket is not None:
            await self.api_websocket.send_reconcile()
        else:
            _LOGGER.warning("No API websocket connection")
        return response

    async def _update_infinity_zone_activity(self, variables: dict[str, Any]) -> dict[str, Any]:
        """Run the Carrier zone activity configuration mutation.

        Args:
            variables: GraphQL variables containing an
                ``InfinityZoneActivityInput``.

        Returns:
            The decoded mutation response.
        """
        query = gql(
            """
            mutation updateInfinityZoneActivity($input: InfinityZoneActivityInput!) {
                updateInfinityZoneActivity(input: $input) {
                    etag
                }
            }
            """
        )
        _LOGGER.debug("updateInfinityZoneActivity: %s", variables)
        response = await self.authed_query(
            operation_name="updateInfinityZoneActivity", query=query, variable_values=variables
        )
        if self.api_websocket is not None:
            await self.api_websocket.send_reconcile()
        else:
            _LOGGER.warning("No API websocket connection")
        return response

    async def _update_infinity_zone_config(self, variables: dict[str, Any]) -> dict[str, Any]:
        """Run the Carrier zone configuration mutation.

        Args:
            variables: GraphQL variables containing an ``InfinityZoneConfigInput``.

        Returns:
            The decoded mutation response.
        """
        query = gql(
            """
            mutation updateInfinityZoneConfig($input: InfinityZoneConfigInput!) {
                updateInfinityZoneConfig(input: $input) {
                    etag
                }
            }
            """
        )
        _LOGGER.debug("updateInfinityZoneConfig: %s", variables)
        response = await self.authed_query(
            operation_name="updateInfinityZoneConfig", query=query, variable_values=variables
        )
        if self.api_websocket is not None:
            await self.api_websocket.send_reconcile()
        else:
            _LOGGER.warning("No API websocket connection")
        return response

    async def set_config_mode(self, system_serial: str, mode: SystemModes) -> dict[str, Any]:
        """Update a Carrier system's operating mode.

        Args:
            system_serial: Serial number of the system to update.
            mode: Requested system operating mode.

        Returns:
            The decoded mutation response.

        Raises:
            ValueError: If ``mode`` is not a ``SystemModes`` member.
        """
        if mode not in SystemModes:
            raise ValueError(f"{mode} is not a valid system mode")
        variables = {"input": {"serial": system_serial, "mode": mode.value}}
        return await self._update_infinity_config(variables)

    async def set_config_heat_humidity(
        self, system_serial: str, humidity_target: int
    ) -> dict[str, Any]:
        """Update the heating humidifier target for home mode.

        Args:
            system_serial: Serial number of the system to update.
            humidity_target: Target relative humidity percentage. Carrier
                accepts zero or five-percent increments from 5 through 45.

        Returns:
            The decoded mutation response.

        Raises:
            ValueError: If ``humidity_target`` is outside Carrier's accepted
                values.
        """
        if humidity_target not in [0, 5, 10, 15, 20, 25, 30, 35, 40, 45]:
            raise ValueError(f"{humidity_target} is not a valid humidity target")
        variables = {"input": {"serial": system_serial, "humidityHome": {}}}
        if humidity_target == 0:
            variables["input"]["humidityHome"] = {"humidifier": "off"}
        else:
            variables["input"]["humidityHome"] = {"humidifier": "on", "rhtg": humidity_target / 5}
        return await self._update_infinity_config(variables)

    async def set_heat_source(
        self, system_serial: str, heat_source: HeatSourceTypes
    ) -> dict[str, Any]:
        """Update which equipment source should provide heat.

        Args:
            system_serial: Serial number of the system to update.
            heat_source: Requested heat source routing mode.

        Returns:
            The decoded mutation response.

        Raises:
            ValueError: If ``heat_source`` is not a ``HeatSourceTypes`` member.
        """
        if heat_source not in HeatSourceTypes:
            raise ValueError(f"{heat_source} is not a valid heat source")
        variables = {"input": {"serial": system_serial, "heatsource": heat_source.value}}
        return await self._update_infinity_config(variables)

    async def set_humidifier(
        self,
        system_serial: str,
        humidifier_on: bool | None = None,
        over_cooling: bool | None = None,
        cooling_percent: Literal[5, 10, 15, 20, 25, 30, 35, 40, 45] | None = None,
        heating_percent: Literal[5, 10, 15, 20, 25, 30, 35, 40, 45] | None = None,
    ) -> dict[str, Any]:
        """Update home-mode humidifier and dehumidification settings.

        Args:
            system_serial: Serial number of the system to update.
            humidifier_on: When ``False``, disable humidification. ``None``
                leaves the default manual-on mutation payload in place.
            over_cooling: Optional over-cooling setting for dehumidification.
            cooling_percent: Optional cooling humidity target in five-percent
                increments accepted by Carrier.
            heating_percent: Optional heating humidity target in five-percent
                increments accepted by Carrier.

        Returns:
            The decoded mutation response.
        """
        variables: dict[str, Any] = {
            "input": {
                "serial": system_serial,
                "humidityHome": {
                    "humid": "manual",
                    "humidifier": "on",
                },
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

    async def update_fan(
        self, system_serial: str, zone_id: str, activity_type: ActivityTypes, fan_mode: FanModes
    ) -> dict[str, Any]:
        """Update the fan mode for a zone activity.

        Args:
            system_serial: Serial number of the system to update.
            zone_id: Carrier zone identifier.
            activity_type: Activity whose fan mode should be changed.
            fan_mode: Requested fan mode.

        Returns:
            The decoded mutation response.

        Raises:
            ValueError: If ``fan_mode`` or ``activity_type`` is not a valid enum
                member.
        """
        if fan_mode not in FanModes:
            raise ValueError(f"{fan_mode} is not a valid fan mode")
        if activity_type not in ActivityTypes:
            raise ValueError(f"{activity_type} is not a valid activity type")
        variables = {
            "input": {
                "serial": system_serial,
                "zoneId": zone_id,
                "activityType": activity_type.value,
                "fan": fan_mode.value,
            }
        }
        return await self._update_infinity_zone_activity(variables=variables)

    async def set_config_hold(
        self,
        system_serial: str,
        zone_id: str,
        activity_type: ActivityTypes,
        hold_until: str | None = None,
    ) -> dict[str, Any]:
        """Place a zone on hold for a selected activity.

        Args:
            system_serial: Serial number of the system to update.
            zone_id: Carrier zone identifier.
            activity_type: Activity to hold.
            hold_until: Optional Carrier hold-until time string. ``None`` keeps
                the hold indefinite according to Carrier's API behavior.

        Returns:
            The decoded mutation response.

        Raises:
            ValueError: If ``activity_type`` is not a valid enum member.
        """
        if activity_type not in ActivityTypes:
            raise ValueError(f"{activity_type} is not a valid activity type")
        variables = {
            "input": {
                "serial": system_serial,
                "zoneId": zone_id,
                "hold": "on",
                "holdActivity": activity_type.value,
                "otmr": hold_until,
            }
        }
        return await self._update_infinity_zone_config(variables=variables)

    async def resume_schedule(self, system_serial: str, zone_id: str) -> dict[str, Any]:
        """Clear a zone hold and resume its programmed schedule.

        Args:
            system_serial: Serial number of the system to update.
            zone_id: Carrier zone identifier.

        Returns:
            The decoded mutation response.
        """
        variables = {
            "input": {
                "serial": system_serial,
                "zoneId": zone_id,
                "hold": "off",
                "holdActivity": None,
                "otmr": None,
            }
        }
        return await self._update_infinity_zone_config(variables=variables)

    async def set_config_manual_activity(
        self,
        system_serial: str,
        zone_id: str,
        heat_set_point: str,
        cool_set_point: str,
        fan_mode: FanModes | None = None,
    ) -> dict[str, Any]:
        """Update a zone's manual activity set points and optional fan mode.

        Args:
            system_serial: Serial number of the system to update.
            zone_id: Carrier zone identifier.
            heat_set_point: Requested heat set point as Carrier expects it.
            cool_set_point: Requested cool set point as Carrier expects it.
            fan_mode: Optional fan mode to include in the manual activity update.

        Returns:
            The decoded mutation response.

        Raises:
            ValueError: If ``fan_mode`` is supplied and is not a valid enum
                member.
        """
        variables = {
            "input": {
                "serial": system_serial,
                "zoneId": zone_id,
                "activityType": "manual",
                "clsp": cool_set_point,
                "htsp": heat_set_point,
            }
        }
        if fan_mode is not None:
            if fan_mode not in FanModes:
                raise ValueError(f"{fan_mode} is not a valid fan mode")
            variables["input"]["fan"] = fan_mode.value
        return await self._update_infinity_zone_activity(variables=variables)
