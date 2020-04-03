import time
import json
import requests
import collections
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement, Comment, tostring


class OmniLogic:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.systemid = ''
        self.userid = ''
        self.token = ''
        self.verbose = True
        self.logged_in = False

    #Build Request - Pass name of method and dict of params
    def buildRequest(self,requestName,params):

        req = Element('Request')
        reqName = SubElement(req,'Name')
        reqName.text = requestName
        paramTag = SubElement(req,'Parameters')

        for item in params:
            for p in item.keys():
                datatype=""

                if (type(item[p]) == int):
                    #print("int check")
                    datatype = "int"
                elif (type(item[p]) == str):
                    #print("str check")
                    datatype = "string"
                else:
                    print("Couldn't determine datatype, exiting.")
                    return None

                param = SubElement(paramTag,'Parameter', name=p, dataType=datatype)
                param.text = str(item[p])
        
        xml = ElementTree.tostring(req).decode()
        print ("\n" + xml + "\n")
        return xml

    #Generic method to call API.
    def call_api(self,methodName, params):
       
        url = "https://app1.haywardomnilogic.com/HAAPI/HomeAutomation/API.ashx"
        payload = self.buildRequest(methodName,params) 
        headers = {
            'content-type': "text/xml",
            'cache-control': "no-cache",
            }

        response = requests.request("POST", url, data=payload, headers=headers)

        print (response.text)
        return(response.content)


    def connect(self):
        
        params = [{'UserName': self.username, 'Password': self.password}]
        response = self.call_api('Login',params)
        responseXML = ElementTree.fromstring(response)
        self.token = responseXML.find("./Parameters/Parameter[@name='Token']").text
        self.userid = int(responseXML.find("./Parameters/Parameter[@name='UserID']").text)

        if self.token is None:
            return False

        self.logged_in = True
 
    def get_site_list(self):
        assert (self.token != ''), "No login token"

        params = [{'Token': self.token}, {'UserID': self.userid}]
        response = self.call_api('GetSiteList',params)
        responseXML = ElementTree.fromstring(response)
        self.systemid = int(responseXML.find("./Parameters/Parameter/Item/Property[@name='MspSystemID']").text)
        
    def get_msp_config_file(self):
        assert (self.token != ''), "No login token"

        params = [{'Token': self.token}, {'MspSystemID': self.systemid}, {'Version': "0"}]
        response = self.call_api('GetMspConfigFile',params)

    #def get_telemetry_data(self):

    #def get_alarm_list(self):

#put yo creds in to test
c = OmniLogic(username='',password='')
c.connect()
print("\nToken: " + c.token)
c.get_site_list()
c.get_msp_config_file()