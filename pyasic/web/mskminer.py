# ------------------------------------------------------------------------------
#  Copyright 2024 Upstream Data Inc                                            -
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
import json
import warnings
from typing import Any

import httpx

from pyasic import settings
from pyasic.errors import APIError, APITransportError
from pyasic.web.base import BaseWebAPI


class MSKMinerWebAPI(BaseWebAPI):
    def __init__(self, ip: str) -> None:
        super().__init__(ip)
        self.username = "admin"
        self.pwd = settings.get("default_mskminer_web_password", "root")

    async def multicommand(
        self, *commands: str, ignore_errors: bool = False, allow_warning: bool = True
    ) -> dict:
        tasks = {c: asyncio.create_task(getattr(self, c)()) for c in commands}
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        data = {}
        for command, result in zip(tasks, results):
            if isinstance(result, APIError):
                # on record by send_command; the batch goes on
                data[command] = {}
            elif isinstance(result, BaseException):
                raise result
            else:
                data[command] = result
        return data

    async def send_command(
        self,
        command: str | bytes,
        ignore_errors: bool = False,
        allow_warning: bool = True,
        privileged: bool = False,
        **parameters: Any,
    ) -> dict:
        async with httpx.AsyncClient(transport=settings.transport()) as client:
            try:
                # auth
                await client.post(
                    f"http://{self.ip}:{self.port}/admin/login",
                    data={"username": self.username, "password": self.pwd},
                )
            except httpx.HTTPError:
                warnings.warn(f"Could not authenticate with miner web: {self}")
            self._start_command(command)
            try:
                resp = await client.post(
                    f"http://{self.ip}:{self.port}/api/{command}", params=parameters
                )
                if not resp.status_code == 200:
                    self._record_transport_error(
                        command, APITransportError(f"HTTP {resp.status_code}")
                    )
                    if not ignore_errors:
                        raise APIError(f"Command failed: {command}")
                    warnings.warn(f"Command failed: {command}")
                try:
                    return resp.json()
                except json.JSONDecodeError:
                    self._record_decode_failure(command)
                    raise APIError(f"Command failed: {command}")
            except httpx.HTTPError as e:
                self._record_transport_error(command, e)
                raise APIError(f"Command failed: {command}")

    async def info_v1(self):
        return await self.send_command("info_v1")
