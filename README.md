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

## Functions

### get_msp_config_file()

Returns the full configuration of the registered Omnilogic System in JSON format.

### get_telemetry_data

Returns the status of all of the equipment in the Omnilogic System in JSON format (ie. pump speeds, water temperature, heat setting, etc)

### get_BOWS

Returns the list of Bodies of Water from the MSP configuration file, forced into a JSON list (handles issues between single pool and multiple pool setups)

### get_alarm_list

Returns a list of all alarms on the pool equipment in JSON format. If there are no alarms returns JSON {'Alarms', 'False'}

### set_heater_onoff(PoolID, HeaterID, HeaterEnable)

Turns the heater on or off (toggle). Pass the PoolID and HeaterID as int and boolean True (turn on) or False (turn off) to set the heater state.
