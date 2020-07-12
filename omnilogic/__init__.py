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
        self.systemname = None
        self.userid = None
        self.token = None
        self.verbose = True
        self.logged_in = False
        self.retry = 5
        self._session = aiohttp.ClientSession()
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

        if methodName == "Login" and "You don't have permission" in response:
            #login invalid
            response = "Failed"

        if int(responseXML.find("./Parameters/Parameter[@name='Status']").text) != 0:
            self.request_statusmessage = responseXML.find(
                "./Parameters/Parameter[@name='StatusMessage']"
            ).text
            #raise ValueError(self.request_statusmessage)
            response = self.request_statusmessage
        
        return response

    async def _get_token(self):

        params = {"UserName": self.username, "Password": self.password}

        response = await self.call_api("Login", params)
        
        if "There is no information" in response:
          return '{"Error":"Failed"}'
        else:
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
            
            if response != '{"Error":"Failed"}':
              self.token = response['token']
              self.userid = response['userid']
            else:
              self.token = ""
              self.userid = ""

    async def connect(self):
        """
        Connect to the omnilogic API and if successful, return 
        token and user id from the xml response
        """
        #assert self.username != "", "Username not provided"
        #assert self.password != "", "password not provided"

        if self.username != "" and self.password != "":
          await self.authenticate()

          if self.token is None:
              return False

          self.logged_in = True
          
          return self.token, self.userid

    async def get_site_list(self):
        #assert self.token != "", "No login token"
        
        if self.token is not None:
          params = {"Token": self.token, "UserID": self.userid}

          response = await self.call_api("GetSiteList", params)
          
          if "You don't have permission" in response or "The message format is wrong" in response:
            self.systems = []
          else:
            responseXML = ElementTree.fromstring(response)
            for child in responseXML.findall('./Parameters/Parameter/Item'):
              siteID = 0
              siteName = ""
              site = {}

              for item in child:

                if item.get('name') == "MspSystemID":
                  siteID = int(item.text)
                elif item.get('name') == "BackyardName":
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
            params = {"Token": self.token, "MspSystemID": system['MspSystemID'], "Version": "0"}

            mspconfig = await self.call_api("GetMspConfigFile", params)
            
            configitem = self.convert_to_json(mspconfig)
            configitem['MspSystemID'] = system['MspSystemID']
            configitem['BackyardName'] = system['BackyardName']

            relays = []
            if "Relay" in configitem['Backyard']:
              try:
                for relay in configitem['Relay']:
                  relays.append(relay)
              except:
                relays.append(configitem['Backyard']['Relay'])
            
            configitem['Relays'] = relays

            BOW_list = []
            
            if type(configitem['Backyard']['Body-of-water']) == dict:
              BOW = json.dumps(configitem['Backyard']['Body-of-water'])
              
              bow_relays = []
              bow_lights = []
              
              if 'Relay' in BOW:
                try:
                  for relay in BOW['Relay']:
                    bow_relays.append(relay)
                except:
                  bow_relays.append(configitem['Backyard']['Body-of-water']['Relay'])
              if 'ColorLogic-Light' in BOW:
                try:
                  for light in BOW['ColorLogic-Light']:
                    bow_lights.append(light)
                except:
                  bow_lights.append(configitem['Backyard']['Body-of-water']['ColorLogic-Light'])

              BOW = json.loads(BOW) 
              BOW['Relays'] = bow_relays
              BOW['Lights'] = bow_lights

              BOW_list.append(BOW)
            else:
              for BOW in configitem['Backyard']['Body-of-water']:
                bow_relays = []
                bow_lights = []
                
                if 'Relay' in BOW:
                  try:
                    for relay in BOW['Relay']:
                      if type(relay) == str:
                        bow_relays.append(BOW['Relay'])
                        break
                      else:
                        bow_relays.append(relay)
                  except:
                    bow_relays.append(BOW['Relay'])
                if 'ColorLogic-Light' in BOW:
                  try:
                    for light in BOW['ColorLogic-Light']:
                      if type(light) == str:
                        bow_lights.append(BOW['ColorLogic-Light'])
                        break
                      else:
                        bow_lights.append(light)
                  except:
                    bow_lights.append(BOW['ColorLogic-Light'])
                
                BOW['Relays'] = bow_relays
                BOW['Lights'] = bow_lights

                BOW_list.append(BOW)
            
            configitem['Backyard']['BOWS'] = BOW_list

            mspconfig_list.append(configitem)

          return mspconfig_list
        else:
          return '{"Error":"Failed"}'

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

        if isinstance(config_data['Backyard']['Body-of-water'], list):
            BOWS = config_data['Backyard']['Body-of-water']
        else:
            BOWS = []
            BOWS.append(config_data['Backyard']['Body-of-water'])

        return BOWS

    async def get_alarm_list(self):
        if self.token is None:
            await self.connect()
        if len(self.systems) == 0:
            await self.get_site_list()

        alarmslist = []

        if len(self.systems) != 0 and self.token is not None:
          for system in self.systems:
            params = {"Token": self.token, "MspSystemID": system['MspSystemID'], "Version": "0"}
            site_alarms = {}

            this_alarm = await self.call_api("GetAlarmList", params)

            site_alarms["Alarms"] = self.alarms_to_json(this_alarm)
            site_alarms["MspSystemID"] = system["MspSystemID"]
            site_alarms["BackyardName"] = system["BackyardName"]
            alarmslist.append(site_alarms)
        else:
          return {"Error":"Failure"}    
        
        return alarmslist

    async def set_heater_onoff(self, MspSystemID, PoolID, HeaterID, HeaterEnable):
        if self.token is None:
            await self.connect()
        
        success = False

        if self.token is not None:
          params = {"Token": self.token, "MspSystemID": MspSystemID, "Version": "0", "PoolID": PoolID, "HeaterID": HeaterID, "Enabled": HeaterEnable}

          response = await self.call_api("SetHeaterEnable", params)
          responseXML = ElementTree.fromstring(response)
          
          if int(responseXML.find("./Parameters/Parameter[@name='Status']").text) == 0:
              success = True
        
        return success

    async def set_heater_temperature(self, MspSystemID, PoolID, HeaterID, Temperature):
        if self.token is None:
            await self.connect()

        success = False

        if self.token is not None:
          params = {"Token": self.token, "MspSystemID": MspSystemID, "Version": "0", "PoolID": PoolID, "HeaterID": HeaterID, "Temp": Temperature}

          response = await self.call_api("SetUIHeaterCmd", params)
          responseXML = ElementTree.fromstring(response)
          
          if int(responseXML.find("./Parameters/Parameter[@name='Status']").text) == 0:
              success = True

        return success

    async def set_pump_speed(self, MspSystemID, PoolID, PumpID, Speed):
        if self.token is None:
            await self.connect()

        success = False

        if self.token is not None:
          params = {"Token": self.token, "MspSystemID": MspSystemID, "Version": "0", "PoolID": PoolID, "EquipmentID": PumpID, "IsOn": Speed, "IsCountDownTimer": False, "StartTimeHours": 0, "StartTimeMinutes": 0, "EndTimeHours": 0, "EndTimeMinutes": 0, "DaysActive": 0, "Recurring": False}

          response = await self.call_api("SetUIEquipmentCmd", params)
          responseXML = ElementTree.fromstring(response)
          
          if int(responseXML.find("./Parameters/Parameter[@name='Status']").text) == 0:
              success = True

        return success

    async def set_relay_valve(self, MspSystemID, PoolID, EquipmentID, OnOff):
        if self.token is None:
            await self.connect()

        success = False

        if self.token is not None:
          params = {"Token": self.token, "MspSystemID": MspSystemID, "Version": "0", "PoolID": PoolID, "EquipmentID": EquipmentID, "IsOn": OnOff, "IsCountDownTimer": False, "StartTimeHours": 0, "StartTimeMinutes": 0, "EndTimeHours": 0, "EndTimeMinutes": 0, "DaysActive": 0, "Recurring": False}

          response = await self.call_api("SetUIEquipmentCmd", params)
          
          responseXML = ElementTree.fromstring(response)
          
          if int(responseXML.find("./Parameters/Parameter[@name='Status']").text) == 0:
              success = True

        return success

    async def set_spillover_speed(self, MspSystemID, PoolID, Speed):
        if self.token is None:
            await self.connect()

        success = False

        if self.token is not None:
          params = {"Token": self.token, "MspSystemID": MspSystemID, "Version": "0", "PoolID": PoolID, "Speed": Speed, "IsCountDownTimer": False, "StartTimeHours": 0, "StartTimeMinutes": 0, "EndTimeHours": 0, "EndTimeMinutes": 0, "DaysActive": 0, "Recurring": False}

          response = await self.call_api("SetUISpilloverCmd", params)
          responseXML = ElementTree.fromstring(response)

          if int(responseXML.find("./Parameters/Parameter[@name='Status']").text) == 0:
              success = True

        return success

    async def set_superchlorination(self, MspSystemID, PoolID, ChlorID, IsOn):
        if self.token is None:
            await self.connect()

        success = False

        if self.token is not None:
          params = {"Token": self.token, "MspSystemID": MspSystemID, "Version": "0", "PoolID": PoolID, "ChlorID": ChlorID, "IsOn": IsOn}

          response = await self.call_api("SetUISuperCHLORCmd", params)
          responseXML = ElementTree.fromstring(response)
          
          if int(responseXML.find("./Parameters/Parameter[@name='Status']").text) == 0:
              success = True

        return success

    async def set_lightshow(self, MspSystemID, PoolID, LightID, ShowID):
        if self.token is None:
            await self.connect()

        success = False

        if self.token is not None:
          params = {"Token": self.token, "MspSystemID": MspSystemID, "Version": "0", "PoolID": PoolID, "LightID": LightID, "Show": ShowID, "IsCountDownTimer": False, "StartTimeHours": 0, "StartTimeMinutes": 0, "EndTimeHours": 0, "EndTimeMinutes": 0, "DaysActive": 0, "Recurring": False}

          response = await self.call_api("SetStandAloneLightShow", params)
          responseXML = ElementTree.fromstring(response)
          
          if int(responseXML.find("./Parameters/Parameter[@name='Status']").text) == 0:
              success = True

        return success

    async def set_lightshowv2(self, MspSystemID, PoolID, LightID, ShowID, Speed, Brightness):
        if self.token is None:
            await self.connect()

        success = False

        if self.token is not None:
          params = {"Token": self.token, "MspSystemID": MspSystemID, "Version": "0", "PoolID": PoolID, "LightID": LightID, "Show": ShowID, "Speed":Speed, "Brightness": Brightness, "IsCountDownTimer": False, "StartTimeHours": 0, "StartTimeMinutes": 0, "EndTimeHours": 0, "EndTimeMinutes": 0, "DaysActive": 0, "Recurring": False}

          response = await self.call_api("SetStandAloneLightShowV2", params)
          responseXML = ElementTree.fromstring(response)
          
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

        BOW = {}

        backyard_list = []
        BOW_list = []
        relays = []
        bow_lights = []
        bow_relays = []

        backyard_name = ""
        BOWname = ""

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
                  BOW_list.append(BOW)
                  backyard["BOWS"] = BOW_list
                  backyard_list.append(backyard)

                  backyard_name = "Backyard" + str(child.attrib["systemId"])
                  backyard = child.attrib
                  BOW_list = []
                  bow_lights = []
                  bow_relays = []
                  relays = []
                  BOWname = ""
                
            elif child.tag == "BodyOfWater":
                if BOWname == "":
                  backyard["Relays"] = relays
                  BOWname = "BOW" + str(child.attrib["systemId"])
                  BOW = child.attrib
                else:
                  BOW["Lights"] = bow_lights
                  BOW["Relays"] = bow_relays
                  
                  BOW_list.append(BOW)

                  BOW = {}
                  bow_lights = []
                  bow_relays = []

                  BOWname = "BOW" + str(child.attrib["systemId"])
                  
                  BOW = child.attrib
                
            elif child.tag == "Relay" and BOWname=="":
                relays.append(child.attrib)

            elif child.tag == "ColorLogic-Light":
                bow_lights.append(child.attrib)

            elif child.tag == "Relay":
                bow_relays.append(child.attrib)

            else:
                BOW[child.tag] = child.attrib

        BOW["Lights"] = bow_lights
        BOW["Relays"] = bow_relays
        BOW_list.append(BOW)

        backyard["BOWS"] = BOW_list

        backyard_list.append(backyard)

        return backyard_list

    async def get_telemetry_data(self):
        if self.token is None:
            await self.connect()
        if len(self.systems) == 0:
            await self.get_site_list()

        # assert self.token != "", "No login token"
        telem_list = []
        if self.token != "" and len(self.systems) != 0:
          
          for system in self.systems:
            
            params = {"Token": self.token, "MspSystemID": system['MspSystemID']}
            
            telem = await self.call_api("GetTelemetryData", params)
            
            site_telem = {}
            site_telem['Telemetry'] = self.telemetry_to_json(telem)
            site_telem['MspSystemID'] = system['MspSystemID']
            site_telem['BackyardName'] = system['BackyardName']

            telem_list.append(site_telem)

        else:
          return({"Error":"Failure"})

        return telem_list

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