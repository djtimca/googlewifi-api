# googlewifi-api
PyPi Integration for Google WiFi Services for Home Assistant integration.

## Required - Refresh Token

In order to use this API you will need to get a Refresh Token by using the tools or Chrome plugin at https://www.angelod.com/onhubauthtool

## Available Methods

When you initiate the GoogleWifi class you will need to pass in your refresh token that you receive using the tools at www.angelod.com.

Session can be sent as an optional aiohttp session if you are managing your session within an application.

### get_systems()

Returns a structured data set that includes the entire system data including system status, access point information and status, and devices from the network.

### pause_device(system_id:str, device_id:str, pause_state:bool)

Pause or unpause a specific device on the network. Must specify the system_id, device_id and pause_state (True to pause, False to unpause). Returns True/False on success of the call.

### prioritize_device(system_id:str, device_id:str, duration_hours:int (default 1))

Prioritize a device for a period of hours (to be specified by duration_hours) from 1 hour to 6 hours maximum. Must specify the system_id and device_id. If duration_hours is not passed it will default to 1 hour prioritization. Returns True/False on success of the call.

### clear_prioritization(system_id:str)

Clear any existing device prioritization from the system. Must specify the system_id to clear. Returns True/False on success of the call.

### set_brightness(ap_id:str, brightness:int)

Set the light brightness on the Access Point. Must specify the access point id (ap_id) and the desired brightness. Brightness range is 0-100. Returns True/False on the success of the call.

### restart_ap(ap_id:str)

Restart a specific Access Point. Must specify the access point (ap_id). Returns True/False on the success of the call.

### restart_system(system_id:str)

Restart the entire system. Must specify the system to restart (system_id). Returns True/False on the success of the call.

Note: This library was built specifically for integration to Home Assistant.
