import asyncio
import aiohttp
import json
import datetime

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

  async def post_api(self, url:str, headers:str, payload:str):
    """Post to the Google APIs."""
    async with self._session.post(url, headers=headers, data=payload) as resp:
      try:
        response = await resp.text()
      except aiohttp.ClientConnectorError as error:
        raise ConnectionError(error)
    
    try:
      response = json.loads(response)
    except json.JSONDecodeError as error:
      raise ValueError(error)

    return response

  async def get_api(self, url:str, headers:str, payload:str):
    """Get call to Google APIs."""
    async with self._session.get(url, headers=headers, data=payload) as resp:
      try:
        response = await resp.text()
      except aiohttp.ConnectionError as error:
        raise ConnectionError(error)
    
    try:
      response = json.loads(response)
    except json.JSONDecodeError as error:
      raise ValueError(error)
    
    return response

  async def put_api(self, url:str, headers:str, payload:str):
    """Put call to Google APIs."""
    async with self._session.put(url, headers=headers, data=payload) as resp:
      try:
        response = await resp.text()
      except aiohttp.ConnectionError as error:
        raise ConnectionError(error)
      
      try:
        response = json.loads(response)
      except json.JSONDecodeError as error:
        raise ValueError(error)

      return response

  async def delete_api(self, url:str, headers:str, payload:str):
    """Delete call to Google APIs."""
    async with self._session.delete(url, headers=headers, data=payload) as resp:
      try:
        response = await resp.text()
      except aiohttp.ConnectionError as error:
        raise ConnectionError(error)

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
        raise ConnectionError("Failed to retreive Google Wifi Data.")

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

      systems[this_system["id"]]["status"] = system_status["wanConnectionStatus"]

      this_status = {}
      for this_ap in system_status["apStatuses"]:
        this_status[this_ap["apId"]] = this_ap

      system_status["status"] = this_status

      access_points = {}
      
      for this_ap in this_system["accessPoints"]:
        access_points[this_ap["id"]] = this_ap
        access_points[this_ap["id"]]["status"] = system_status["status"][this_ap["id"]]["apState"]
      
      systems[this_system["id"]]["access_points"] = access_points

      devices_list = await self.get_devices(this_system["id"])
      
      devices = {}
      for this_device in devices_list["stations"]:
        devices[this_device["id"]] = this_device

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
