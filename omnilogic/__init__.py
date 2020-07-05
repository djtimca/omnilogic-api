import time
import json
import xmltodict
import collections
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement, Comment, tostring
import asyncio
import logging
import config
import aiohttp

HAYWARD_API_URL = "https://app1.haywardomnilogic.com/HAAPI/HomeAutomation/API.ashx"
# CONNECT_PARAMS = [
#     UserName = "",
#     Password = ""
# ]

# get_msp_config_file = {}
_LOGGER = logging.getLogger("omnilogic")


class OmniLogic:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.systemid = None
        self.userid = None
        self.token = None
        self.verbose = True
        self.logged_in = False
        self.retry = 5
        self._session = aiohttp.ClientSession()

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

        for k, v in params.items():
            datatype = ""

            if type(v) == int:
                datatype = "int"
            elif type(v) == str:
                datatype = "string"
            elif type(v) == bool:
                datatype = "bool"
            else:
                _LOGGER.info("Couldn't determine datatype, exiting.")
                # print("Couldn't determine datatype, exiting.")
                return None

            param = SubElement(paramTag, "Parameter", name=k, dataType=datatype)
            param.text = str(v)

        requestXML = ElementTree.tostring(req).decode()
        # print("\n" + requestXML + "\n")
        return requestXML

    async def call_api(self, methodName, params):
        """
        Generic method to call API.
        """
        payload = self.buildRequest(methodName, params)
        # headers = {
        #     "content-type": "text/xml",
        #     "cache-control": "no-cache",
        # }
        
        async with self._session.post(HAYWARD_API_URL, data=payload) as resp:
            response = await resp.text()
        responseXML = ElementTree.fromstring(response)

        """ ### GetMspConfigFile/Telemetry do not return a successfull status, having to catch it a different way :thumbsdown: """
        if methodName == "GetMspConfigFile" and "MSPConfig" in response:
            return response

        if methodName == "GetTelemetryData" and "Backyard systemId" in response:
            # print(responseXML.text)
            return response
        """ ######################## """

        if int(responseXML.find("./Parameters/Parameter[@name='Status']").text) != 0:
            self.request_statusmessage = responseXML.find(
                "./Parameters/Parameter[@name='StatusMessage']"
            ).text
            raise ValueError(self.request_statusmessage)

        return response

    async def _get_token(self):

        params = {"UserName": self.username, "Password": self.password}

        response = await self.call_api("Login", params)
        root = ElementTree.fromstring(response)
        userid = root[1][2].text
        token = root[1][3].text
        # await self.close()
        return {"token": token, "userid": userid}

    async def _get_new_token(self):
      return await self._get_token()

    async def authenticate(self):

        if not self.token:
            response = await self._get_new_token()
            self.token = response['token']
            self.userid = response['userid']

    async def connect(self):
        """
        Connect to the omnilogic API and if successful, return 
        token and user id from the xml response
        """
        assert self.username != "", "Username not provided"
        assert self.password != "", "password not provided"

        await self.authenticate()

        if self.token is None:
            return False

        self.logged_in = True
        return self.token, self.userid

    async def get_site_list(self):
        assert self.token != "", "No login token"

        params = {"Token": self.token, "UserID": self.userid}

        response = await self.call_api("GetSiteList", params)
        responseXML = ElementTree.fromstring(response)
        self.systemid = int(
            responseXML.find(
                "./Parameters/Parameter/Item/Property[@name='MspSystemID']"
            ).text
        )

        return self.systemid

    async def get_msp_config_file(self):
        if self.token is None:
            await self.connect()
        if self.systemid is None:
            await self.get_site_list()
        assert self.token != "", "No login token"
        assert self.systemid != "", "No MSP id"

        params = {"Token": self.token, "MspSystemID": self.systemid, "Version": "0"}

        mspconfig = await self.call_api("GetMspConfigFile", params)

        return self.convert_to_json(mspconfig)

    async def get_BOWS(self):
        if self.token is None:
            await self.connect()
        if self.systemid is None:
            await self.get_site_list()
        assert self.token != "", "No login token"
        assert self.systemid != "", "No MSP id"

        params = {"Token": self.token, "MspSystemID": self.systemid, "Version": "0"}

        mspconfig = await self.call_api("GetMspConfigFile", params)

        config_data = self.convert_to_json(mspconfig)

        if isinstance(config_data['Backyard']['Body-of-water'], list):
            BOWS = config_data['Backyard']['Body-of-water']
        else:
            BOWS = []
            BOWS.append(config_data['Backyard']['Body-of-water'])

        return BOWS

    async def get_alarm_list(self):
        if self.token is None:
            await self.connect()
        if self.systemid is None:
            await self.get_site_list()
        assert self.token != "", "No login token"
        assert self.systemid != "", "No MSP id"

        params = {"Token": self.token, "MspSystemID": self.systemid, "Version": "0"}

        mspconfig = await self.call_api("GetAlarmList", params)
    
        return self.alarms_to_json(mspconfig)

    async def set_heater_onoff(self, PoolID, HeaterID, HeaterEnable):
        if self.token is None:
            await self.connect()
        if self.systemid is None:
            await self.get_site_list()
        assert self.token != "", "No login token"
        assert self.systemid != "", "No MSP id"

        params = {"Token": self.token, "MspSystemID": self.systemid, "Version": "0", "PoolID": PoolID, "HeaterID": HeaterID, "Enabled": HeaterEnable}

        response = await self.call_api("SetHeaterEnable", params)
        responseXML = ElementTree.fromstring(response)
        
        success = False

        if int(responseXML.find("./Parameters/Parameter[@name='Status']").text) == 0:
            success = True

        return success

    async def set_heater_temperature(self, PoolID, HeaterID, Temperature):
        if self.token is None:
            await self.connect()
        if self.systemid is None:
            await self.get_site_list()
        assert self.token != "", "No login token"
        assert self.systemid != "", "No MSP id"

        params = {"Token": self.token, "MspSystemID": self.systemid, "Version": "0", "PoolID": PoolID, "HeaterID": HeaterID, "Temp": Temperature}

        response = await self.call_api("SetUIHeaterCmd", params)
        responseXML = ElementTree.fromstring(response)
        
        success = False

        if int(responseXML.find("./Parameters/Parameter[@name='Status']").text) == 0:
            success = True

        return success

    async def set_pump_speed(self, PoolID, PumpID, Speed):
        if self.token is None:
            await self.connect()
        if self.systemid is None:
            await self.get_site_list()
        assert self.token != "", "No login token"
        assert self.systemid != "", "No MSP id"

        params = {"Token": self.token, "MspSystemID": self.systemid, "Version": "0", "PoolID": PoolID, "EquipmentID": PumpID, "IsOn": Speed, "IsCountDownTimer": False, "StartTimeHours": 0, "StartTimeMinutes": 0, "EndTimeHours": 0, "EndTimeMinutes": 0, "DaysActive": 0, "Recurring": False}

        response = await self.call_api("SetUIEquipmentCmd", params)
        responseXML = ElementTree.fromstring(response)
        
        success = False

        if int(responseXML.find("./Parameters/Parameter[@name='Status']").text) == 0:
            success = True

        return success

    async def set_relay_valve(self, PoolID, EquipmentID, OnOff):
        if self.token is None:
            await self.connect()
        if self.systemid is None:
            await self.get_site_list()
        assert self.token != "", "No login token"
        assert self.systemid != "", "No MSP id"

        params = {"Token": self.token, "MspSystemID": self.systemid, "Version": "0", "PoolID": PoolID, "EquipmentID": EquipmentID, "IsOn": OnOff, "IsCountDownTimer": False, "StartTimeHours": 0, "StartTimeMinutes": 0, "EndTimeHours": 0, "EndTimeMinutes": 0, "DaysActive": 0, "Recurring": False}

        response = await self.call_api("SetUIEquipmentCmd", params)
        responseXML = ElementTree.fromstring(response)
        
        success = False

        if int(responseXML.find("./Parameters/Parameter[@name='Status']").text) == 0:
            success = True

        return success

    async def set_spillover_speed(self, PoolID, Speed):
        if self.token is None:
            await self.connect()
        if self.systemid is None:
            await self.get_site_list()
        assert self.token != "", "No login token"
        assert self.systemid != "", "No MSP id"

        params = {"Token": self.token, "MspSystemID": self.systemid, "Version": "0", "PoolID": PoolID, "Speed": Speed, "IsCountDownTimer": False, "StartTimeHours": 0, "StartTimeMinutes": 0, "EndTimeHours": 0, "EndTimeMinutes": 0, "DaysActive": 0, "Recurring": False}

        response = await self.call_api("SetUISpilloverCmd", params)
        responseXML = ElementTree.fromstring(response)
        
        success = False

        if int(responseXML.find("./Parameters/Parameter[@name='Status']").text) == 0:
            success = True

        return success

    async def set_superchlorination(self, PoolID, ChlorID, IsOn):
        if self.token is None:
            await self.connect()
        if self.systemid is None:
            await self.get_site_list()
        assert self.token != "", "No login token"
        assert self.systemid != "", "No MSP id"

        params = {"Token": self.token, "MspSystemID": self.systemid, "Version": "0", "PoolID": PoolID, "ChlorID": ChlorID, "IsOn": IsOn}

        response = await self.call_api("SetUISuperCHLORCmd", params)
        responseXML = ElementTree.fromstring(response)
        
        success = False

        if int(responseXML.find("./Parameters/Parameter[@name='Status']").text) == 0:
            success = True

        return success

    async def set_lightshow(self, PoolID, LightID, ShowID):
        if self.token is None:
            await self.connect()
        if self.systemid is None:
            await self.get_site_list()
        assert self.token != "", "No login token"
        assert self.systemid != "", "No MSP id"

        params = {"Token": self.token, "MspSystemID": self.systemid, "Version": "0", "PoolID": PoolID, "LightID": LightID, "Show": ShowID, "IsCountDownTimer": False, "StartTimeHours": 0, "StartTimeMinutes": 0, "EndTimeHours": 0, "EndTimeMinutes": 0, "DaysActive": 0, "Recurring": False}

        response = await self.call_api("SetStandAloneLightShow", params)
        responseXML = ElementTree.fromstring(response)
        
        success = False

        if int(responseXML.find("./Parameters/Parameter[@name='Status']").text) == 0:
            success = True

        return success

    async def set_lightshowv2(self, PoolID, LightID, ShowID, Speed, Brightness):
        if self.token is None:
            await self.connect()
        if self.systemid is None:
            await self.get_site_list()
        assert self.token != "", "No login token"
        assert self.systemid != "", "No MSP id"

        params = {"Token": self.token, "MspSystemID": self.systemid, "Version": "0", "PoolID": PoolID, "LightID": LightID, "Show": ShowID, "Speed":Speed, "Brightness": Brightness, "IsCountDownTimer": False, "StartTimeHours": 0, "StartTimeMinutes": 0, "EndTimeHours": 0, "EndTimeMinutes": 0, "DaysActive": 0, "Recurring": False}

        response = await self.call_api("SetStandAloneLightShowV2", params)
        responseXML = ElementTree.fromstring(response)
        
        success = False

        if int(responseXML.find("./Parameters/Parameter[@name='Status']").text) == 0:
            success = True

        return success

    def alarms_to_json(self, alarms):
        alarmsXML = ElementTree.fromstring(alarms)
        alarmslist = []
        
        for child in alarmsXML:
            if child.tag == "Parameters":
                for params in child:
                    if params.get('name') == "List":
                        for alarmitem in params:
                            thisalarm = {}
                            
                            for alarmline in alarmitem:
                                thisalarm[alarmline.get('name')] = alarmline.text
                            
                            alarmslist.append(thisalarm)
        
        if len(alarmslist) == 0:
            thisalarm = {}
            thisalarm["BowID"] = 'False'
            
            alarmslist.append(thisalarm)
        
        return alarmslist

    def telemetry_to_json(self, telemetry):
        telemetryXML = ElementTree.fromstring(telemetry)
        backyard = {}
        BOWname = ""

        for child in telemetryXML:
            if "version" in child.attrib:
                continue

            elif child.tag == "Backyard":
                backyard["Backyard"] = child.attrib

            elif child.tag == "BodyOfWater":
                BOWname = "BOW" + str(child.attrib["systemId"])
                backyard["Backyard"][BOWname] = child.attrib

            else:
                backyard["Backyard"][BOWname][child.tag] = child.attrib
        """ my_dict=xmltodict.parse(telemetry)
        json_data=json.dumps(my_dict)
        #print(json_data)

        return json_data """

        return backyard

    async def get_telemetry_data(self):
        if self.token is None:
            await self.connect()
        if self.systemid is None:
            await self.get_site_list()

        # assert self.token != "", "No login token"

        params = {"Token": self.token, "MspSystemID": self.systemid}

        telem = await self.call_api("GetTelemetryData", params)
        return self.telemetry_to_json(telem)

    # def get_alarm_list(self):

    def convert_to_json(self,xmlString):
        my_dict=xmltodict.parse(xmlString)
        json_data=json.dumps(my_dict)
        #print(json_data)

        return json.loads(json_data)['Response']['MSPConfig']

    def set_equipment(self, poolId, equipmentId, isOn):
        params = [
            {"Token": self.token},
            {"MspSystemID": self.systemid},
            {"PoolID": poolId},
            {"EquipmentID": equipmentId},
            {"IsOn": isOn},
            {"IsCountDownTimer": False},
            {"StartTimeHours": 0},
            {"StartTimeMinutes": 0},
            {"EndTimeHours": 0},
            {"EndTimeMinutes": 0},
            {"DaysActive": 0},
            {"Recurring": False},
        ]

        self.call_api("SetUIEquipmentCmd", params)

