import asyncio
import time
import aiohttp
import json
import datetime
import dateutil.parser
import grpc
import gpsoauth

from ghome_foyer_api.api_pb2 import GetHomeGraphRequest
from ghome_foyer_api.api_pb2_grpc import StructuresServiceStub

GH_HEADERS = {"Content-Type": "application/json"}

OAUTH_SERVICE = (
  "oauth2:https://www.googleapis.com/auth/accesspoints "
  "https://www.googleapis.com/auth/clouddevices"
)
GOOGLE_HOME_APP = "com.google.android.apps.chromecast.app"
GOOGLE_HOME_CLIENT_SIG = "24bb24c05e47e0aefa68a58a766179d9b613a600"
TOKEN_REFRESH_MARGIN = 300
GPSOAUTH_TIMEOUT = 30


class GoogleWifi:

  def __init__(self, email:str, master_token:str, android_id:str, session:aiohttp.ClientSession = None):
    """Initialize the Google Wifi API with a Google account credential set.

    email: Google account email address.
    master_token: aas_et/... or oauth2rt_1/... master token obtained via exchange_oauth_token().
    android_id: android id used when the master token was minted.
    """

    if session:
      self._session = session
    else:
      self._session = aiohttp.ClientSession()

    self._email = email
    self._master_token = master_token
    self._android_id = android_id
    self._api_token = None
    self._api_token_expiry = 0
    self._systems = None
    self._access_points = {}

  @staticmethod
  async def exchange_oauth_token(email:str, oauth_token:str, android_id:str):
    """Exchange an EmbeddedSetup oauth_token (oauth2_4/...) for a master token."""
    def _exchange():
      return gpsoauth.exchange_token(email, oauth_token, android_id)

    try:
      response = await asyncio.wait_for(asyncio.to_thread(_exchange), GPSOAUTH_TIMEOUT)
    except asyncio.TimeoutError as error:
      raise ConnectionError(f"Timed out contacting Google authentication: {error}") from error
    except Exception as error:
      raise GoogleWifiAuthError(f"Could not exchange oauth_token: {error}") from error

    if not isinstance(response, dict):
      raise GoogleWifiAuthError("Malformed response from Google authentication")

    master_token = response.get("Token")
    if not master_token:
      error = response.get("Error") or response.get("error") or "unknown error"
      raise GoogleWifiAuthError(f"Google did not return a master token: {error}")

    return master_token

  async def post_api(
    self,
    url:str,
    headers:str=None,
    payload:str=None,
    params:str=None,
    json_payload=None,
    _retry:bool=True,
    ):
    """Post to the Google APIs."""
    async with self._session.post(
      url,
      headers=headers,
      data=payload,
      params=params,
      json=json_payload,
      timeout=30,
    ) as resp:
      if resp.status == 401 and _retry:
        await self._refresh_token_once(headers)
        return await self.post_api(url, headers, payload, params, json_payload, False)
      self._check_status(resp.status)
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

  async def get_api(self, url:str, headers:str=None, payload:str=None, params:str=None, _retry:bool=True):
    """Get call to Google APIs."""
    try:
      async with self._session.get(
        url,
        headers=headers,
        data=payload,
        params=params,
        timeout=30,
      ) as resp:
        if resp.status == 401 and _retry:
          await self._refresh_token_once(headers)
          return await self.get_api(url, headers, payload, params, False)
        self._check_status(resp.status)
        try:
          response = await resp.text()
        except aiohttp.ClientError as error:
          raise ConnectionError(error)
    except asyncio.TimeoutError as error:
      raise GoogleHomeIgnoreDevice(error)

    if response:
      try:
        response = json.loads(response)
      except json.JSONDecodeError as error:
        raise ValueError(error)

    return response

  async def put_api(self, url:str, headers:str=None, payload:str=None, params:str=None, _retry:bool=True):
    """Put call to Google APIs."""
    async with self._session.put(
      url,
      headers=headers,
      data=payload,
      params=params,
      timeout=30,
    ) as resp:
      if resp.status == 401 and _retry:
        await self._refresh_token_once(headers)
        return await self.put_api(url, headers, payload, params, False)
      self._check_status(resp.status)
      try:
        response = await resp.text()
      except aiohttp.ClientError as error:
        raise ConnectionError(error)

    if response:
      try:
        response = json.loads(response)
      except json.JSONDecodeError as error:
        raise ValueError(error)

      return response

  async def delete_api(self, url:str, headers:str=None, payload:str=None, params:str=None, _retry:bool=True):
    """Delete call to Google APIs."""
    async with self._session.delete(
      url,
      headers=headers,
      data=payload,
      params=params,
      timeout=30,
    ) as resp:
      if resp.status == 401 and _retry:
        await self._refresh_token_once(headers)
        return await self.delete_api(url, headers, payload, params, False)
      self._check_status(resp.status)
      try:
        response = await resp.text()
      except aiohttp.ClientError as error:
        raise ConnectionError(error)

    if response:
      try:
        response = json.loads(response)
      except json.JSONDecodeError as error:
        raise ValueError(error)

      return response

  @staticmethod
  def _check_status(status:int):
    """Raise on error responses, re-mintable auth errors included."""
    if status == 401 or status == 403:
      raise GoogleWifiAuthError(f"Foyer authorization failed (HTTP {status})")
    if status >= 400:
      raise GoogleWifiException(f"Foyer API returned HTTP {status}")

  async def get_api_token(self, force_refresh:bool=False):
    """Mint or refresh the scoped API token via Google Play Services OAuth."""

    if (
      not force_refresh
      and self._api_token
      and self._api_token_expiry - TOKEN_REFRESH_MARGIN > time.time()
    ):
      return True

    def _oauth():
      return gpsoauth.perform_oauth(
        self._email,
        self._master_token,
        self._android_id,
        service=OAUTH_SERVICE,
        app=GOOGLE_HOME_APP,
        client_sig=GOOGLE_HOME_CLIENT_SIG,
      )

    try:
      response = await asyncio.wait_for(asyncio.to_thread(_oauth), GPSOAUTH_TIMEOUT)
    except asyncio.TimeoutError as error:
      raise ConnectionError(f"Timed out contacting Google authentication: {error}") from error
    except Exception as error:
      raise ConnectionError(f"Google authentication token request failed: {error}") from error

    if not isinstance(response, dict):
      raise ConnectionError("Malformed response from Google authentication")

    error = response.get("Error") or response.get("error")
    if isinstance(error, str) and error.casefold() == "badauthentication":
      raise GoogleWifiAuthError("Google rejected the stored master token")

    token = response.get("Auth")
    if not token:
      raise GoogleWifiAuthError(
        f"Google did not return an access token: {error or 'unknown error'}"
      )

    try:
      lifetime = int(response.get("ExpiresInDurationSec", 3600))
    except (TypeError, ValueError):
      lifetime = 3600

    self._api_token = token
    self._api_token_expiry = time.time() + max(lifetime, 0)

    return True

  async def _refresh_token_once(self, headers):
    """Force a token re-mint and update the Authorization header in place."""
    await self.get_api_token(force_refresh=True)
    if isinstance(headers, dict):
      headers["Authorization"] = f"Bearer {self._api_token}"

  async def connect(self):
    """Authenticate to the Google Wifi services."""
    await self.get_api_token()
    return bool(self._api_token)

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
      system_metrics = await self.get_realtime_metrics(this_system["id"])

      try:
        systems[this_system["id"]]["status"] = system_status["wanConnectionStatus"]
        systems[this_system["id"]]["groupTraffic"] = system_metrics.get("groupTraffic",None)
      except KeyError as error:
        raise GoogleWifiException(error)

      blocking_policies = {}
      family_hub_settings = this_system["groupSettings"].get("familyHubSettings") or {}
      if family_hub_settings.get("stationPolicies"):
        for blocking_policy in family_hub_settings["stationPolicies"]:
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
      station_ids = []
      
      try:
        for this_device in devices_list["stations"]:
          devices[this_device["id"]] = this_device
          station_ids.append(this_device["id"])
          device_paused = False

          if blocking_policies.get(this_device["id"]):
            expire_date = dateutil.parser.parse(blocking_policies[this_device["id"]]["blockingPolicy"]["expiryTimestamp"])
            
            if expire_date > datetime.datetime.now(datetime.timezone.utc) or expire_date.timestamp() == 0:
              device_paused = True

          devices[this_device["id"]]["paused"] = device_paused
      except KeyError as error:
        raise GoogleWifiException(error)

      sensitive_info = await self.get_sensitive_info(system_id=this_system["id"], station_ids=station_ids)                                        
      for this_station in sensitive_info:
        if this_station["stationId"] in devices:
          devices[this_station["stationId"]]["macAddress"] = this_station.get("macAddress",{})

      if system_metrics.get("stationMetrics"):
        for this_station in system_metrics.get("stationMetrics"):
          if this_station["station"]["id"] in devices:
            devices[this_station["station"]["id"]]["traffic"] = this_station.get("traffic",{})

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
      data = {"enable": True, "clear_results": True, "timeout": 5}
      headers = GH_HEADERS
      headers["Host"] = host
      headers["cast-local-authorization-token"] = token

      await self.post_api(url=url,headers=headers,json_payload=data)
      await asyncio.sleep(5)

      url = f"https://{host}:8443/setup/bluetooth/scan_results"
      
      response = await self.get_api(url=url,headers=headers)

      return response

  async def create_wan_speedtest(self, system_id:str):
    """Start a speed test operation on a system."""
    if await self.connect():
      url = f"https://googlehomefoyer-pa.googleapis.com/v2/groups/{system_id}/wanSpeedTest"
      headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {self._api_token}"
      }
      payload = {}
      params = (
        ('prettyPrint', 'false'),
      )

      response = await self.post_api(url=url,headers=headers,payload=payload,params=params)
      operation_id = response["operation"]["operationId"]

      return operation_id

  async def check_operation(self, operation_id: str):
    """Check the status of a speed test operation."""
    if await self.connect():
      url = f"https://googlehomefoyer-pa.googleapis.com/v2/operations/{operation_id}"
      headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {self._api_token}"
      }
      payload = {}
      params = (
        ('prettyPrint', 'false'),
      )

      return await self.get_api(url=url,headers=headers,payload=payload,params=params)

  async def speed_test_results(self, system_id:str):
    """Retrieve the speed test results."""
    if await self.connect():
      url = f"https://googlehomefoyer-pa.googleapis.com/v2/groups/{system_id}/speedTestResults"
      headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {self._api_token}"
      }
      payload = {}
      params = (
        ('prettyPrint', 'false'),
        ('maxResultCount', 1)
      )

      response = await self.get_api(url=url,headers=headers,payload=payload,params=params)

      return response["speedTestResults"]

  async def run_speed_test(self, system_id:str):
    """Run a speed test and return the results."""
    if await self.connect():
      operation_id = await self.create_wan_speedtest(system_id=system_id)

      status = await self.check_operation(operation_id)
      status = status["operationState"]

      while status != "DONE":
        status = await self.check_operation(operation_id)
        status = status["operationState"]
        await asyncio.sleep(5)

      results = await self.speed_test_results(system_id=system_id)
      return results[0]
      
  async def start_retrieve_sensitive_info(self, system_id:str, station_ids:list):
    """Start the request to return the device sensitive information."""
    if await self.connect():
      url = f"https://googlehomefoyer-pa.googleapis.com/v2/groups/{system_id}/stations/operations/sensitiveInfo"

      headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {self._api_token}"
      }
      json_payload = {"stationIds":station_ids}
      params = (
        ('prettyPrint', 'false'),
      )

      response = await self.post_api(url=url,headers=headers,json_payload=json_payload,params=params)
      operation_id = response.get("operation",[]).get("operationId")

      return operation_id

  async def sensitive_info_results(self, operation_id:str):
    """Return the results of the sensitive info request."""
    if await self.connect():
      url = f"https://googlehomefoyer-pa.googleapis.com/v2/operations/{operation_id}/sensitiveInfo"
      params = (
        ('prettyPrint', 'false'),
      )
      headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {self._api_token}"
      }
      payload = {}

      return await self.get_api(url=url, headers=headers, payload=payload, params=params)

  async def get_sensitive_info(self, system_id:str, station_ids:list):
    """Return a full set of sensitive info on the system."""
    if await self.connect():
      operation_id = await self.start_retrieve_sensitive_info(
        system_id=system_id,station_ids=station_ids
      )

      status = await self.check_operation(operation_id)
      status = status["operationState"]

      while status != "DONE":
        status = await self.check_operation(operation_id)
        status = status["operationState"]
        await asyncio.sleep(5)

      results = await self.sensitive_info_results(operation_id=operation_id)
      return results.get("stationSensitiveInfos",[])

  async def get_realtime_metrics(self, system_id:str):
    """Return real-time metrics from the system."""
    if await self.connect():
      url =  f"https://googlehomefoyer-pa.googleapis.com/v2/groups/{system_id}/realtimeMetrics"
      params = (
        ('prettyPrint', 'false'),
      )
      headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {self._api_token}"
      }
      payload = {}

      return await self.get_api(url=url, headers=headers, payload=payload, params=params)
    

class GoogleWifiException(Exception):
  """Platform not ready exception."""
  pass

class GoogleWifiAuthError(Exception):
  """Stored Google credentials were rejected; re-authentication required."""
  pass

class GoogleHomeUpdateFailed(Exception):
  """Google Home Update failed, token refresh required."""

class GoogleHomeIgnoreDevice(Exception):
  """Google Home can't get data, ignore it."""
