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
        self.systemid = ""
        self.userid = ""
        self.token = ""
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
                print("Couldn't determine datatype, exiting.")
                return None

            param = SubElement(paramTag, "Parameter", name=k, dataType=datatype)
            param.text = str(v)

        requestXML = ElementTree.tostring(req).decode()
        print("\n" + requestXML + "\n")
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
        # print(response)
        self.systemid = int(
            responseXML.find(
                "./Parameters/Parameter/Item/Property[@name='MspSystemID']"
            ).text
        )

        return self.systemid

        # def msp_config_to_json(self, mspconfig):
        #     mspconfigXML = ElementTree.fromstring(mspconfig)

        #     mspconf = mspconfigXML.findall("./Response/MSPConfig/Backyard/...")
        #     print("MSP: ", mspconfig)
        #     print(type(mspconfig))

        # mspconfig = {}

        # for childs in mspconfigXML:
        #     # print(childs.tag)
        #     # print(type(childs))
        #     for child in childs:f
        #         if "version" in child.attrib:
        #             continue
        #         # print(type(child))

        #         # print("  ", child.tag, " ", child.attrib)
        #         for item in child:
        #             print(type(item))

        #             if item.attrib == {}:
        #                 for i in item:
        #                     print(i.tag, i.attrib)
        #             else:
        #                 print(item.tag, " ", item.attrib)

        #

        # return

    async def get_msp_config_file(self):
        assert self.token != "", "No login token"
        assert self.systemid != "", "No MSP id"

        params = {"Token": self.token, "MspSystemID": self.systemid, "Version": "0"}

        mspconfig = await self.call_api("GetMspConfigFile", params)
        return mspconfig
        # return self.msp_config_to_json(mspconfig)

    def telemetry_to_json(self, telemetry):
        telemetryXML = ElementTree.fromstring(telemetry)
        backyard = {}

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
        assert self.token != "", "No login token"

        params = {"Token": self.token, "MspSystemID": self.systemid}

        telem = await self.call_api("GetTelemetryData", params)
        return self.telemetry_to_json(telem)

    # def get_alarm_list(self):

    def convert_to_json(self,xmlString):
        my_dict=xmltodict.parse(xmlString)
        json_data=json.dumps(my_dict)
        #print(json_data)

        return json_data

    def set_filter(self, state):
        assert self.token != "", "No login token"

        if state == "on":
            speed = 80
        if state == "off":
            speed = 0

        params = [
            {"Token": self.token},
            {"MspSystemID": self.systemid},
            {"PoolID": 1},
            {"EquipmentID": 3},
            {"IsOn": speed},
            {"IsCountDownTimer": False},
            {"StartTimeHours": 0},
            {"StartTimeMinutes": 0},
            {"EndTimeHours": 0},
            {"EndTimeMinutes": 0},
            {"DaysActive": 0},
            {"Recurring": False},
        ]

        self.call_api("SetUIEquipmentCmd", params)


# put yo creds in to test
async def main():
    c = OmniLogic(username=config.username, password=config.password)
    user = await c.connect()
    print('User: ')
    print(user)
    site_list = await c.get_site_list()
    print('site_list')
    print(site_list)
    config_file = await c.get_msp_config_file()
    # print(config_file)
    json_data = c.convert_to_json(config_file)
    # print(json_data)
    t_data = await c.get_telemetry_data()
    print(t_data)

asyncio.run(main())