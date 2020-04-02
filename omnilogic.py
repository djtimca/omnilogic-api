import time
import json
import requests
import xmltodict
import collections
from xml.etree import ElementTree


class OmniLogic:
    def __init__(self, username, password, systemid):
        self.username = username
        self.password = password
        self.systemid = systemid
        self.verbose = True
        self.logged_in = False

    def connect(self):
        connect_response = self.call_api("login")

        if connect_response is None:
            return False

        self.token = self.get_login_token(connect_response)
        if self.token is None:
            return False

        self.logged_in = True

        return None  ### REMOVE ###
        # return self.get_status()

    def get_status(self):
        get_status_response = self.call_api("status")

        if get_status_response is None:
            return False

        self.current_status = get_status_response

        return None

    def call_api(self, request_type, format_params=None):
        url = "https://app1.haywardomnilogic.com/HAAPI/HomeAutomation/API.ashx"
        if request_type == "login":
            request_xml = """<?xml version="1.0" encoding="UTF-8"?>
                             <Request>
                             <Name>Login</Name>
                             <Parameters>
                               <Parameter name="UserName" dataType="string">{username}</Parameter>
                               <Parameter name="Password" dataType="string">{password}</Parameter>
                             </Parameters>
                             </Request>""".format(
                username=self.username, password=self.password
            )
        if request_type == "status":
            request_xml = """<?xml version="1.0" encoding="utf-8"?>
                            <Request>
                            <Name>GetTelemetryData</Name>
                            <Parameters>
                              <Parameter name="Token" dataType="String">{token}</Parameter>
                              <Parameter name="MspSystemID" dataType="String">{systemid}</Parameter>
                            </Parameters>
                            </Request>
                            """.format(
                token=self.token, systemid=self.systemid
            )

        # if self.logged_in:
        #     format_params["token"] = self.token

        if self.verbose:
            print(request_xml)

        r = requests.post(url, data=request_xml)

        if self.verbose:
            print(request_type + ": " + r.text)

        if "xml version" in r.text:
            fixed_output = r.text[38:].lower()
            print("xml found" + fixed_output)
        else:
            fixed_output = r.text.lower()
            print("no xml found" + fixed_output)

        if "You haven" in fixed_output:
            return None

        return xmltodict.parse(fixed_output)

    def get_login_token(self, response):

        lines = response["response"]["parameters"]["parameter"]

        for line in lines:
            if line["@name"] == "token":
                return line["#text"]

        return None
