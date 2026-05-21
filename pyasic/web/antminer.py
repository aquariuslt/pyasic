# ------------------------------------------------------------------------------
#  Copyright 2022 Upstream Data Inc                                            -
#                                                                              -
#  Licensed under the Apache License, Version 2.0 (the "License");             -
#  you may not use this file except in compliance with the License.            -
#  You may obtain a copy of the License at                                     -
#                                                                              -
#      http://www.apache.org/licenses/LICENSE-2.0                              -
#                                                                              -
#  Unless required by applicable law or agreed to in writing, software         -
#  distributed under the License is distributed on an "AS IS" BASIS,           -
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.    -
#  See the License for the specific language governing permissions and         -
#  limitations under the License.                                              -
# ------------------------------------------------------------------------------
from __future__ import annotations

import asyncio
import gzip
import io
import json
import logging
import shutil
import tarfile
from pathlib import Path
from typing import Any

import aiofiles
import httpx

from pyasic import settings
from pyasic.web.base import BaseWebAPI, normalize_wattage_value


class AntminerModernWebAPI(BaseWebAPI):
    def __init__(self, ip: str) -> None:
        """Initialize the modern Antminer API client with a specific IP address.

        Args:
            ip (str): IP address of the Antminer device.
        """
        super().__init__(ip)
        self.username = "root"
        self.pwd = settings.get("default_antminer_web_password", "root")

    async def _update_firmware(self, file: Path, **parameters) -> dict:
        """Upload a firmware file to the Antminer device.

        Args:
            file (Path): Path to the firmware file to be uploaded.

        Returns:
            dict: A dictionary response from the device after the upload.
        """
        command = "upgrade"

        async with aiofiles.open(file, "rb") as firmware:
            file_content = await firmware.read()

        url = f"http://{self.ip}:{self.port}/cgi-bin/{command}.cgi"
        auth = httpx.DigestAuth(self.username, self.pwd)
        try:
            async with httpx.AsyncClient(transport=settings.transport()) as client:
                data = await client.post(
                    url,
                    auth=auth,
                    timeout=settings.get("api_function_timeout", 120),
                    files={
                        "firmware": (
                            file.name,
                            file_content,
                            "application/octet-stream",
                        )
                    },
                    data=parameters,
                )
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
        return {"success": False, "message": "Unknown error occurred"}

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
        url_port = self.port if port is None else port
        url = f"http://{self.ip}:{url_port}/{path}"

        try:
            async with httpx.AsyncClient(transport=settings.transport()) as client:
                data = await client.get(
                    url,
                    timeout=settings.get("api_function_timeout", 3),
                )
        except httpx.ConnectError as e:
            return {
                "success": False,
                "message": f"Connection error occurred: {type(e), str(e)}",
            }
        except httpx.HTTPError as e:
            return {
                "success": False,
                "message": f"HTTP error occurred: {type(e), str(e)}",
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

    async def get_miner_conf(self) -> dict:
        """Retrieve the miner configuration from the Antminer device.

        Returns:
            dict: A dictionary containing the current configuration of the miner.
        """
        return await self.send_command("get_miner_conf")

    async def set_miner_conf(self, conf: dict) -> dict:
        """Set the configuration for the miner.

        Args:
            conf (dict): A dictionary of configuration settings to apply to the miner.

        Returns:
            dict: A dictionary response from the device after setting the configuration.
        """
        return await self.send_command("set_miner_conf", **conf)

    async def blink(self, blink: bool) -> dict:
        """Control the blinking of the LED on the miner device.

        Args:
            blink (bool): True to start blinking, False to stop.

        Returns:
            dict: A dictionary response from the device after the command execution.
        """
        if blink:
            return await self.send_command("blink", blink="true")
        return await self.send_command("blink", blink="false")

    async def reboot(self) -> dict:
        """Reboot the miner device.

        Returns:
            dict: A dictionary response from the device confirming the reboot command.
        """
        return await self.send_command("reboot")

    async def get_system_info(self) -> dict:
        """Retrieve system information from the miner.

        Returns:
            dict: A dictionary containing system information of the miner.
        """
        return await self.send_command("get_system_info")

    async def get_miner_type(self) -> dict:
        """Retrieve miner type information such as model and control board."""
        return await self.send_command("miner_type")

    async def get_network_info(self) -> dict:
        """Retrieve network configuration information from the miner.

        Returns:
            dict: A dictionary containing the network configuration of the miner.
        """
        return await self.send_command("get_network_info")

    async def _create_log_backup(self, log_list: list) -> dict | None:
        command = "create_log_backup"
        url = f"http://{self.ip}:{self.port}/cgi-bin/{command}.cgi"
        auth = httpx.DigestAuth(self.username, self.pwd)
        try:
            async with httpx.AsyncClient(transport=settings.transport()) as client:
                data = await client.post(
                    url,
                    json=log_list,
                    auth=auth,
                    timeout=settings.get("api_function_timeout", 3),
                )
        except httpx.HTTPError as e:
            return {
                "success": False,
                "message": f"HTTP error occurred: {type(e), str(e)}",
            }
        else:
            if data.status_code == 200:
                try:
                    json_data = data.json()
                    return {
                        "success": json_data.get("stats") == "success",
                        "message": json_data.get("msg"),
                        "msg": json_data.get("msg"),
                    }
                except json.decoder.JSONDecodeError:
                    return {"success": False, "message": "Failed to decode JSON"}
            else:
                return {
                    "success": False,
                    "message": f"Failed to create log file backup: code={data.status_code}, msg={data.text}",
                }

    async def _download_log_file(self, filename: str) -> dict | None:
        url = f"http://{self.ip}:{self.port}/log/{filename}"
        auth = httpx.DigestAuth(self.username, self.pwd)
        try:
            async with httpx.AsyncClient(transport=settings.transport()) as client:
                data = await client.get(
                    url,
                    auth=auth,
                    timeout=30,  # downloading log file may take longer time
                )
        except httpx.HTTPError as e:
            return {
                "success": False,
                "message": f"HTTP error occurred: {type(e), str(e)}",
            }
        else:
            if data.status_code == 200:
                try:
                    gz_buffer = io.BytesIO()
                    tar_file = io.BytesIO(data.content)
                    with gzip.open(gz_buffer, "wb") as gz_file:
                        shutil.copyfileobj(tar_file, gz_file)
                    gz_buffer.seek(0)
                    return {
                        "success": True,
                        "message": "Log file downloaded successfully",
                        "data": {
                            "content": gz_buffer.getvalue(),
                            "ext": "tar.gz",
                            "log_type": "compressed",
                        },
                    }
                except Exception as e:
                    logging.exception("Error extracting/compressing log file")
                    return {
                        "success": False,
                        "message": f"Failed to extract/compress log file: {e}",
                    }
            else:
                return {
                    "success": False,
                    "message": f"Failed to download log file: code={data.status_code}, msg={data.text}",
                }

    async def _download_history_logs(self) -> dict | None:
        ret = await self.send_command("dlog")
        if not ret.get("dlog"):
            return {
                "success": False,
                "message": f"failed to fetch log list: {ret.get('message')}",
            }
        log_list = ret.get("log_list", [])
        log_list.sort()
        log_backup_ret = await self._create_log_backup(log_list[-7:])  # last 7 days
        success = log_backup_ret.get("success")
        if not success:
            return log_backup_ret
        filename = log_backup_ret.get("msg")
        return await self._download_log_file(filename)

    async def _download_current_logs(self) -> dict | None:
        command = "log"
        url = f"http://{self.ip}:{self.port}/cgi-bin/{command}.cgi"
        auth = httpx.DigestAuth(self.username, self.pwd)
        try:
            async with httpx.AsyncClient(transport=settings.transport()) as client:
                data = await client.post(
                    url,
                    auth=auth,
                    timeout=settings.get("api_function_timeout", 60),
                )
        except httpx.HTTPError as e:
            return {
                "success": False,
                "message": f"HTTP error occurred: {type(e), str(e)}",
            }
        else:
            if data.status_code == 200:
                return {
                    "success": True,
                    "message": "successfully retrieved current log",
                    "data": {
                        "content": data.text,
                        "ext": "log",
                        "log_type": "flat",
                    },
                }
            else:
                return {
                    "success": False,
                    "message": f"Failed to download current log file: code={data.status_code}, msg={data.text}",
                }

    async def download_logs(self, category="history") -> dict | None:
        if category not in ["history", "current"]:
            raise ValueError("category must be either 'history' or 'current'")
        if category == "history":
            return await self._download_history_logs()
        else:
            return await self._download_current_logs()

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

    async def set_network_conf(
        self,
        ip: str,
        dns: str,
        gateway: str,
        subnet_mask: str,
        hostname: str,
        protocol: int,
    ) -> dict:
        """Set the network configuration of the miner.

        Args:
            ip (str): IP address of the device.
            dns (str): DNS server IP address.
            gateway (str): Gateway IP address.
            subnet_mask (str): Network subnet mask.
            hostname (str): Hostname of the device.
            protocol (int): Network protocol used.

        Returns:
            dict: A dictionary response from the device after setting the network configuration.
        """
        return await self.send_command(
            "set_network_conf",
            ipAddress=ip,
            ipDns=dns,
            ipGateway=gateway,
            ipHost=hostname,
            ipPro=protocol,
            ipSub=subnet_mask,
        )

    async def update_config_lock(self, file: Path) -> dict:
        command = "upgrade"

        async with aiofiles.open(file, "rb") as firmware:
            file_content = await firmware.read()

        url = f"http://{self.ip}:{self.port}/cgi-bin/{command}.cgi"
        auth = httpx.DigestAuth(self.username, self.pwd)
        try:
            async with httpx.AsyncClient(transport=settings.transport()) as client:
                data = await client.post(
                    url,
                    auth=auth,
                    timeout=30,
                    files={
                        "firmware": file_content,
                    },
                )
        except httpx.HTTPError as e:
            return {
                "success": False,
                "message": f"HTTP error occurred: {type(e), str(e)}",
            }
        else:
            if data.status_code == 200:
                try:
                    json_data = data.json()
                    if json_data.get("code") == "U001" and json_data.get("msg") == "6":
                        return {
                            "success": True,
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"Unknown error: message={data.text}",
                        }
                except json.decoder.JSONDecodeError:
                    return {"success": False, "message": "Failed to decode JSON"}
            else:
                return {
                    "success": False,
                    "message": f"Unknown error with http failure: code={data.status_code}, message={data.text}",
                }

    async def update_firmware(self, file: Path, keep_settings: bool = True) -> dict:
        """Perform a system update by uploading a firmware file and sending a command to initiate the update."""

        parameters = {
            "keep_settings": keep_settings,
        }
        return await self._update_firmware(file, **parameters)

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
        response = await self._invoke_http_get("miner_power", 6060)
        if response.get("success") and response.get("data"):
            wattage = normalize_wattage_value(response.get("data"))
            if wattage is not None:
                return {
                    "wattage": wattage,
                }

        return {}


class AntminerOldWebAPI(BaseWebAPI):
    def __init__(self, ip: str) -> None:
        """Initialize the old Antminer API client with a specific IP address.

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
                        data=parameters,
                        auth=auth,
                        timeout=settings.get("api_function_timeout", 3),
                    )
                else:
                    data = await client.get(url, auth=auth)
        except httpx.HTTPError:
            pass
        else:
            if data.status_code == 200:
                try:
                    return data.json()
                except json.decoder.JSONDecodeError:
                    pass

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
        data = {k: None for k in commands}
        auth = httpx.DigestAuth(self.username, self.pwd)
        async with httpx.AsyncClient(transport=settings.transport()) as client:
            for command in commands:
                try:
                    url = f"http://{self.ip}/cgi-bin/{command}.cgi"
                    ret = await client.get(url, auth=auth)
                except httpx.HTTPError:
                    pass
                else:
                    if ret.status_code == 200:
                        try:
                            json_data = ret.json()
                            data[command] = json_data
                        except json.decoder.JSONDecodeError:
                            pass
        return data

    async def get_system_info(self) -> dict:
        """Retrieve system information from the miner.

        Returns:
            dict: A dictionary containing system information of the miner.
        """
        return await self.send_command("get_system_info")

    async def blink(self, blink: bool) -> dict:
        """Control the blinking of the LED on the miner device.

        Args:
            blink (bool): True to start blinking, False to stop.

        Returns:
            dict: A dictionary response from the device after the command execution.
        """
        if blink:
            return await self.send_command("blink", action="startBlink")
        return await self.send_command("blink", action="stopBlink")

    async def reboot(self) -> dict:
        """Reboot the miner device.

        Returns:
            dict: A dictionary response from the device confirming the reboot command.
        """
        return await self.send_command("reboot")

    async def get_blink_status(self) -> dict:
        """Check the status of the LED blinking on the miner.

        Returns:
            dict: A dictionary indicating whether the LED is currently blinking.
        """
        return await self.send_command("blink", action="onPageLoaded")

    async def get_miner_conf(self) -> dict:
        """Retrieve the miner configuration from the Antminer device.

        Returns:
            dict: A dictionary containing the current configuration of the miner.
        """
        return await self.send_command("get_miner_conf")

    async def set_miner_conf(self, conf: dict) -> dict:
        """Set the configuration for the miner.

        Args:
            conf (dict): A dictionary of configuration settings to apply to the miner.

        Returns:
            dict: A dictionary response from the device after setting the configuration.
        """
        return await self.send_command("set_miner_conf", **conf)

    async def stats(self) -> dict:
        """Retrieve detailed statistical data of the mining operation.

        Returns:
            dict: Detailed statistics of the miner's operation.
        """
        return await self.send_command("miner_stats")

    async def summary(self) -> dict:
        """Get a summary of the miner's status and performance.

        Returns:
            dict: A summary of the miner's current operational status.
        """
        return await self.send_command("miner_summary")

    async def pools(self) -> dict:
        """Retrieve current pool information associated with the miner.

        Returns:
            dict: Information about the mining pools configured in the miner.
        """
        return await self.send_command("miner_pools")

    async def update_firmware(self, file: Path, keep_settings: bool = True) -> dict:
        """Perform a system update by uploading a firmware file and sending a command to initiate the update."""

        async with aiofiles.open(file, "rb") as firmware:
            file_content = await firmware.read()

        parameters = {
            "file": (file.name, file_content, "application/octet-stream"),
            "filename": file.name,
            "keep_settings": keep_settings,
        }

        return await self.send_command(command="upgrade", **parameters)
