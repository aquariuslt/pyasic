from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from pyasic import settings
from pyasic.errors import APITransportError
from pyasic.web.base import BaseWebAPI

# The web server fronts two bases: /api/v1 proxies the sdminer process over
# loopback, /system/v1 is served by CGI scripts and keeps answering while the
# miner process is stopped
SDMINER_WEB_PATHS = {
    "overview": "/api/v1/overview",
    "hashboards": "/api/v1/hashboards",
    "system": "/api/v1/system",
    "pools": "/api/v1/pools",
    "miner_config": "/api/v1/config/miner",
    "logs": "/api/v1/logs",
    "system_info": "/system/v1/info",
    "network": "/system/v1/network",
    "find_miner": "/system/v1/find-miner",
    "support_bundle": "/system/v1/support-bundle",
}
# the firmware builds the bundle on request; the manual asks for a longer
# timeout than telemetry reads
SDMINER_SUPPORT_BUNDLE_TIMEOUT_SECONDS = 60


class SDMinerWebAPI(BaseWebAPI):
    """Client for the GridFW web server. Both bases take the web Digest
    credentials, the same root account as stock Antminer firmware."""

    def __init__(self, ip: str) -> None:
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
    ) -> Any:
        async with httpx.AsyncClient(transport=settings.transport()) as client:
            return await self._get(client, str(command))

    async def multicommand(
        self, *commands: str, ignore_errors: bool = False, allow_warning: bool = True
    ) -> dict:
        async with httpx.AsyncClient(transport=settings.transport()) as client:
            answers = await asyncio.gather(
                *[self._get(client, command) for command in commands]
            )
        data: dict[str, Any] = dict(zip(commands, answers))
        data["multicommand"] = True
        return data

    async def _request(
        self,
        client: httpx.AsyncClient,
        command: str,
        *,
        method: str = "GET",
        body: dict | None = None,
        timeout: float | None = None,
    ) -> httpx.Response | None:
        self._start_command(command)
        try:
            response = await client.request(
                method,
                f"http://{self.ip}:{self.port}{SDMINER_WEB_PATHS[command]}",
                auth=httpx.DigestAuth(self.username, self.pwd),
                json=body,
                timeout=(
                    timeout
                    if timeout is not None
                    else settings.get("api_function_timeout", 5)
                ),
            )
        except httpx.HTTPError as e:
            self._record_transport_error(command, e)
            return None
        if response.status_code != 200:
            self._record_transport_error(
                command, APITransportError(f"HTTP {response.status_code}")
            )
            return None
        return response

    def _decode_json(self, command: str, response: httpx.Response | None) -> Any:
        # some /system/v1 scripts answer JSON without a JSON content type, so
        # the text is parsed whatever the header says
        if response is None:
            return {}
        try:
            return json.loads(response.text)
        except json.JSONDecodeError:
            self._record_decode_failure(command)
            return {}

    async def _get(self, client: httpx.AsyncClient, command: str) -> Any:
        return self._decode_json(command, await self._request(client, command))

    async def _get_raw(
        self, command: str, timeout: float | None = None
    ) -> bytes | None:
        async with httpx.AsyncClient(transport=settings.transport()) as client:
            response = await self._request(client, command, timeout=timeout)
        return response.content if response is not None else None

    async def overview(self) -> dict:
        return await self.send_command("overview")

    async def hashboards(self) -> dict:
        return await self.send_command("hashboards")

    async def system(self) -> dict:
        return await self.send_command("system")

    async def pools(self) -> list | dict:
        return await self.send_command("pools")

    async def miner_config(self) -> dict:
        return await self.send_command("miner_config")

    async def system_info(self) -> dict:
        return await self.send_command("system_info")

    async def network(self) -> dict:
        return await self.send_command("network")

    async def find_miner(self) -> dict:
        return await self.send_command("find_miner")

    async def logs(self) -> bytes | None:
        """The miner, event and audit logs as the JSON document the firmware
        serves."""
        return await self._get_raw("logs")

    async def support_bundle(self) -> bytes | None:
        """The firmware's support bundle, a tar.gz."""
        return await self._get_raw(
            "support_bundle", timeout=SDMINER_SUPPORT_BUNDLE_TIMEOUT_SECONDS
        )

    async def set_find_miner(self, enabled: bool) -> dict:
        """Switch the locator light; answers the same shape as find_miner."""
        async with httpx.AsyncClient(transport=settings.transport()) as client:
            response = await self._request(
                client, "find_miner", method="POST", body={"enabled": enabled}
            )
        return self._decode_json("find_miner", response)
