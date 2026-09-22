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

import warnings
from abc import ABC, abstractmethod
from typing import Any

from pyasic.errors import (
    AUTH_FAILURE_MESSAGE,
    DECODE_FAILURE_MESSAGE,
    APITransportError,
    APIWarning,
)

# MinerData fields that some backends read through an endpoint of their own
# instead of the multicommand. A failure there is recorded under the field
# name, the only key that carries it back to the field it feeds
SERIAL_NUMBER_FIELD = "serial_number"
WATTAGE_FIELD = "wattage"


def normalize_wattage_value(value: Any) -> int | None:
    if value is None:
        return None

    if isinstance(value, int) and not isinstance(value, bool):
        return value

    power = str(value).strip()
    if power.startswith("miner power:"):
        power = power.split(":", 1)[-1].strip()

    if power.isdigit():
        return int(power)

    return None


class BaseWebAPI(ABC):
    def __init__(self, ip: str) -> None:
        # ip address of the miner
        self.ip = ip
        self.username = None
        self.pwd = None
        self.port = 80

        self.token = None
        # transport failures since the last clear, keyed by command. The
        # backends answer a failed request with an empty result, so this is
        # what tells a field the device never answered from one it answered
        # empty
        self.transport_errors: dict[str, Exception] = {}
        # requests sent and lost since the last clear, counted because a
        # command sent twice keeps only its last outcome above
        self.request_count = 0
        self.failure_count = 0

    def __new__(cls, *args, **kwargs):
        if cls is BaseWebAPI:
            raise TypeError(f"Only children of '{cls.__name__}' may be instantiated")
        return object.__new__(cls)

    def __repr__(self):
        return f"{self.__class__.__name__}: {str(self.ip)}"

    @abstractmethod
    async def send_command(
        self,
        command: str | bytes,
        ignore_errors: bool = False,
        allow_warning: bool = True,
        privileged: bool = False,
        **parameters: Any,
    ) -> dict:
        pass

    @abstractmethod
    async def multicommand(
        self, *commands: str, ignore_errors: bool = False, allow_warning: bool = True
    ) -> dict:
        pass

    def _record_transport_error(self, command: str | bytes, error: Exception) -> None:
        # one failure per request: a request that records twice (an error
        # status, then a body that will not parse) still failed once
        if str(command) not in self.transport_errors:
            self.failure_count += 1
        self.transport_errors[str(command)] = error

    def _start_command(self, command: str | bytes) -> None:
        """Count the command as sent and forget an earlier failure of it:
        each request decides its own transport outcome."""
        self.request_count += 1
        self.transport_errors.pop(str(command), None)

    def _record_decode_failure(self, command: str | bytes) -> None:
        self._record_transport_error(command, APITransportError(DECODE_FAILURE_MESSAGE))

    def _record_missing_token(self, command: str | bytes) -> None:
        """Record that this command was never sent, the login before it having
        failed."""
        self._record_transport_error(command, APITransportError(AUTH_FAILURE_MESSAGE))

    def _record_endpoint_failure(self, field: str, response: dict) -> None:
        """Record the failure of a request the backend made outside the
        multicommand, under the field that request feeds."""
        self._record_transport_error(
            field, APITransportError(str(response.get("message")))
        )

    def _clear_transport_errors(self) -> None:
        self.transport_errors.clear()
        self.request_count = 0
        self.failure_count = 0

    def _check_commands(self, *commands):
        allowed_commands = self.get_commands()
        return_commands = []
        for command in [*commands]:
            if command in allowed_commands:
                return_commands.append(command)
            else:
                warnings.warn(
                    f"""Removing incorrect command: {command}
If you are sure you want to use this command please use WebAPI.send_command("{command}", ignore_errors=True) instead.""",
                    APIWarning,
                )
        return return_commands

    @property
    def commands(self) -> list:
        return self.get_commands()

    def get_commands(self) -> list:
        """Get a list of command accessible to a specific type of web API on the miner.

        Returns:
            A list of all web commands that the miner supports.
        """
        return [
            func
            for func in
            # each function in self
            dir(self)
            if not func == "commands"
            if callable(getattr(self, func)) and
            # no __ or _ methods
            not func.startswith("__") and not func.startswith("_") and
            # remove all functions that are in this base class
            func
            not in [
                func for func in dir(BaseWebAPI) if callable(getattr(BaseWebAPI, func))
            ]
        ]
