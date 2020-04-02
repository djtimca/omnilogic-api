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
        self.token = ''
        self.verbose = True
        self.logged_in = False

    #Build Request - Pass name of method and dict of params
    def buildRequest(self,requestName,params):

        req = Element('Request')
        reqName = SubElement(req,'Name')
        reqName.text = requestName
        paramTag = SubElement(req,'Parameters')

        for p in params.keys():
            param = SubElement(paramTag,'Parameter', name=p,dataType="string")
            param.text = params[p]
        
        xml = ElementTree.tostring(req).decode()
        print (xml)
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
        
        params = {'UserName': self.username, 'Password': self.password}
        response = self.call_api('Login',params)
        responseXML = ElementTree.fromstring(response)
        self.token = responseXML.find("./Parameters/Parameter[@name='Token']").text

        if self.token is None:
            return False

        self.logged_in = True



#put yo creds in to test
c = OmniLogic(username='',password='')
c.connect()
print(c.token)