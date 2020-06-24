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

### set_heater_temperature(self, PoolID, HeaterID, Temperature)

Sets the heater set-point to a specified temperature. Pass the PoolID, HeaterID, and desired Temperature as int to set the heater target temperature.

### set_pump_speed(self, PoolID, PumpID, Speed)

Sets the pump speed or turns the pump on or off. Pass the PoolID and HeaterID as int. Pass the Speed according to the following table.

|Pump Type|ON|OFF|
|---------|--|---|
|Single Speed|100|0|
|Variable Speed|18-100|0|

### set_relay_valve(self, PoolID, EquipmentID, OnOff)

Sets a relay or valve to On/Off (Open/Close). Pass the PoolID and EquipmentID of the valve or relay as int. Pass OnOff value as int according to the following table. Also used to turn on/off lights attached to a relay without changing the lightshow.

|Equipment Type|Value=1|Value=0|
|--------------|-------|-------|
|Relay|ON|OFF|
|Valve|OPEN|CLOSED|

### set_spillover_speed(self, PoolID, Speed)

Sets the spillover speed for a pool that supports Spillover. Pass the PoolID and desired spillover Speed as int.

### set_superchlorination(self, PoolID, ChlorID, IsOn)

Sets the SuperChlorination function on or off. Pass the PoolID and the ChlorID (Equipment ID of the Chlorinator) as int. Pass IsOn as int with 1 to turn on SuperChlorination and 0 to turn off SuperChlorination.

### set_lightshow(self, PoolID, LightID, ShowID)

Turns on and sets the desired lightshow for V1 (non-brightness/speed controlled) lights. Pass the PoolID and LightID as int. Select the desired show based on the table below:

|ShowID|Color/Show|
|------|----------|
|0|Show-Voodoo Lounge|
|1|Fixed-Deep Blue Sea|
|2|Fixed-Royal Blue|
|3|Fixed-Afternoon Skies|
|4|Fixed-Aqua Green|
|5|Fixed-Emerald|
|6|Fixed-Cloud White|
|7|Fixed-Warm Red|
|8|Fixed-Flamingo|
|9|Fixed-Vivid Violet|
|10|Fixed-Sangria|
|11|Show-Twilight|
|12|Show-Tranquility|
|13|Show-Gemstone|
|14|Show-USA|
|15|Show-Mardi Gras|
|16|Show-Cool Cabaret|

### set_lightshowv2(self, PoolID, LightID, ShowID, Speed, Brightness)

Turns on and sets the desired lightshow for V2 light systems. Pass the PoolID and LightID as int. Use the table from above for the desired show as int. Send brightness and speed as Int.

