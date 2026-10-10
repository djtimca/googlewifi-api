# googlewifi-api
PyPi Integration for Google WiFi Services for Home Assistant integration. Also provides bluetooth scanning from Google/Nest Home, Mini etc smart speakers to return information about bluetooth devices in the area.

## Required - Google account credentials

This API authenticates through Google Play Services OAuth (`gpsoauth`). You need your Google account email, a master token (`aas_et/...` or `oauth2rt_1/...`), and an `android_id`.

To obtain a master token:

1. Open `https://accounts.google.com/EmbeddedSetup` in a browser.
2. Sign in with the Google account that owns/manages the Wifi network.
3. Open browser developer tools and copy the **entire** value of the `oauth_token` cookie (it starts with `oauth2_4/`).
4. Exchange it for a master token:

```python
import secrets, asyncio
from googlewifi import GoogleWifi

android_id = secrets.token_hex(8)
master_token = asyncio.run(
    GoogleWifi.exchange_oauth_token("you@gmail.com", "oauth2_4/...", android_id)
)
```

The short-lived `oauth_token` is only used once. The resulting master token is reusable and sensitive — treat it like a password.

If you already have a master token, skip the exchange and pass it directly.

## Usage

```python
api = GoogleWifi(
    email="you@gmail.com",
    master_token="aas_et/...",
    android_id="0123456789abcdef",
)
await api.connect()
systems = await api.get_systems()
```

Session can be sent as an optional aiohttp session if you are managing your session within an application.

`GoogleWifiAuthError` is raised when the stored master token is rejected by Google and a new `oauth_token` exchange is required.

## Available Methods

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

### refresh_tokens()

Will return a dict of local access tokens for Google Home/Mini etc devices in format {cloud_device_id:local_access_token}. These tokens are required to access a Google Home device for bluetooth updates and scanning.

### update_info(host:str)

Will return the detailed capabilities and information for a Google Home/Mini etc device. You have to provide the host IP (ie. 192.168.0.20) and it will return a detailed JSON payload which includes the capabilities of the device as well as the cloud device ID which can be used to extract the correct local access token from the refresh_tokens() dict.

### get_bluetooth_status(host:str, token:str)

Will return the current bluetooth status for the Google Home/Mini etc device.

### get_bluetooth_devices(host:str, token:str)

Will return a list of all bluetooth devices which are within range of that Google Home/Mini etc including the MAC address, device type, name, and RSSI (signal strength).

### run_speed_test(system_id:str)

Will run a WAN speed test on the system and return the results (upload/download speed).

Note: This library was built specifically for integration to Home Assistant.
