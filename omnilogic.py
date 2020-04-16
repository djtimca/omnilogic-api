import time
import json
import requests
from requests.exceptions import ConnectionError as ConnectError, HTTPError, Timeout
import xmltodict
import collections
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement, Comment, tostring
import asyncio
import logging

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
        self.token = "1d320b9beb934c2cb42dd8f79532fa8b"
        self.verbose = True
        self.logged_in = False
        self.retry = 5

    def buildRequest(self, requestName, params):
        """ Generate the XML object required for each API call

        Args:
            requestName (str): Passing the param of the request, ex: Login, GetMspConfig, etc.
            params (dict): Differing requirements based on requestName
        Returns:
            XML object that will be sent to the API
        Raises:
            None

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
        print("\n" + xml + "\n")
        return requestXML

    def call_api(self, methodName, params):
        """
        Generic method to call API.
        """
        payload = self.buildRequest(methodName, params)
        headers = {
            "content-type": "text/xml",
            "cache-control": "no-cache",
        }
        try:
            response = requests.request(
                "POST", HAYWARD_API_URL, data=payload, headers=headers
            )
            response.raise_for_status()

        except requests.exceptions.HTTPError as errh:
            print("Http Error: ", errh)
        except requests.exceptions.ConnectionError as errc:
            print("Error Connecting: ", errc)
        except requests.exceptions.Timeout as errt:
            print("Timeout Error: ", errt)
        except requests.exceptions.RequestException as err:
            print("Oops. Something Else: ", err)

        responseXML = ElementTree.fromstring(response.text)

        """ ### GetMspConfigFile/Telemetry do not return a successfull status, having to catch it a different way :thumbsdown: """
        if methodName == "GetMspConfigFile" and "MSPConfig" in response.text:
            return response.text

        if methodName == "GetTelemetryData" and "Backyard systemId" in response.text:
            # print(responseXML.text)
            return response.text
        """ ######################## """

        if int(responseXML.find("./Parameters/Parameter[@name='Status']").text) != 0:
            self.request_statusmessage = responseXML.find(
                "./Parameters/Parameter[@name='StatusMessage']"
            ).text
            raise ValueError(self.request_statusmessage)

        return response.text

    def connect(self):
        """
        Connect to the omnilogic API and if successful, return 
        token and user id from the xml response
        """
        # print(f"user: {self.username}")
        assert self.username != "", "Username not provided"
        assert self.password != "", "password not provided"

        params = {"UserName": self.username, "Password": self.password}

        try:
            response = self.call_api("Login", params)
        except:
            pass

        responseXML = ElementTree.fromstring(response)
        self.token = responseXML.find("./Parameters/Parameter[@name='Token']").text
        self.userid = int(
            responseXML.find("./Parameters/Parameter[@name='UserID']").text
        )

        if self.token is None:
            return False

        # self.logged_in = True
        return self.token, self.userid

    def get_site_list(self):
        assert self.token != "", "No login token"

        params = {"Token": self.token, "UserID": self.userid}

        response = self.call_api("GetSiteList", params)
        responseXML = ElementTree.fromstring(response)
        # print(response)
        self.systemid = int(
            responseXML.find(
                "./Parameters/Parameter/Item/Property[@name='MspSystemID']"
            ).text
        )

        return self.systemid

    def get_msp_config_file(self):
        assert self.token != "", "No login token"

        params = {"Token": self.token, "MspSystemID": self.systemid, "Version": "0"}

        return self.call_api("GetMspConfigFile", params)

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

        return backyard

    def get_telemetry_data(self):
        assert self.token != "", "No login token"

        params = {"Token": self.token, "MspSystemID": self.systemid}

        telem = self.call_api("GetTelemetryData", params)
        return self.telemetry_to_json(telem)

    # def get_alarm_list(self):

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
c = OmniLogic(username="", password="")
print(c.connect())
# print(c.get_telemetry_data())

print("\nToken: " + c.token)
print(c.get_site_list())

print("MSP CONFIG ##############\n\n")
config = c.get_msp_config_file()
print(config)
# print(c.returnJson(config))

print("Telemetry ###############\n\n")
telemetry = c.get_telemetry_data()
print(telemetry)
