import asyncio
import aiohttp
import json
import datetime
import dateutil.parser
import grpc

from .v1_pb2 import GetHomeGraphRequest
from .v1_pb2_grpc import StructuresServiceStub

GH_HEADERS = {"Content-Type": "application/json"}
class GoogleWifi:

  def __init__(self, refresh_token, session:aiohttp.ClientSession = None):
    """Get the API Bearer Token."""

    if session:
      self._session = session
    else:
      self._session = aiohttp.ClientSession()

    self._refresh_token = refresh_token
    self._access_token = None
    self._api_token = None
    self._systems = None
    self._access_points = {}

  async def post_api(
    self, 
    url:str, 
    headers:str=None, 
    payload:str=None, 
    params:str=None,
    json_payload=None,
    ):
    """Post to the Google APIs."""
    async with self._session.post(
      url, 
      headers=headers, 
      data=payload,
      params=params,
      verify_ssl=False,
      json=json_payload,
    ) as resp:
      try:
        response = await resp.text()
      except aiohttp.ClientConnectorError as error:
        raise ConnectionError(error)
    
    if response:
      try:
        response = json.loads(response)
      except json.JSONDecodeError as error:
        raise ValueError(error)

    return response

  async def get_api(self, url:str, headers:str=None, payload:str=None, params:str=None):
    """Get call to Google APIs."""
    async with self._session.get(
      url, 
      headers=headers, 
      data=payload, 
      params=params,
      verify_ssl=False,
    ) as resp:
      try:
        response = await resp.text()
      except aiohttp.ConnectionError as error:
        raise ConnectionError(error)
    
    if response:
      try:
        response = json.loads(response)
      except json.JSONDecodeError as error:
        raise ValueError(error)
      
    return response

  async def put_api(self, url:str, headers:str=None, payload:str=None, params:str=None):
    """Put call to Google APIs."""
    async with self._session.put(
      url, 
      headers=headers, 
      data=payload,
      params=params,
      verify_ssl=False,
    ) as resp:
      try:
        response = await resp.text()
      except aiohttp.ConnectionError as error:
        raise ConnectionError(error)

    if response:  
      try:
        response = json.loads(response)
      except json.JSONDecodeError as error:
        raise ValueError(error)

      return response

  async def delete_api(self, url:str, headers:str=None, payload:str=None, params:str=None):
    """Delete call to Google APIs."""
    async with self._session.delete(
      url, 
      headers=headers, 
      data=payload,
      params=params,
      verify_ssl=False,
    ) as resp:
      try:
        response = await resp.text()
      except aiohttp.ConnectionError as error:
        raise ConnectionError(error)

    if response:
      try:
        response = json.loads(response)
      except json.JSONDecodeError as error:
        raise ValueError(error)

      return response

  async def get_access_token(self):
    """Get Access Token"""
    url = "https://www.googleapis.com/oauth2/v4/token"
    payload = f"client_id=936475272427.apps.googleusercontent.com&grant_type=refresh_token&refresh_token={self._refresh_token}"
    headers = {
      'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    response = await self.post_api(url, headers, payload)
    
    self._access_token = response.get("access_token", None)

  async def get_api_token(self):
    """Get the API Token."""
    
    if not self._access_token:
      await self.get_access_token()
      
      if not self._access_token:
        raise ConnectionError("Authorization Error")

    oath_url = "https://oauthaccountmanager.googleapis.com/v1/issuetoken"
    payload = "app_id=com.google.OnHub&client_id=586698244315-vc96jg3mn4nap78iir799fc2ll3rk18s.apps.googleusercontent.com&hl=en-US&lib_ver=3.3&response_type=token&scope=https%3A//www.googleapis.com/auth/accesspoints%20https%3A//www.googleapis.com/auth/clouddevices"
    headers = {
      'Authorization': f"Bearer {self._access_token}",
      'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    response = await self.post_api(oath_url, headers, payload)
    
    self._api_token = response.get("token", None)
    if self._api_token:
      return True

  async def connect(self):
    """Authenticate to the Google Wifi services."""
    success = True

    if not self._api_token:
      success = await self.get_api_token()
      
    if success:
      return True
    else:
      return False

  async def get_systems(self):
    """Get the systems on this account."""
    if await self.connect():
      url = "https://googlehomefoyer-pa.googleapis.com/v2/groups?prettyPrint=false"
      headers = {
        "Authorization": f"Bearer {self._api_token}",
        "Content-Type": "application/json; charset=utf-8"
      }
      payload = {}
      
      response = await self.get_api(url, headers, payload)

      if response.get("groups"):
        return await self.structure_systems(response)
      else:
        raise GoogleWifiException("Failed to retreive Google Wifi Data.")

  async def get_devices(self, system_id):
    """Retrieve the devices list for a given system."""
    
    if await self.connect():
      url = f"https://googlehomefoyer-pa.googleapis.com/v2/groups/{system_id}/stations?prettyPrint=false"
      headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {self._api_token}"
      }
      payload = {}

      response =  await self.get_api(url, headers, payload)

      return(response)

  async def get_status(self, system_id):
    """Retrieve the status payload for a system."""

    if await self.connect():
      url=f"https://googlehomefoyer-pa.googleapis.com/v2/groups/{system_id}/status?prettyPrint=false"
      headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {self._api_token}"
      }
      payload = {}

      response = await self.get_api(url, headers, payload)

      return(response)

  async def structure_systems(self, system_data):
    """Structure the data with ids in dict."""
    systems = {}
    
    for this_system in system_data["groups"]:
      systems[this_system["id"]] = this_system

      system_status = await self.get_status(this_system["id"])

      try:
        systems[this_system["id"]]["status"] = system_status["wanConnectionStatus"]
      except KeyError as error:
        raise GoogleWifiException(error)

      blocking_policies = {}
      if this_system["groupSettings"].get("familyHubSettings").get("stationPolicies"):
        for blocking_policy in this_system["groupSettings"]["familyHubSettings"]["stationPolicies"]:
          blocking_policies[blocking_policy["stationId"]] = blocking_policy

      this_status = {}
      for this_ap in system_status["apStatuses"]:
        this_status[this_ap["apId"]] = this_ap

      system_status["status"] = this_status

      access_points = {}
      
      try:
        for this_ap in this_system["accessPoints"]:
          access_points[this_ap["id"]] = this_ap
          access_points[this_ap["id"]]["status"] = system_status["status"][this_ap["id"]]["apState"]
      except KeyError as error:
        raise GoogleWifiException(error)

      systems[this_system["id"]]["access_points"] = access_points

      devices_list = await self.get_devices(this_system["id"])
      
      devices = {}
      
      try:
        for this_device in devices_list["stations"]:
          devices[this_device["id"]] = this_device
          device_paused = False

          if blocking_policies.get(this_device["id"]):
            expire_date = dateutil.parser.parse(blocking_policies[this_device["id"]]["blockingPolicy"]["expiryTimestamp"])
            
            if expire_date > datetime.datetime.now(datetime.timezone.utc) or expire_date.timestamp() == 0:
              device_paused = True

          devices[this_device["id"]]["paused"] = device_paused
      except KeyError as error:
        raise GoogleWifiException(error)

      systems[this_system["id"]]["devices"] = devices

      return systems

  async def pause_device(self, system_id:str, device_id:str, pause_state:bool):
    """Pause or unpause a specific device"""

    if await self.connect():
      url = f"https://googlehomefoyer-pa.googleapis.com/v2/groups/{system_id}/stationBlocking?prettyPrint=false"
      headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {self._api_token}"
      }

      payload = {
        "blocked": str(pause_state).lower(),
        "stationId": device_id
      }
      payload = json.dumps(payload)
      
      response = await self.put_api(url, headers, payload)

      return response.get("operation").get("operationState") == "CREATED"

    else:
      return False

  async def prioritize_device(self, system_id:str, device_id:str, duration_hours:int=1):
    """Set priority device for specified time (default 1 hour)."""
    
    if await self.connect():
      duration_hours = 1 if duration_hours < 1 else duration_hours
      duration_hours = 6 if duration_hours > 6 else duration_hours
      
      url = f"https://googlehomefoyer-pa.googleapis.com/v2/groups/{system_id}/prioritizedStation?prettyPrint=false"
      headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {self._api_token}"
      }

      end_time = datetime.datetime.now() + datetime.timedelta(hours=duration_hours)

      end_time = end_time.astimezone().replace(microsecond=0).isoformat()

      payload = {
        "stationId": device_id,
        "prioritizationEndTime": end_time
      }

      payload = json.dumps(payload)

      response = await self.put_api(url, headers=headers, payload=payload)

      return response.get("operation").get("operationState") == "CREATED"

    else:
      return False

  async def clear_prioritization(self, system_id:str):
    """Clear any device prioritization."""
    
    if await self.connect():
      url=f"https://googlehomefoyer-pa.googleapis.com/v2/groups/{system_id}/prioritizedStation?prettyPrint=false"

      headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {self._api_token}"
      }

      payload = {}

      response = await self.delete_api(url, headers=headers, payload=payload)

      return response.get("operation").get("operationState") == "CREATED"

    else:
      return False

  async def set_brightness(self, ap_id:str, brightness:int):
    """Set Access Point Light Brightness."""

    if await self.connect():
      brightness = 0 if brightness < 0 else brightness
      brightness = 100 if brightness > 100 else brightness
      
      url = f"https://googlehomefoyer-pa.googleapis.com/v2/accesspoints/{ap_id}/lighting?prettyPrint=false"

      headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {self._api_token}"
      }

      payload = {
        "automatic": False,
        "intensity": brightness
      }

      payload = json.dumps(payload)

      response = await self.put_api(url, headers=headers, payload=payload)

      return response.get("operation").get("operationState") == "CREATED"

    else:
      return False

  async def restart_ap(self, ap_id:str):
    """Restart a specific Access Point."""

    if await self.connect():
      url=f"https://googlehomefoyer-pa.googleapis.com/v2/accesspoints/{ap_id}/reboot?prettyPrint=false"

      headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {self._api_token}"
      }

      payload = {}
      
      response = await self.post_api(url, headers=headers, payload=payload)

      return response.get("operation").get("operationState") == "CREATED"
    
    else:
      return False
  
  async def restart_system(self, system_id:str):
    """Restart the whole Google Wifi System."""

    if await self.connect():
      url = f"https://googlehomefoyer-pa.googleapis.com/v2/groups/{system_id}/reboot?prettyPrint=false"

      headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {self._api_token}"
      }

      payload = {}

      response = await self.post_api(url, headers=headers, payload=payload)

      return response.get("operation").get("operationState") == "CREATED"

    else:
      return False

  async def refresh_tokens(self):
    """Refresh the Google Access tokens for local Google devices."""
    if await self.connect():
      creds = grpc.access_token_call_credentials(self._api_token)
      ssl = grpc.ssl_channel_credentials()
      composite = grpc.composite_channel_credentials(ssl, creds)
      channel = grpc.secure_channel("googlehomefoyer-pa.googleapis.com:443", composite)
      service = StructuresServiceStub(channel)
      resp = service.GetHomeGraph(GetHomeGraphRequest())
      data = resp.home.devices

      tokens = {}

      for device in data:
          # this is the 'cloud device id'
          if device.local_auth_token != "":
            tokens[
                device.device_info.project_info.string2
            ] = device.local_auth_token

      return tokens

  async def update_info(self, host):
    """Update data from Google Home."""

    if await self.connect():
      url = f"https://{host}:8443/setup/eureka_info"
      params = {
        "params":"version,audio,name,build_info,detail,device_info,net,wifi,setup,settings,opt_in,opencast,multizone,proxy,night_mode_params,user_eq,room_equalizer",
        "options":"detail"
      }

      response = await self.get_api(url=url,params=params)

      if response:
        return response
      else:
        raise GoogleHomeUpdateFailed()

  async def get_bluetooth_status(self, host, token):
    """Retrieve the current bluetooth status."""
    if await self.connect():
      url = f"https://{host}:8443/setup/bluetooth/status"
      headers = {"cast-local-authorization-token": token}

      response = await self.get_api(url=url,headers=headers)

      return response

  async def get_bluetooth_devices(self, host, token):
    """Retrieve the current bluetooth clients from a Google Home."""

    if await self.connect():
      url = f"https://{host}:8443/setup/bluetooth/scan"
      data = {"enable": True, "clear_results": False, "timeout": 5}
      headers = GH_HEADERS
      headers["Host"] = host
      headers["cast-local-authorization-token"] = token

      await self.post_api(url=url,headers=headers,json_payload=data)
      await asyncio.sleep(5)

      url = f"https://{host}:8443/setup/bluetooth/scan_results"
      
      response = await self.get_api(url=url,headers=headers)

      if response:
        return response
      else:
        raise GoogleHomeUpdateFailed()

class GoogleWifiException(Exception):
  """Platform not ready exception."""
  pass

class GoogleHomeUpdateFailed(Exception):
  """Google Home Update failed, token refresh required."""
