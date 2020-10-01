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

telemetry_data = await api_client.get_telemetry_data()


## Functions

### get_msp_config_file()

** DEPRECATED - ALL CONFIG DATA NOW RETURNED WITH THE TELEMETRY **

Returns the full configuration of the registered Omnilogic System in JSON format with all systems on your account returned in a list and all bodies-of-water captured in a list (BOWS). Additional components like lights and relays are also forced into a list to make them easier to parse. You will need to retain the MspSystemID for each pool system in order to be able to call any of the equipment change methods. Left available to allow retrieval of new configurations for addition to the get_telemetry_data method as development continues.

### get_telemetry_data(APIClient)

Returns the status of all of the equipment in the Omnilogic System in JSON format (ie. pump speeds, water temperature, heat setting, etc). This data also is returned as a list with components like lights and relays grouped into lists for easy parsing. Includes key config data such as SystemIds, equipment names, equipment parameters (max/min speed etc) and alarms for common pool components.

### get_alarm_list(APIClient)

Returns a list of all alarms on the pool equipment in JSON format. If there are no alarms returns JSON {'BowID', 'False'}. Also returned as a list for all pool systems on your Omnilogic account. Note that alarm information is also returned in the get_telemetry_data method so unless you need just the full list of alarms this should not be needed.

### set_heater_onoff(APIClient, MSPSystemID, PoolID, HeaterID, HeaterEnable)

Turns the heater on or off (toggle). Pass the MspSystemID, PoolID and HeaterID as int and boolean True (turn on) or False (turn off) to set the heater state.

### set_heater_temperature(APIClient, MspSystemID, PoolID, HeaterID, Temperature)

Sets the heater set-point to a specified temperature. Pass the MspSystemId, PoolID, HeaterID, and desired Temperature as int to set the heater target temperature.

### set_pump_speed(APIClient, MspSystemID, PoolID, PumpID, Speed)

Sets the pump speed or turns the pump on or off. Pass the MspSystemID, PoolID and HeaterID as int. Pass the Speed according to the following table.

|Pump Type|ON|OFF|
|---------|--|---|
|Single Speed|100|0|
|Variable Speed|18-100|0|

### set_relay_valve(APIClient, MspSystemID, PoolID, EquipmentID, OnOff)

Sets a relay or valve to On/Off (Open/Close). Pass the MspSystemID, PoolID and EquipmentID of the valve or relay as int. Pass OnOff value as int according to the following table. Also used to turn on/off lights attached to a relay without changing the lightshow.

|Equipment Type|Value=1|Value=0|
|--------------|-------|-------|
|Relay|ON|OFF|
|Valve|OPEN|CLOSED|

### set_spillover_speed(APIClient, MspSystemID, PoolID, Speed)

Sets the spillover speed for a pool that supports Spillover. Pass the MspSystemID, PoolID and desired spillover Speed as int.

### set_superchlorination(APIClient, MspSystemID, PoolID, ChlorID, IsOn)

Sets the SuperChlorination function on or off. Pass the MspSystemID, PoolID and the ChlorID (Equipment ID of the Chlorinator) as int. Pass IsOn as int with 1 to turn on SuperChlorination and 0 to turn off SuperChlorination.

### set_lightshow(APIClient, MspSystemID, PoolID, LightID, ShowID)

Turns on and sets the desired lightshow for V1 (non-brightness/speed controlled) lights. Pass the MspSystemID, PoolID and LightID as int. Select the desired show based on the table below:

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
|17|YELLOW|
|18|ORANGE|
|19|GOLD|
|20|MINT|
|21|TEAL|
|22|BURNT_ORANGE|
|23|PURE_WHITE|
|24|CRISP_WHITE|
|25|WARM_WHITE|
|26|BRIGHT_YELLOW|

Note that show 17-26 may not be supported by all ColorLogic Light Systems.

### set_lightshowv2(APIClient, MspSystemID, PoolID, LightID, ShowID, Speed, Brightness)

Turns on and sets the desired lightshow for V2 light systems. Pass the MspSystemID, PoolID and LightID as int. Use the table from above for the desired show as int. Send brightness and speed as Int.

