from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import requests

from pyasic import settings
from pyasic.web.base import BaseWebAPI


class HttpClient:
    def __init__(self):
        self.session = requests.Session()

    def set_digest_auth(self, username: str, password: str):
        self.session.auth = requests.auth.HTTPDigestAuth(username, password)

    def unset_auth(self):
        self.session.auth = None

    async def get(
        self, url: str, params: dict = None, timeout=None
    ) -> requests.Response:
        resp = await asyncio.to_thread(
            self.session.get,
            url,
            params=params,
            verify=False,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp

    async def post(
        self, url: str, params: dict, json_: Any = None, timeout=None
    ) -> requests.Response:
        resp = await asyncio.to_thread(
            self.session.post,
            url,
            params=params,
            json=json_,
            verify=False,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp


class BitfufuAntminerWebAPI(BaseWebAPI):
    def __init__(self, ip: str) -> None:
        """Initialize the Bitfufu Antminer API client with a specific IP address.

        Args:
            ip (str): IP address of the Antminer device.
        """
        super().__init__(ip)
        self.username = "root"
        self.pwd = settings.get("default_antminer_web_password", "root")

    async def send_command(
        self,
        command: str | bytes,
        ignore_errors: bool = False,
        allow_warning: bool = True,
        privileged: bool = False,
        **parameters: Any,
    ) -> dict:
        """Send a command to the Antminer device using HTTP digest authentication.

        Args:
            command (str | bytes): The CGI command to send.
            ignore_errors (bool): If True, ignore any HTTP errors.
            allow_warning (bool): If True, proceed with warnings.
            privileged (bool): If set to True, requires elevated privileges.
            **parameters: Arbitrary keyword arguments to be sent as parameters in the request.

        Returns:
            dict: The JSON response from the device or an empty dictionary if an error occurs.
        """
        url = f"http://{self.ip}:{self.port}/cgi-bin/{command}.cgi"
        auth = httpx.DigestAuth(self.username, self.pwd)
        try:
            async with httpx.AsyncClient(transport=settings.transport()) as client:

                if parameters:
                    data = await client.post(
                        url,
                        auth=auth,
                        timeout=settings.get("api_function_timeout", 3),
                        json=parameters,
                    )
                else:
                    data = await client.get(url, auth=auth)
        except httpx.HTTPError as e:
            return {
                "success": False,
                "message": f"HTTP error occurred: {type(e), str(e)}",
            }
        else:
            if data.status_code == 200:
                try:
                    return data.json()
                except json.decoder.JSONDecodeError:
                    return {"success": False, "message": "Failed to decode JSON"}
            else:
                return {
                    "success": False,
                    "message": f"Unknown error occurred: {data.status_code, data.text}",
                }

    async def multicommand(
        self, *commands: str, ignore_errors: bool = False, allow_warning: bool = True
    ) -> dict:
        """Execute multiple commands simultaneously.

        Args:
            *commands (str): Multiple command strings to be executed.
            ignore_errors (bool): If True, ignore any HTTP errors.
            allow_warning (bool): If True, proceed with warnings.

        Returns:
            dict: A dictionary containing the results of all commands executed.
        """
        async with httpx.AsyncClient(transport=settings.transport()) as client:
            tasks = [
                asyncio.create_task(self._handle_multicommand(client, command))
                for command in commands
            ]
            all_data = await asyncio.gather(*tasks)

        data = {}
        for item in all_data:
            data.update(item)

        data["multicommand"] = True
        return data

    async def get_network_info(self) -> dict:
        """Retrieve network configuration information from the miner.

        Returns:
            dict: A dictionary containing the network configuration of the miner.
        """
        return await self.send_command("get_network_info")

    async def summary(self) -> dict:
        """Get a summary of the miner's status and performance.

        Returns:
            dict: A summary of the miner's current operational status.
        """
        return await self.send_command("summary")

    async def get_blink_status(self) -> dict:
        """Check the status of the LED blinking on the miner.

        Returns:
            dict: A dictionary indicating whether the LED is currently blinking.
        """
        return await self.send_command("get_blink_status")

    async def get_miner_conf(self) -> dict:
        """Retrieve the miner configuration from the Antminer device.

        Returns:
            dict: A dictionary containing the current configuration of the miner.
        """
        return await self.send_command("get_miner_conf")

    async def get_system_info(self) -> dict:
        """Retrieve system information from the miner.

        Returns:
            dict: A dictionary containing system information of the miner.
        """
        return await self.send_command("get_system_info")

    async def _handle_multicommand(
        self, client: httpx.AsyncClient, command: str
    ) -> dict:
        """Helper function for handling individual commands in a multicommand execution.

        Args:
            client (httpx.AsyncClient): The HTTP client to use for the request.
            command (str): The command to be executed.

        Returns:
            dict: A dictionary containing the response of the executed command.
        """
        auth = httpx.DigestAuth(self.username, self.pwd)

        try:
            url = f"http://{self.ip}/cgi-bin/{command}.cgi"
            ret = await client.get(url, auth=auth)
        except httpx.HTTPError:
            pass
        else:
            if ret.status_code == 200:
                try:
                    json_data = ret.json()
                    return {command: json_data}
                except json.decoder.JSONDecodeError:
                    pass
        return {command: {}}

    async def _invoke_http_get(self, path: str, port: int = None) -> dict:
        # WARNING(winkidney): should not use httpx but our custom client
        #  since the response from 6060 port is abnormal,
        #  only requests library is compatible with it
        url_port = self.port if port is None else port
        url = f"http://{self.ip}:{url_port}/{path}"

        try:
            client = HttpClient()
            async with asyncio.timeout(10):
                data = await client.get(
                    url,
                    timeout=settings.get("api_function_timeout", 3),
                )
        except requests.exceptions.HTTPError as e:
            return {
                "success": False,
                "message": f"HTTP error occurred: {type(e), str(e)}",
            }
        except (requests.exceptions.Timeout, asyncio.TimeoutError) as e:
            return {
                "success": False,
                "message": f"Timeout error occurred: {type(e), str(e)}",
            }
        else:
            if data.status_code == 200:
                return {
                    "success": True,
                    "data": data.text,
                }
            else:
                return {
                    "success": False,
                    "message": f"Unknown error occurred: {data.status_code, data.text}",
                }

    async def pools(self) -> dict:
        """Retrieve current pool information associated with the miner.

        Returns:
            dict: Information about the mining pools configured in the miner.
        """
        return await self.send_command("miner_pools")

    async def get_serial_number(self) -> dict:
        """Get the serial number of the miner.

        Returns:
            dict: A dictionary containing the serial number of the miner.
        """
        response = await self._invoke_http_get("get_sn", 6060)
        if response.get("success") and response.get("data"):
            return {
                "serinum": response.get("data"),
            }

        return {}

    async def get_wattage(self) -> dict:
        """Get the current power of the miner.

        Returns:
            dict: A dictionary containing the power of the miner.
        """
        response = await self._invoke_http_get("get_power", 6060)
        if response.get("success") and response.get("data"):
            power = response.get("data")
            if power is not None and power.isdigit():
                return {
                    "wattage": int(power),
                }

        return {}
