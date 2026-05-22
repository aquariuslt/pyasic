from __future__ import annotations

import asyncio
import gzip
import io
import json
import logging
import shutil
from pathlib import Path
from typing import Any

import aiofiles
import httpx

from pyasic import settings
from pyasic.web.base import BaseWebAPI, normalize_wattage_value


class SpiderOSWebAPI(BaseWebAPI):
    def __init__(self, ip: str) -> None:
        super().__init__(ip)
        self.username = "root"
        self.pwd = settings.get("default_antminer_web_password", "root")

    async def _update_firmware(self, file: Path, **parameters) -> dict:
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
                    data = await client.get(
                        url,
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
                    return data.json()
                except json.decoder.JSONDecodeError:
                    return {"success": False, "message": "Failed to decode JSON"}
            return {
                "success": False,
                "message": f"Unknown error occurred: {data.status_code, data.text}",
            }

    async def multicommand(
        self, *commands: str, ignore_errors: bool = False, allow_warning: bool = True
    ) -> dict:
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
        auth = httpx.DigestAuth(self.username, self.pwd)

        try:
            url = f"http://{self.ip}:{self.port}/cgi-bin/{command}.cgi"
            ret = await client.get(
                url,
                auth=auth,
                timeout=settings.get("api_function_timeout", 3),
            )
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
                return {"success": True, "data": data.text}
            return {
                "success": False,
                "message": f"Unknown error occurred: {data.status_code, data.text}",
            }

    async def get_miner_conf(self) -> dict:
        return await self.send_command("get_miner_conf")

    async def set_miner_conf(self, conf: dict) -> dict:
        return await self.send_command("set_miner_conf", **conf)

    async def blink(self, blink: bool) -> dict:
        if blink:
            return await self.send_command("blink", blink="true")
        return await self.send_command("blink", blink="false")

    async def reboot(self) -> dict:
        return await self.send_command("reboot")

    async def get_system_info(self) -> dict:
        return await self.send_command("get_system_info")

    async def get_miner_type(self) -> dict:
        return await self.send_command("miner_type")

    async def get_network_info(self) -> dict:
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
            return {
                "success": False,
                "message": f"Failed to create log file backup: code={data.status_code}, msg={data.text}",
            }

    async def _download_log_file(self, filename: str) -> dict | None:
        url = f"http://{self.ip}:{self.port}/log/{filename}"
        auth = httpx.DigestAuth(self.username, self.pwd)
        try:
            async with httpx.AsyncClient(transport=settings.transport()) as client:
                data = await client.get(url, auth=auth, timeout=30)
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
        log_backup_ret = await self._create_log_backup(log_list[-7:])
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
            return {
                "success": False,
                "message": f"Failed to download current log file: code={data.status_code}, msg={data.text}",
            }

    async def download_logs(self, category="history") -> dict | None:
        if category not in ["history", "current"]:
            raise ValueError("category must be either 'history' or 'current'")
        if category == "history":
            return await self._download_history_logs()
        return await self._download_current_logs()

    async def summary(self) -> dict:
        return await self.send_command("summary")

    async def get_blink_status(self) -> dict:
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
                    files={"firmware": file_content},
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
                        return {"success": True}
                    return {
                        "success": False,
                        "message": f"Unknown error: message={data.text}",
                    }
                except json.decoder.JSONDecodeError:
                    return {"success": False, "message": "Failed to decode JSON"}
            return {
                "success": False,
                "message": f"Unknown error with http failure: code={data.status_code}, message={data.text}",
            }

    async def update_firmware(self, file: Path, keep_settings: bool = True) -> dict:
        parameters = {"keep_settings": keep_settings}
        return await self._update_firmware(file, **parameters)

    async def get_serial_number(self) -> dict:
        response = await self._invoke_http_get("get_sn", 6060)
        if response.get("success") and response.get("data"):
            return {"serinum": response.get("data")}
        return {}

    async def get_wattage(self) -> dict:
        response = await self._invoke_http_get("miner_power", 6060)
        if response.get("success") and response.get("data"):
            wattage = normalize_wattage_value(response.get("data"))
            if wattage is not None:
                return {"wattage": wattage}

        return {}
