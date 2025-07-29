import time
import json
import xmltodict
import collections
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement, Comment, tostring
from enum import Enum
import asyncio
import logging
from datetime import datetime, timedelta

import aiohttp

HAYWARD_API_URL = "https://www.haywardomnilogic.com/HAAPI/HomeAutomation/API.ashx"
HAYWARD_AUTH_URL = "https://services-gamma.haywardcloud.net/auth-service/v2/login"
HAYWARD_REFRESH_URL = "https://services-gamma.haywardcloud.net/auth-service/v2/refresh"
HAYWARD_APP_ID = "tzwqg83jvkyurxblidnepmachs"

_LOGGER = logging.getLogger("omnilogic")

class OmniLogic:
    def __init__(self, username, password, session:aiohttp.ClientSession = None):
        self.username = username
        self.password = password
        self.systemid = None
        self.systemname = None
        self.userid = None
        self.token = None
        self.refresh_token = None
        self.token_expiry = None
        self.verbose = True
        self.logged_in = False
        self.retry = 5
        if session is None:
            self._session = aiohttp.ClientSession()
        else:
            self._session = session
            
        self.systems = []

    async def close(self):
        await self._session.close()

    def buildRequest(self, requestName, params):
        """ Generate the XML object required for each API call
        Args:
            requestName (str): Passing the param of the request, ex: Login, GetMspConfig, etc.
            params (dict): Differing requirements based on requestName
        Returns:
            XML object that will be sent to the API
        Raises:
            TBD
        """

        req = Element("Request")
        reqName = SubElement(req, "Name")
        reqName.text = requestName
        paramTag = SubElement(req, "Parameters")

        # Special handling for SetCHLORParams - manually construct XML to match manufacturer format
        if requestName == "SetCHLORParams":
            # Build XML manually to ensure proper opening/closing tags for empty values
            xml_parts = ['<?xml version="1.0" encoding="utf-8"?>', '<Request>', '<Name>SetCHLORParams</Name>', '<Parameters>']
            
            # Define parameter order and types - API actually requires MspSystemID despite manufacturer feedback
            # Note: Hayward has a typo in their API - they expect "ORPTimout" (missing 'e')
            param_order = [
                ("MspSystemID", "int"),
                ("PoolID", "int"), 
                ("ChlorID", "int"),
                ("CfgState", "byte"),
                ("OpMode", "byte"),
                ("BOWType", "byte"),
                ("CellType", "byte"),
                ("TimedPercent", "byte"),
                ("SCTimeout", "byte"),
                ("ORPTimout", "byte")  # Hayward's typo - missing 'e'
            ]
            
            for param_name, data_type in param_order:
                if param_name in params and param_name != "Token":
                    value = params[param_name]
                    if value is not None and str(value) != "":
                        xml_parts.append(f'            <Parameter name="{param_name}" dataType="{data_type}">{value}</Parameter>')
                    else:
                        # Handle None values with consistent defaults for missing MSP config values
                        if param_name in ["SCTimeout", "ORPTimout"]:  # Note: ORPTimout is Hayward's typo
                            default_value = 4  # 4 hours default for both timeout parameters
                            xml_parts.append(f'            <Parameter name="{param_name}" dataType="{data_type}">{default_value}</Parameter>')
                            _LOGGER.info(f"Using default for {param_name}: {default_value} hours (MSP config value was None)")
                        else:
                            # Skip other parameters with empty/None values
                            _LOGGER.warning(f"Skipping parameter {param_name} with empty value: {value}")
            
            xml_parts.extend(['</Parameters>', '</Request>'])
            requestXML = '\n'.join(xml_parts)
            
            # Debug logging for SetCHLORParams
            _LOGGER.info(f"Generated XML for {requestName}:")
            _LOGGER.info(requestXML)
            return requestXML
        else:
            # Standard parameter handling for other API calls
            for k, v in params.items():
                datatype = ""

                if type(v) == int:
                    datatype = "int"
                elif type(v) == str:
                    datatype = "string"
                elif type(v) == bool:
                    datatype = "bool"
                else:
                    _LOGGER.info(f"Couldn't determine datatype for parameter '{k}' with value '{v}' (type: {type(v)}), exiting.")
                    # print("Couldn't determine datatype, exiting.")
                    return None

                if str(k) != "Token":
                    param = SubElement(paramTag, "Parameter", name=k, dataType=datatype)
                    param.text = str(v)

        requestXML = ElementTree.tostring(req).decode()
        # Debug logging for SetCHLORParams
        if requestName == "SetCHLORParams":
            _LOGGER.info(f"Generated XML for {requestName}:")
            _LOGGER.info(requestXML)
        return requestXML

    async def call_api(self, methodName, params):
        """
        Generic method to call API.
        """
        # Check if authentication is needed
        if self.token and self.token_expiry and datetime.now() >= self.token_expiry:
            await self.authenticate()
            
        payload = self.buildRequest(methodName, params)

        headers = {
            "content-type": "text/xml",
            "cache-control": "no-cache",
        }

        if self.token:
            headers["Token"] = self.token
            if "MspSystemID" in params:
                headers["SiteID"] = str(params["MspSystemID"])
            elif methodName == "SetCHLORParams":
                # Special case: SetCHLORParams needs MspSystemID in header but not in parameters
                if self.systems and len(self.systems) > 0:
                    headers["SiteID"] = str(self.systems[0]["MspSystemID"])
                    _LOGGER.debug(f"SetCHLORParams: Added SiteID {self.systems[0]['MspSystemID']} to header")
                else:
                    _LOGGER.error("SetCHLORParams: No systems available for SiteID header")

        async with self._session.post(
            HAYWARD_API_URL, data=payload, headers=headers
        ) as resp:
            try:
                response = await resp.text()
            except aiohttp.ClientConnectorError as e:
                raise LoginException(e)

        responseXML = ElementTree.fromstring(response)

        """ ### GetMspConfigFile/Telemetry do not return a successfull status, having to catch it a different way :thumbsdown: """
        if methodName == "GetMspConfigFile" and "MSPConfig" in response:
            return response

        if methodName == "GetTelemetryData" and "Backyard systemId" in response:
            # print(responseXML.text)
            return response
        """ ######################## """

        if methodName == "Login" and "There is no information" in response:
            # login invalid
            # response = {"Error":"Failed login"}
            raise LoginException("Failed Login: Bad username or password")

        if int(responseXML.find("./Parameters/Parameter[@name='Status']").text) != 0:
            self.request_statusmessage = responseXML.find(
                "./Parameters/Parameter[@name='StatusMessage']"
            ).text
            # raise ValueError(self.request_statusmessage)
            response = self.request_statusmessage

        return response

    async def _get_token(self):
        """ Get a new authentication token using the new auth endpoint """
        headers = {
            "Content-Type": "application/json",
            "X-HAYWARD-APP-ID": HAYWARD_APP_ID
        }
        
        payload = {
            "email": self.username,
            "password": self.password
        }
        
        _LOGGER.debug(f"Authenticating with URL: {HAYWARD_AUTH_URL}")
        _LOGGER.debug(f"Using headers: {headers}")
        _LOGGER.debug(f"Using payload structure: {list(payload.keys())}")
        
        try:
            async with self._session.post(
                HAYWARD_AUTH_URL, json=payload, headers=headers
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    _LOGGER.error(f"Authentication failed with status {resp.status}")
                    _LOGGER.error(f"Error details: {error_text}")
                    _LOGGER.error(f"Response headers: {resp.headers}")
                    _LOGGER.error(f"Request URL: {HAYWARD_AUTH_URL}")
                    _LOGGER.error(f"Request payload keys: {list(payload.keys())}")
                    _LOGGER.error(f"Using username/email: {self.username[:3]}...{self.username[-3:] if len(self.username) > 6 else ''}")
                    raise LoginException(f"Failed login: {resp.status}. Details: {error_text}")
                
                response = await resp.json()
                _LOGGER.debug(f"Authentication successful. Response keys: {list(response.keys())}")
                
                # Set token expiry to 24 hours from now (refresh daily)
                self.token_expiry = datetime.now() + timedelta(hours=24)
                
                # Debug the actual response structure
                _LOGGER.debug(f"Token value in response: {response.get('token')}, userID: {response.get('userID')}")
                
                return {
                    "token": response.get("token"),  # API returns 'token', not 'access_token'
                    "refresh_token": response.get("refreshToken"),  # API returns 'refreshToken'
                    "userid": response.get("userID")  # API returns 'userID'
                }
                
        except aiohttp.ClientConnectorError as e:
            raise LoginException(f"Connection error: {e}")

    async def _get_new_token(self):
        return await self._get_token()
        
    async def _refresh_token(self):
        """ Refresh the authentication token """
        if not self.refresh_token:
            # If no refresh token is available, get a new token instead
            return await self._get_token()
            
        headers = {
            "Content-Type": "application/json",
            "X-HAYWARD-APP-ID": HAYWARD_APP_ID
        }
        
        payload = {
            "refresh_token": self.refresh_token
        }
        
        try:
            async with self._session.post(
                HAYWARD_REFRESH_URL, json=payload, headers=headers
            ) as resp:
                if resp.status != 200:
                    _LOGGER.warning("Token refresh failed, getting new token")
                    # If refresh fails, fall back to getting a new token
                    return await self._get_token()
                
                response = await resp.json()
                
                # Set token expiry to 24 hours from now
                self.token_expiry = datetime.now() + timedelta(hours=24)
                
                return {
                    "token": response.get("access_token"),
                    "refresh_token": response.get("refresh_token"),
                    "userid": self.userid  # Keep the existing user ID
                }
                
        except aiohttp.ClientConnectorError as e:
            _LOGGER.error(f"Token refresh connection error: {e}")
            # If refresh fails with connection error, fall back to getting a new token
            return await self._get_token()

    async def authenticate(self):
        """ Authenticate or refresh token if needed """
        # Check if token needs refresh
        if self.token and self.token_expiry and datetime.now() < self.token_expiry:
            # Token is still valid, no action needed
            return
            
        # Get new token or refresh existing token
        if not self.token or not self.refresh_token:
            response = await self._get_new_token()
        else:
            response = await self._refresh_token()

        if response and "token" in response:
            self.token = response["token"]
            self.refresh_token = response.get("refresh_token")
            self.userid = response["userid"]
        else:
            self.token = None
            self.refresh_token = None
            self.userid = None

    async def connect(self):
        """
        Connect to the omnilogic API and if successful, return 
        token and user id from the xml response
        """
        # assert self.username != "", "Username not provided"
        # assert self.password != "", "password not provided"

        if self.username != "" and self.password != "":
            await self.authenticate()

            if self.token is None:
                return False

            self.logged_in = True

            return self.token, self.userid

    async def get_site_list(self):
        # assert self.token != "", "No login token"

        if self.token is not None:
            params = {"Token": self.token, "UserID": self.userid}

            response = await self.call_api("GetSiteList", params)

            if (
                "You don't have permission" in response
                or "The message format is wrong" in response
            ):
                self.systems = []
            else:
                responseXML = ElementTree.fromstring(response)
                for child in responseXML.findall("./Parameters/Parameter/Item"):
                    siteID = 0
                    siteName = ""
                    site = {}

                    for item in child:

                        if item.get("name") == "MspSystemID":
                            siteID = int(item.text)
                        elif item.get("name") == "BackyardName":
                            siteName = str(item.text)

                    site["MspSystemID"] = siteID
                    site["BackyardName"] = siteName

                    self.systems.append(site)

        return self.systems

    async def get_msp_config_file(self):
        if self.token is None:
            await self.connect()
        if len(self.systems) == 0:
            await self.get_site_list()

        mspconfig_list = []

        if len(self.systems) != 0 and self.token != "":
            for system in self.systems:
                params = {
                    "Token": self.token,
                    "MspSystemID": system["MspSystemID"],
                    "Version": 0,
                }

                mspconfig = await self.call_api("GetMspConfigFile", params)
            
                # Store raw MSP config XML for use by set_chlor_params method
                if not hasattr(self, 'msp_config') or not self.msp_config:
                    self.msp_config = mspconfig

                configitem = self.convert_to_json(mspconfig)
                configitem["MspSystemID"] = system["MspSystemID"]
                configitem["BackyardName"] = system["BackyardName"]

                relays = []
                if "Relay" in configitem["Backyard"]:
                    try:
                        for relay in configitem["Relay"]:
                            relays.append(relay)

                    except:
                        if isinstance(configitem["Backyard"]["Relay"], list):
                            relays = configitem["Backyard"]["Relay"]
                        else:
                            relays.append(configitem["Backyard"]["Relay"])

                configitem["Relays"] = relays

                BOW_list = []

                if type(configitem["Backyard"]["Body-of-water"]) == dict:
                    BOW = json.dumps(configitem["Backyard"]["Body-of-water"])

                    bow_relays = []
                    bow_lights = []
                    bow_heaters = []

                    if "Relay" in BOW:
                        try:
                            for relay in BOW["Relay"]:
                                bow_relays.append(relay)
                        except:
                            if isinstance(
                                configitem["Backyard"]["Body-of-water"]["Relay"], list
                            ):
                                bow_relays = configitem["Backyard"]["Body-of-water"][
                                    "Relay"
                                ]
                            else:
                                bow_relays.append(
                                    configitem["Backyard"]["Body-of-water"]["Relay"]
                                )

                    if "Heater" in BOW:
                        this_bow = json.loads(BOW)
                        if isinstance(this_bow["Heater"]["Operation"], list):
                            for heater in this_bow["Heater"]["Operation"]:
                                this_heater = {}
                                this_heater["Name"] = heater["Heater-Equipment"]["Name"]
                                this_heater["System-Id"] = this_bow["Heater"]["System-Id"]
                                this_heater["Shared-Type"] = this_bow["Heater"]["Shared-Type"]
                                this_heater["Enabled"] = this_bow["Heater"]["Enabled"]
                                this_heater["Current-Set-Point"] = this_bow["Heater"]["Current-Set-Point"]
                                this_heater["Max-Water-Temp"] = this_bow["Heater"]["Max-Water-Temp"]
                                this_heater["Min-Settable-Water-Temp"] = this_bow["Heater"]["Min-Settable-Water-Temp"]
                                this_heater["Max-Settable-Water-Temp"] = this_bow["Heater"]["Max-Settable-Water-Temp"]
                                this_heater["Operation"] = heater
                                bow_heaters.append(this_heater)
                        else:
                            bow_heaters.append(this_bow["Heater"])
                            
                        
                    if "ColorLogic-Light" in BOW:
                        try:
                            for light in BOW["ColorLogic-Light"]:
                                if "V2-Active" not in light:
                                    light["V2-Active"] = "no"
                                else:
                                    light["V2-Active"] = "yes"
                                bow_lights.append(light)
                        except:
                            if isinstance(
                                configitem["Backyard"]["Body-of-water"][
                                    "ColorLogic-Light"
                                ],
                                list,
                            ):
                                for light in configitem["Backyard"]["Body-of-water"][
                                    "ColorLogic-Light"
                                ]:
                                    if "V2-Active" not in light:
                                        light["V2-Active"] = "no"
                                    else:
                                        light["V2-Active"] = "yes"
                                    bow_lights.append(light)
                            else:
                                light = configitem["Backyard"]["Body-of-water"][
                                    "ColorLogic-Light"
                                ]
                                if "V2-Active" not in light:
                                    light["V2-Active"] = "no"
                                else:
                                    light["V2-Active"] = "yes"
                                bow_lights.append(light)

                    BOW = json.loads(BOW)
                    BOW["Relays"] = bow_relays
                    BOW["Lights"] = bow_lights
                    BOW["Heaters"] = bow_heaters

                    BOW_list.append(BOW)
                else:
                    for BOW in configitem["Backyard"]["Body-of-water"]:
                        bow_relays = []
                        bow_lights = []
                        bow_heaters = []

                        if "Relay" in BOW:
                            try:
                                for relay in BOW["Relay"]:
                                    if type(relay) == str:
                                        bow_relays.append(BOW["Relay"])
                                        break
                                    else:
                                        bow_relays.append(relay)
                            except:
                                bow_relays.append(BOW["Relay"])

                        if "Heater" in BOW:
                            if isinstance(BOW["Heater"]["Operation"], list):
                                for heater in BOW["Heater"]["Operation"]:
                                    this_heater = {}
                                    this_heater["Name"] = heater["Heater-Equipment"]["Name"]
                                    this_heater["System-Id"] = BOW["Heater"]["System-Id"]
                                    this_heater["Shared-Type"] = BOW["Heater"]["Shared-Type"]
                                    this_heater["Enabled"] = BOW["Heater"]["Enabled"]
                                    this_heater["Current-Set-Point"] = BOW["Heater"]["Current-Set-Point"]
                                    this_heater["Max-Water-Temp"] = BOW["Heater"]["Max-Water-Temp"]
                                    this_heater["Min-Settable-Water-Temp"] = BOW["Heater"]["Min-Settable-Water-Temp"]
                                    this_heater["Max-Settable-Water-Temp"] = BOW["Heater"]["Max-Settable-Water-Temp"]
                                    this_heater["Operation"] = heater
                                    bow_heaters.append(this_heater)
                            else:
                                bow_heaters.append(BOW["Heater"])
                        
                        if "ColorLogic-Light" in BOW:
                            try:
                                for light in BOW["ColorLogic-Light"]:
                                    if type(light) == str:
                                        this_light = BOW["ColorLogic-Light"]
                                        if "V2-Active" not in this_light:
                                            this_light["V2-Active"] = "no"
                                        else:
                                            this_light["V2-Active"] = "yes"
                                        bow_lights.append(this_light)
                                        break
                                    else:
                                        if "V2-Active" not in light:
                                            light["V2-Active"] = "no"
                                        else:
                                            light["V2-Active"] = "yes"
                                        bow_lights.append(light)
                            except:
                                bow_lights.append(BOW["ColorLogic-Light"])

                        BOW["Relays"] = bow_relays
                        BOW["Lights"] = bow_lights
                        BOW["Heaters"] = bow_heaters

                        BOW_list.append(BOW)

                configitem["Backyard"]["BOWS"] = BOW_list

                mspconfig_list.append(configitem)

            
            return mspconfig_list
        else:
            raise OmniLogicException("Failed getting MSP Config Data.")

    async def get_BOWS(self):
        # DEPRECATED - USE get_msp_config_data instead.
        if self.token is None:
            await self.connect()
        if self.systemid is None:
            await self.get_site_list()
        assert self.token != "", "No login token"
        assert self.systemid != "", "No MSP id"

        params = {"Token": self.token, "MspSystemID": self.systemid, "Version": "0"}

        mspconfig = await self.call_api("GetMspConfigFile", params)

        config_data = self.convert_to_json(mspconfig)

        if isinstance(config_data["Backyard"]["Body-of-water"], list):
            BOWS = config_data["Backyard"]["Body-of-water"]
        else:
            BOWS = []
            BOWS.append(config_data["Backyard"]["Body-of-water"])

        return BOWS

    async def get_alarm_list(self):
        if self.token is None:
            await self.connect()
        if len(self.systems) == 0:
            await self.get_site_list()

        alarmslist = []

        if len(self.systems) != 0 and self.token is not None:
            for system in self.systems:
                params = {
                    "Token": self.token,
                    "MspSystemID": system["MspSystemID"],
                    "Version": "0",
                }
                site_alarms = {}

                this_alarm = await self.call_api("GetAlarmList", params)

                site_alarms["Alarms"] = self.alarms_to_json(this_alarm)
                site_alarms["MspSystemID"] = system["MspSystemID"]
                site_alarms["BackyardName"] = system["BackyardName"]
                alarmslist.append(site_alarms)
        else:
            raise OmniLogicException("Failure getting alarms.")

        return alarmslist

    async def set_heater_onoff(self, MspSystemID, PoolID, HeaterID, HeaterEnable):
        if self.token is None:
            await self.connect()

        success = False

        if self.token is not None:
            params = {
                "Token": self.token,
                "MspSystemID": MspSystemID,
                "Version": "0",
                "PoolID": PoolID,
                "HeaterID": HeaterID,
                "Enabled": HeaterEnable,
            }

            response = await self.call_api("SetHeaterEnable", params)
            responseXML = ElementTree.fromstring(response)

            if (
                int(responseXML.find("./Parameters/Parameter[@name='Status']").text)
                == 0
            ):
                success = True

        return success

    async def set_heater_temperature(self, MspSystemID, PoolID, HeaterID, Temperature):
        if self.token is None:
            await self.connect()

        success = False

        if self.token is not None:
            params = {
                "Token": self.token,
                "MspSystemID": MspSystemID,
                "Version": "0",
                "PoolID": PoolID,
                "HeaterID": HeaterID,
                "Temp": Temperature,
            }

            response = await self.call_api("SetUIHeaterCmd", params)
            responseXML = ElementTree.fromstring(response)

            if (
                int(responseXML.find("./Parameters/Parameter[@name='Status']").text)
                == 0
            ):
                success = True

        return success

    async def set_pump_speed(self, MspSystemID, PoolID, PumpID, Speed):
        if self.token is None:
            await self.connect()

        success = False

        if self.token is not None:
            params = {
                "Token": self.token,
                "MspSystemID": MspSystemID,
                "Version": "0",
                "PoolID": PoolID,
                "EquipmentID": PumpID,
                "IsOn": Speed,
                "IsCountDownTimer": False,
                "StartTimeHours": 0,
                "StartTimeMinutes": 0,
                "EndTimeHours": 0,
                "EndTimeMinutes": 0,
                "DaysActive": 0,
                "Recurring": False,
            }

            response = await self.call_api("SetUIEquipmentCmd", params)
            responseXML = ElementTree.fromstring(response)

            if (
                int(responseXML.find("./Parameters/Parameter[@name='Status']").text)
                == 0
            ):
                success = True

        return success

    async def set_relay_valve(self, MspSystemID, PoolID, EquipmentID, OnOff):
        if self.token is None:
            await self.connect()

        success = False

        if self.token is not None:
            params = {
                "Token": self.token,
                "MspSystemID": MspSystemID,
                "Version": "0",
                "PoolID": PoolID,
                "EquipmentID": EquipmentID,
                "IsOn": OnOff,
                "IsCountDownTimer": False,
                "StartTimeHours": 0,
                "StartTimeMinutes": 0,
                "EndTimeHours": 0,
                "EndTimeMinutes": 0,
                "DaysActive": 0,
                "Recurring": False,
            }

            response = await self.call_api("SetUIEquipmentCmd", params)

            responseXML = ElementTree.fromstring(response)

            if (
                int(responseXML.find("./Parameters/Parameter[@name='Status']").text)
                == 0
            ):
                success = True

        return success

    async def set_spillover_speed(self, MspSystemID, PoolID, Speed):
        if self.token is None:
            await self.connect()

        success = False

        if self.token is not None:
            params = {
                "Token": self.token,
                "MspSystemID": MspSystemID,
                "Version": "0",
                "PoolID": PoolID,
                "Speed": Speed,
                "IsCountDownTimer": False,
                "StartTimeHours": 0,
                "StartTimeMinutes": 0,
                "EndTimeHours": 0,
                "EndTimeMinutes": 0,
                "DaysActive": 0,
                "Recurring": False,
            }

            response = await self.call_api("SetUISpilloverCmd", params)
            responseXML = ElementTree.fromstring(response)

            if (
                int(responseXML.find("./Parameters/Parameter[@name='Status']").text)
                == 0
            ):
                success = True

        return success

    async def set_superchlorination(self, MspSystemID, PoolID, ChlorID, IsOn):
        if self.token is None:
            await self.connect()

        success = False

        if self.token is not None:
            params = {
                "Token": self.token,
                "MspSystemID": MspSystemID,
                "Version": "0",
                "PoolID": PoolID,
                "ChlorID": ChlorID,
                "IsOn": IsOn,
            }

            response = await self.call_api("SetUISuperCHLORCmd", params)
            responseXML = ElementTree.fromstring(response)

            if (
                int(responseXML.find("./Parameters/Parameter[@name='Status']").text)
                == 0
            ):
                success = True

        return success

    async def set_lightshow(self, MspSystemID, PoolID, LightID, ShowID):
        if self.token is None:
            await self.connect()

        success = False

        if self.token is not None:
            params = {
                "Token": self.token,
                "MspSystemID": MspSystemID,
                "Version": "0",
                "PoolID": PoolID,
                "LightID": LightID,
                "Show": ShowID,
                "IsCountDownTimer": False,
                "StartTimeHours": 0,
                "StartTimeMinutes": 0,
                "EndTimeHours": 0,
                "EndTimeMinutes": 0,
                "DaysActive": 0,
                "Recurring": False,
            }

            response = await self.call_api("SetStandAloneLightShow", params)
            responseXML = ElementTree.fromstring(response)

            if (
                int(responseXML.find("./Parameters/Parameter[@name='Status']").text)
                == 0
            ):
                success = True

        return success

    async def set_lightshowv2(
        self, MspSystemID, PoolID, LightID, ShowID, Speed, Brightness
    ):
        if self.token is None:
            await self.connect()

        success = False

        if self.token is not None:
            params = {
                "Token": self.token,
                "MspSystemID": MspSystemID,
                "Version": "0",
                "PoolID": PoolID,
                "LightID": LightID,
                "Show": ShowID,
                "Speed": Speed,
                "Brightness": Brightness,
                "IsCountDownTimer": False,
                "StartTimeHours": 0,
                "StartTimeMinutes": 0,
                "EndTimeHours": 0,
                "EndTimeMinutes": 0,
                "DaysActive": 0,
                "Recurring": False,
            }

            response = await self.call_api("SetStandAloneLightShowV2", params)
            responseXML = ElementTree.fromstring(response)

            if (
                int(responseXML.find("./Parameters/Parameter[@name='Status']").text)
                == 0
            ):
                success = True

        return success

    def alarms_to_json(self, alarms):
        try:
            alarmsXML = ElementTree.fromstring(alarms)
        except:
            raise OmniLogicException("Error loading Hayward data.")
            
        alarmslist = []

        for child in alarmsXML:
            if child.tag == "Parameters":
                for params in child:
                    if params.get("name") == "List":
                        for alarmitem in params:
                            thisalarm = {}

                            for alarmline in alarmitem:
                                thisalarm[alarmline.get("name")] = alarmline.text

                            alarmslist.append(thisalarm)

        if len(alarmslist) == 0:
            thisalarm = {}
            thisalarm["BowID"] = "False"

            alarmslist.append(thisalarm)

        return alarmslist

    def telemetry_to_json(self, telemetry, config_data, site_alarms):
        try:
            telemetryXML = ElementTree.fromstring(telemetry)
        except:
            raise OmniLogicException("Error loading Hayward data.")

        backyard = {}

        BOW = {}

        backyard_list = []
        BOW_list = []
        relays = []
        bow_lights = []
        bow_relays = []
        bow_pumps = []
        bow_heaters = []
        bow_item = {}

        backyard_name = ""
        BOWname = ""

        if site_alarms[0].get("BowID") == "False":
            site_alarms = []

        for child in telemetryXML:
            if "version" in child.attrib:
                continue

            elif child.tag == "Backyard":
                if backyard_name == "":
                    backyard_name = "Backyard" + str(child.attrib["systemId"])
                    backyard = child.attrib
                else:
                    BOW["Lights"] = bow_lights
                    BOW["Relays"] = bow_relays
                    BOW["Pumps"] = bow_pumps
                    BOW["Heaters"] = bow_heaters
                    BOW_list.append(BOW)
                    backyard["BOWS"] = BOW_list
                    backyard_list.append(backyard)

                    backyard_name = "Backyard" + str(child.attrib["systemId"])
                    backyard = child.attrib
                    BOW_list = []
                    bow_lights = []
                    bow_relays = []
                    bow_pumps = []
                    bow_heaters = []
                    relays = []
                    BOWname = ""

            elif child.tag == "BodyOfWater":
                if BOWname == "":
                    backyard["Relays"] = relays
                    BOWname = "BOW" + str(child.attrib["systemId"])

                    for bow in config_data["Backyard"]["BOWS"]:
                        if child.attrib["systemId"] == bow["System-Id"]:
                            bow_item = bow
                    BOW = child.attrib
                else:
                    BOW["Lights"] = bow_lights
                    BOW["Relays"] = bow_relays
                    BOW["Pumps"] = bow_pumps
                    BOW["Heaters"] = bow_heaters

                    BOW_list.append(BOW)

                    BOW = {}
                    bow_lights = []
                    bow_relays = []
                    bow_pumps = []
                    bow_heaters = []

                    BOWname = "BOW" + str(child.attrib["systemId"])

                    for bow in config_data["Backyard"]["BOWS"]:
                        if child.attrib["systemId"] == bow["System-Id"]:
                            bow_item = bow

                    BOW = child.attrib
                BOW["Name"] = bow_item["Name"]
                BOW["Supports-Spillover"] = bow_item["Supports-Spillover"]

            elif child.tag == "Relay" and BOWname == "":
                this_relay = child.attrib
                for relay in config_data.get("Relays",[]):
                    if this_relay["systemId"] == relay["System-Id"]:
                        this_relay["Name"] = relay["Name"]
                        this_relay["Type"] = relay["Type"]
                        this_relay["Function"] = relay["Function"]
                        this_relay["Alarms"] = []
                    for alarm in site_alarms:
                        if alarm["EquipmentID"] == this_relay["systemId"]:
                            this_relay["Alarms"].append(alarm)

                relays.append(this_relay)

            elif child.tag == "ColorLogic-Light":
                this_light = child.attrib
                for light in bow_item.get("Lights",[]):
                    if this_light["systemId"] == light["System-Id"]:
                        this_light["Name"] = light["Name"]
                        this_light["Type"] = light["Type"]
                        this_light["V2"] = light["V2-Active"]
                        this_light["Alarms"] = []
                    for alarm in site_alarms:
                        if bow_item["System-Id"] == alarm["BowID"] and this_light["systemId"] == alarm["EquipmentID"]:
                            this_light["Alarms"].append(alarm)

                bow_lights.append(this_light)

            elif child.tag == "Relay":
                this_relay = child.attrib
                for relay in bow_item.get("Relays",[]):
                    if this_relay["systemId"] == relay["System-Id"]:
                        this_relay["Name"] = relay["Name"]
                        this_relay["Type"] = relay["Type"]
                        this_relay["Function"] = relay["Function"]
                        this_relay["Alarms"] = []
                    for alarm in site_alarms:
                        if bow_item["System-Id"] == alarm["BowID"] and this_relay["systemId"] == alarm["EquipmentID"]:
                            this_relay["Alarms"].append(alarm)

                bow_relays.append(this_relay)

            elif child.tag == "Chlorinator":
                this_chlorinator = child.attrib
                this_chlorinator["Name"] = bow_item["Chlorinator"]["Name"]
                this_chlorinator["Shared-Type"] = bow_item["Chlorinator"]["Shared-Type"]
                this_chlorinator["Operation"] = []
                this_chlorinator["Alarms"] = []

                if type(bow_item["Chlorinator"]["Operation"]) == dict:
                    this_chlorinator["Operation"].append(bow_item["Chlorinator"]["Operation"]["Chlorinator-Equipment"])
                    for alarm in site_alarms:
                        if bow_item["System-Id"] == alarm["BowID"] and this_chlorinator["systemId"] == alarm["EquipmentID"]:
                            this_chlorinator["Alarms"].append(alarm)
                else:
                    for equipment in bow_item["Chlorinator"]["Operation"]:
                        this_chlorinator["Operation"].append(equipment)
                        for alarm in site_alarms:
                            if bow_item["System-Id"] == alarm["BowID"] and this_chlorinator["systemId"] == alarm["EquipmentID"]:
                                this_chlorinator["Alarms"].append(alarm)

                BOW[child.tag] = this_chlorinator

            elif child.tag == "Filter":
                this_filter = child.attrib
                this_filter["Name"] = bow_item["Filter"]["Name"]
                this_filter["Shared-Type"] = bow_item["Filter"]["Shared-Type"]
                this_filter["Filter-Type"] = bow_item["Filter"]["Filter-Type"]
                this_filter["Max-Pump-Speed"] = bow_item["Filter"]["Max-Pump-Speed"]
                this_filter["Min-Pump-Speed"] = bow_item["Filter"]["Min-Pump-Speed"]
                this_filter["Max-Pump-RPM"] = bow_item["Filter"]["Max-Pump-RPM"]
                this_filter["Min-Pump-RPM"] = bow_item["Filter"]["Min-Pump-RPM"]
                this_filter["Priming-Enabled"] = bow_item["Filter"]["Priming-Enabled"]
                this_filter["Alarms"] = []

                for alarm in site_alarms:
                    if bow_item["System-Id"] == alarm["BowID"] and this_filter["systemId"] == alarm["EquipmentID"]:
                        this_filter["Alarms"].append(alarm)

                BOW[child.tag] = this_filter

            elif child.tag == "Pump":
                this_pump = child.attrib

                if type(bow_item["Pump"]) == dict:
                  this_pump["Name"] = bow_item["Pump"]["Name"]
                  this_pump["Type"] = bow_item["Pump"]["Type"]
                  this_pump["Function"] = bow_item["Pump"]["Function"]
                  this_pump["Min-Pump-Speed"] = bow_item["Pump"]["Min-Pump-Speed"]
                  this_pump["Max-Pump-Speed"] = bow_item["Pump"]["Max-Pump-Speed"]
                  this_pump["Alarms"] = []

                  for alarm in site_alarms:
                      if bow_item["System-Id"] == alarm["BowID"] and this_pump["systemId"] == alarm["EquipmentID"]:
                          this_pump["Alarms"].append(alarm)
                else:
                  for pump in bow_item["Pump"]:
                    #Find the right pump
                    if pump["System-Id"] == this_pump["systemId"]:
                      this_pump["Name"] = pump["Name"]
                      this_pump["Type"] = pump["Type"]
                      this_pump["Function"] = pump["Function"]
                      this_pump["Min-Pump-Speed"] = pump["Min-Pump-Speed"]
                      this_pump["Max-Pump_Speed"] = pump["Max-Pump-Speed"]
                      this_pump["Alarms"] = []
                      
                      for alarm in site_alarms:
                          if bow_item["System-Id"] == alarm["BowID"] and this_pump["systemId"] == alarm["EquipmentID"]:
                              this_pump["Alarms"].append(alarm)

                bow_pumps.append(this_pump)

            elif child.tag == "Heater":
                this_heater = child.attrib

                for heater in bow_item["Heaters"]:
                    if this_heater["systemId"] == heater["Operation"]["Heater-Equipment"]["System-Id"]:
                        this_heater["Shared-Type"] = heater["Shared-Type"]
                        this_heater["Operation"] = {}
                        this_heater["Operation"]["VirtualHeater"] = heater["Operation"]["Heater-Equipment"]
                        this_heater["Operation"]["VirtualHeater"]["Current-Set-Point"] = heater["Current-Set-Point"]
                        this_heater["Operation"]["VirtualHeater"]["Max-Water-Temp"] = heater["Max-Water-Temp"]
                        this_heater["Operation"]["VirtualHeater"]["Min-Settable-Water-Temp"] = heater["Min-Settable-Water-Temp"]
                        this_heater["Operation"]["VirtualHeater"]["Max-Settable-Water-Temp"] = heater["Max-Settable-Water-Temp"]
                        this_heater["Operation"]["VirtualHeater"]["enable"] = heater["Operation"]["Heater-Equipment"]["Enabled"]
                        this_heater["Operation"]["VirtualHeater"]["systemId"] = heater["System-Id"]
                        this_heater["systemId"] = heater["Operation"]["Heater-Equipment"]["System-Id"]
                        this_heater["Name"] = heater["Operation"]["Heater-Equipment"]["Name"]
                        this_heater["Alarms"] = []
                        for alarm in site_alarms:
                            if bow_item["System-Id"] == alarm["BowID"] and this_heater["systemId"] == alarm["EquipmentID"]:
                                this_heater["Alarms"].append(alarm)

                bow_heaters.append(this_heater)

                
                for alarm in site_alarms:
                    if bow_item["System-Id"] == alarm["BowID"] and this_heater["systemId"] == alarm["EquipmentID"]:
                        this_heater["Alarms"].append(alarm)

                BOW[child.tag] = this_heater

            elif child.tag == "CSAD":
                this_csad = child.attrib
                this_csad["Alarms"] = []

                for alarm in site_alarms:
                    if this_csad["systemId"] == alarm["EquipmentID"]:
                        this_csad["Alarms"].append(alarm)
                
                BOW[child.tag] = this_csad
                
            else:
                BOW[child.tag] = child.attrib

        BOW["Lights"] = bow_lights
        BOW["Relays"] = bow_relays
        BOW["Pumps"] = bow_pumps
        BOW["Heaters"] = bow_heaters
        BOW_list.append(BOW)

        backyard["BOWS"] = BOW_list

        backyard_list.append(backyard)

        return backyard

    async def get_telemetry_data(self):
        if self.token is None:
            _LOGGER.debug("Token is None, attempting to connect")
            result = await self.connect()
            if not result:
                _LOGGER.error("Failed to connect and obtain token")
                raise OmniLogicException("No authentication token available")
            _LOGGER.debug(f"Connection successful, token obtained: {self.token is not None}")
            
        if len(self.systems) == 0:
            _LOGGER.debug("No systems found, retrieving site list")
            await self.get_site_list()

        # assert self.token != "", "No login token"
        telem_list = []

        if self.token != "" and len(self.systems) != 0:
            try:
                _LOGGER.debug(f"Getting MSP config file for {len(self.systems)} systems")
                config_data = await self.get_msp_config_file()
                _LOGGER.debug(f"Successfully retrieved MSP config data")
                
                """
                f = open("mspconfig_" + self.username + ".txt", "w")
                f.write(str(config_data))
                f.close()
                """
                
                for system in self.systems:
                    try:
                        # Get the right instance of the ID for this system
                        config_item = {}
                        _LOGGER.debug(f"Processing system: {system['MspSystemID']} - {system.get('BackyardName', 'Unknown')}")

                        for sys_data in config_data:
                            if sys_data["MspSystemID"] == system["MspSystemID"]:
                                config_item = sys_data

                        if not config_item:
                            _LOGGER.warning(f"Could not find config data for system {system['MspSystemID']}")
                            continue

                        params = {"Token": self.token, "MspSystemID": system["MspSystemID"]}
                        _LOGGER.debug(f"Getting telemetry data for system {system['MspSystemID']}")

                        telem = await self.call_api("GetTelemetryData", params)
                        _LOGGER.debug(f"Successfully retrieved telemetry data for system {system['MspSystemID']}")
                        
                        params = {
                            "Token": self.token,
                            "MspSystemID": system["MspSystemID"],
                            "Version": "0",
                        }
                        _LOGGER.debug(f"Getting alarm list for system {system['MspSystemID']}")

                        this_alarm = await self.call_api("GetAlarmList", params)
                        _LOGGER.debug(f"Successfully retrieved alarm list for system {system['MspSystemID']}")

                        site_alarms = self.alarms_to_json(this_alarm)
                        _LOGGER.debug(f"Processed alarms: {len(site_alarms)} found")

                        if site_alarms[0].get("BowID") == "False":
                            site_alarms = []
                        
                        _LOGGER.debug(f"Converting telemetry to JSON for system {system['MspSystemID']}")
                        site_telem = self.telemetry_to_json(telem, config_item, self.alarms_to_json(this_alarm))
                        _LOGGER.debug(f"Successfully converted telemetry to JSON for system {system['MspSystemID']}")

                        site_telem["BackyardName"] = config_item["BackyardName"]
                        
                        try:
                            site_telem["Msp-Vsp-Speed-Format"] = config_item["System"]["Msp-Vsp-Speed-Format"]
                            site_telem["Msp-Time-Format"] = config_item["System"]["Msp-Time-Format"]
                            site_telem["Units"] = config_item["System"]["Units"]
                            site_telem["Msp-Chlor-Display"] = config_item["System"]["Msp-Chlor-Display"]
                            site_telem["Msp-Language"] = config_item["System"]["Msp-Language"]
                            site_telem["Unit-of-Measurement"] = config_item["System"]["Units"]
                            site_telem["Alarms"] = site_alarms
                        except KeyError as e:
                            _LOGGER.error(f"Missing key in system config: {e}")
                            _LOGGER.debug(f"Available system keys: {list(config_item.get('System', {}).keys())}")

                        try:
                            if "Sensor" in config_item["Backyard"]:
                                sensors = config_item["Backyard"]["Sensor"]
                                _LOGGER.debug("Found sensors in Backyard")
                            else:
                                if "Sensor" in config_item["Backyard"].get("Body-of-water", {}):
                                    sensors = config_item["Backyard"]["Body-of-water"]["Sensor"]
                                    _LOGGER.debug("Found sensors in Body-of-water")
                                else:
                                    sensors = {}
                                    _LOGGER.debug("No sensors found")

                            hasAirSensor = False

                            if type(sensors) == dict and sensors != {}:
                                site_telem["Unit-of-Temperature"] = sensors.get("Units","UNITS_FAHRENHEIT")

                                if sensors["Name"] == "AirSensor":
                                    hasAirSensor = True
                                    _LOGGER.debug("Found AirSensor")
                            else:
                                for sensor in sensors:
                                    if sensor["Name"] == "AirSensor":
                                        site_telem["Unit-of-Temperature"] = sensor.get("Units","UNITS_FAHRENHEIT")
                                        hasAirSensor = True
                                        _LOGGER.debug("Found AirSensor in sensor list")

                            if hasAirSensor == False:
                                if "airTemp" in site_telem:
                                    del site_telem["airTemp"]
                                    _LOGGER.debug("Removed airTemp as no AirSensor was found")
                        except KeyError as e:
                            _LOGGER.error(f"Error processing sensors: {e}")
                            _LOGGER.debug(f"Backyard keys: {list(config_item.get('Backyard', {}).keys())}")
                        
                        _LOGGER.debug(f"Adding telemetry for system {system['MspSystemID']} to results")
                        telem_list.append(site_telem)
                    except Exception as e:
                        _LOGGER.error(f"Error processing system {system['MspSystemID']}: {str(e)}")
                        _LOGGER.debug("Exception details", exc_info=True)
            except Exception as e:
                _LOGGER.error(f"Error getting telemetry data: {str(e)}")
                _LOGGER.debug("Exception details", exc_info=True)
                raise OmniLogicException(f"Failure getting telemetry: {str(e)}")

        else:
            if self.token is None:
                _LOGGER.error("Failed to get telemetry: No authentication token available")
                raise OmniLogicException("Failure getting telemetry: No authentication token")
            elif len(self.systems) == 0:
                _LOGGER.error("Failed to get telemetry: No systems found")
                raise OmniLogicException("Failure getting telemetry: No systems found")
            else:
                _LOGGER.error("Failed to get telemetry: Unknown reason")
                raise OmniLogicException("Failure getting telemetry.")

        """
        f = open("telemetry_" + self.username + ".txt", "w")
        f.write(str(telem_list))
        f.close()
        """

        return telem_list

    # def get_alarm_list(self):

    def convert_to_json(self, xmlString):
        try:
            my_dict = xmltodict.parse(xmlString)
            json_data = json.dumps(my_dict)
        except:
            raise OmniLogicException("Error converting Hayward data to JSON.")

        return json.loads(json_data)["Response"]["MSPConfig"]

    async def set_equipment(self, poolId, equipmentId, isOn):
        if self.token is None:
            await self.connect()
        if len(self.systems) == 0:
            await self.get_site_list()

        success = False

        if self.token is not None and len(self.systems) > 0:
            # Use the first system's ID (like other methods do)
            system_id = self.systems[0]["MspSystemID"]
            
            params = {
                "Token": self.token,
                "MspSystemID": system_id,
                "Version": "0",
                "PoolID": poolId,
                "EquipmentID": equipmentId,
                "IsOn": isOn,
                "IsCountDownTimer": False,
                "StartTimeHours": 0,
                "StartTimeMinutes": 0,
                "EndTimeHours": 0,
                "EndTimeMinutes": 0,
                "DaysActive": 0,
                "Recurring": False,
            }

            response = await self.call_api("SetUIEquipmentCmd", params)
            
            # Handle potential XML parsing errors
            try:
                responseXML = ElementTree.fromstring(response)
                if (
                    int(responseXML.find("./Parameters/Parameter[@name='Status']").text)
                    == 0
                ):
                    success = True
            except ElementTree.ParseError:
                # If response is not valid XML, it might be an error message
                # In this case, we'll consider it a failure
                success = False

        return success

    async def set_chlor_params(self, poolId, chlorId, cfgState=None, opMode=None, bowType=None, 
                              timedPercent=None, cellType=None, scTimeout=None, orpTimeout=None):
        """
        Set chlorinator parameters using the SetCHLORParams API call.
        Uses current chlorinator configuration from MSP config as defaults, with ability to override.
        
        Args:
            poolId (int): Pool ID
            chlorId (int): Chlorinator ID  
            cfgState (int, optional): Configuration state (2=Disable/Off, 3=Enable/On)
            opMode (int, optional): Operating mode (0=Not Configured, 1=Timed, 2=ORP Autosense)
            bowType (int, optional): Body of Water Type (0=Pool, 1=SPA)
            timedPercent (int, optional): Timed percentage [0-100]
            cellType (int, optional): Cell type (1=T-3, 2=T-5, 3=T-9, 4=T-15)
            scTimeout (int, optional): Superchlorinate timeout in hours [1-96]
            orpTimeout (int, optional): ORP timeout in hours [1-96]
            
        Returns:
            tuple: (success: bool, response: str) - success status and raw API response
        """
        if self.token is None:
            await self.connect()

        success = False
        response = ""

        if self.token is not None:
            # Ensure we have system data
            if not self.systems:
                await self.get_site_list()
            
            # Ensure we have MSP config data for parsing defaults
            if not hasattr(self, 'msp_config') or not self.msp_config:
                await self.get_msp_config_file()
            
            # Parse current chlorinator configuration as defaults
            current_config = self._parse_chlorinator_config(chlorId)
            _LOGGER.info(f"Parsed chlorinator config for ID {chlorId}: {current_config}")
            
            # Use provided values or fall back to current config - NO hard-coded defaults
            cfgState = cfgState if cfgState is not None else current_config["cfgState"]
            opMode = opMode if opMode is not None else current_config["opMode"]
            bowType = bowType if bowType is not None else current_config["bowType"]
            timedPercent = timedPercent if timedPercent is not None else current_config["timedPercent"]
            cellType = cellType if cellType is not None else current_config["cellType"]
            scTimeout = scTimeout if scTimeout is not None else current_config["scTimeout"]
            orpTimeout = orpTimeout if orpTimeout is not None else current_config["orpTimeout"]
            
            # Create parameters - include all parameters as per manufacturer sample
            # Note: Hayward API has typo - expects "ORPTimout" (missing 'e')
            params = {
                "Token": self.token,
                "MspSystemID": self.systems[0]["MspSystemID"],
                "PoolID": poolId,
                "ChlorID": chlorId,
                "CfgState": cfgState,
                "OpMode": opMode,
                "BOWType": bowType,
                "CellType": cellType,
                "TimedPercent": timedPercent,
                "SCTimeout": scTimeout,
                "ORPTimout": orpTimeout  # Hayward's typo - missing 'e'
            }

            response = await self.call_api("SetCHLORParams", params)
            
            # Handle potential XML parsing errors
            try:
                responseXML = ElementTree.fromstring(response)
                if (
                    int(responseXML.find("./Parameters/Parameter[@name='Status']").text)
                    == 0
                ):
                    success = True
            except ElementTree.ParseError:
                # If response is not valid XML, it might be an error message
                # In this case, we'll consider it a failure
                success = False

        return success, response

    def _parse_chlorinator_config(self, chlorId):
        """Parse chlorinator configuration from MSP config file."""
        if not self.msp_config:
            raise ValueError("MSP config not available - cannot determine chlorinator configuration. Call get_msp_config_file() first.")
        
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(self.msp_config)
            
            # Find the chlorinator with the specified ID
            chlorinator = None
            for chlor in root.findall(".//Chlorinator"):
                system_id_elem = chlor.find("System-Id")
                if system_id_elem is not None and int(system_id_elem.text) == chlorId:
                    chlorinator = chlor
                    break
            
            if not chlorinator:
                raise ValueError(f"Chlorinator with ID {chlorId} not found in MSP config - cannot determine configuration")
            
            # Parse configuration values
            config = {}
            
            # Enabled -> CfgState (yes=3, no=2)
            enabled = chlorinator.find("Enabled")
            config["cfgState"] = 3 if enabled is not None and enabled.text == "yes" else 2
            
            # Mode -> OpMode
            mode = chlorinator.find("Mode")
            if mode is not None:
                mode_text = mode.text
                if "NOT_CONFIGURED" in mode_text:
                    config["opMode"] = 0
                elif "TIMED" in mode_text:
                    config["opMode"] = 1
                elif "ORP_AUTO" in mode_text:
                    config["opMode"] = 2
                else:
                    config["opMode"] = 0
            else:
                config["opMode"] = 0
            
            # BOWType - find the pool/spa that contains this chlorinator
            # Look for Body-Of-Water that contains this chlorinator
            bow_type = 0  # Default to Pool
            for bow in root.findall(".//Body-Of-Water"):
                # Check if this chlorinator is in this body of water
                chlor_in_bow = bow.find(f".//Chlorinator[System-Id='{chlorId}']")
                if chlor_in_bow is not None:
                    type_elem = bow.find("Type")
                    if type_elem is not None:
                        if "BOW_POOL" in type_elem.text:
                            bow_type = 0
                        else:  # BOW_SPA or anything else
                            bow_type = 1
                    break
            config["bowType"] = bow_type
            
            # Cell-Type -> CellType
            cell_type = chlorinator.find("Cell-Type")
            if cell_type is not None:
                cell_text = cell_type.text
                if "T3" in cell_text:
                    config["cellType"] = 1
                elif "T5" in cell_text:
                    config["cellType"] = 2
                elif "T9" in cell_text:
                    config["cellType"] = 3
                elif "T15" in cell_text:
                    config["cellType"] = 4
                else:
                    config["cellType"] = 4  # Default to T-15
            else:
                config["cellType"] = 4  # Default to T-15
            
            # Timed-Percent -> TimedPercent
            timed_percent = chlorinator.find("Timed-Percent")
            config["timedPercent"] = int(timed_percent.text) if timed_percent is not None else 50
            
            # SuperChlor-Timeout -> SCTimeout (already in hours)
            sc_timeout = chlorinator.find("SuperChlor-Timeout")
            config["scTimeout"] = int(sc_timeout.text) if sc_timeout is not None else 5
            
            # ORP-Timeout -> ORPTimeout (convert from seconds to hours)
            orp_timeout = chlorinator.find("ORP-Timeout")
            if orp_timeout is not None:
                config["orpTimeout"] = int(int(orp_timeout.text) / 3600)  # Convert seconds to hours
            else:
                config["orpTimeout"] = None  # No default - use None if not found
            
            return config
            
        except Exception as e:
            _LOGGER.error(f"Error parsing chlorinator config: {e}")
            raise ValueError(f"Failed to parse chlorinator configuration from MSP config: {e}")

class LoginException(Exception):
    pass


class OmniLogicException(Exception):
    pass


class LightEffect(Enum):
    VOODOO_LOUNGE = "0"
    DEEP_BLUE_SEA = "1"
    ROYAL_BLUE = "2"
    AFTERNOON_SKY = "3"
    AQUA_GREEN = "4"
    EMERALD = "5"
    CLOUD_WHITE = "6"
    WARM_RED = "7"
    FLAMINGO = "8"
    VIVID_VIOLET = "9"
    SANGRIA = "10"
    TWILIGHT = "11"
    TRANQUILITY = "12"
    GEMSTONE = "13"
    USA = "14"
    MARDI_GRAS = "15"
    COOL_CABARET = "16"
    #### THESE SHOW IN THE APP AFTER SETTING, BUT MAY NOT MATCH ALL LIGHTS
    YELLOW = "17"
    ORANGE = "18"
    GOLD = "19"
    MINT = "20"
    TEAL = "21"
    BURNT_ORANGE = "22"
    PURE_WHITE = "23"
    CRISP_WHITE = "24"
    WARM_WHITE = "25"
    BRIGHT_YELLOW = "26"

