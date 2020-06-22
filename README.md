# Hayward OmniLogic Integration
Integration library for Hayward Omnilogic pool controllers to allow easy integration through their API to your home automation system.

# Usage

## Getting it

To download OmniLogic, either fork this github repo or simply use PyPi via pip.

'''
$ pip install omnilogic
'''

## Using it

OmniLogic provides just the core actions, you will need to code your own specific use of the returned data.

'''
from omnilogic import OmniLogic
'''

A simple example to return the status of your pool equipment is:

'''
api_client = OmniLogic(username, password)

config_data = await api_client.get_msp_config_file()
telemetry_data = await api_client.get_telemetry_data()
BOWS = await api_client.get_BOWS()
