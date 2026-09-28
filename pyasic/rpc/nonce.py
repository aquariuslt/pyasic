"""Read nested stats/summary and legacy MAC and optional PSU diagnostics."""

import asyncio
import json

from pyasic.errors import APIError
from pyasic.rpc.cgminer import CGMinerRPCAPI


class NonceRPCAPI(CGMinerRPCAPI):
    async def _send_bytes(
        self, data: bytes, *, port: int = None, timeout: int = 100
    ) -> bytes:
        # Keep the logical key through request accounting; translate only the wire command.
        request = json.loads(data)
        if request.get("command") == "legacy_stats":
            request["command"] = "stats"
            data = json.dumps(request).encode("utf-8")
        return await super()._send_bytes(data, port=port, timeout=timeout)

    @staticmethod
    def _load_api_data(data: bytes) -> dict:
        # The generic repair path changes quoted "nan"/"inf" into zero. These
        # must remain invalid measurements in Nonce snapshots.
        try:
            result = json.loads(data.removesuffix(b"\x00"))
        except (ValueError, UnicodeDecodeError) as error:
            raise APIError("invalid Nonce JSON response") from error
        if not isinstance(result, dict):
            raise APIError("invalid Nonce response envelope")
        return result

    async def stats(self) -> dict:
        return await self.send_command("stats", new_api=True)

    async def summary(self) -> dict:
        return await self.send_command("summary", new_api=True)

    async def legacy_stats(self) -> dict:
        return await self.send_command("legacy_stats")

    async def multicommand(self, *commands: str, allow_warning: bool = True) -> dict:
        commands = self._check_commands(*commands)
        regular = [
            command
            for command in commands
            if command not in {"stats", "summary", "legacy_stats"}
        ]
        tasks = {}
        if len(regular) == 1:
            tasks["single"] = self.send_command(regular[0], allow_warning=allow_warning)
        elif regular:
            tasks["regular"] = super().multicommand(
                *regular, allow_warning=allow_warning
            )
        for command in ("stats", "summary", "legacy_stats"):
            if command in commands:
                tasks[command] = self.send_command(
                    command,
                    allow_warning=allow_warning,
                    **({} if command == "legacy_stats" else {"new_api": True}),
                )
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        data = {"multicommand": True}
        for key, result in zip(tasks, results):
            if isinstance(result, (APIError, OSError, TimeoutError)):
                if key in {"stats", "summary", "legacy_stats"}:
                    if key not in self.transport_errors:
                        self._record_transport_error(key, result)
                    data[key] = [{}]
                continue
            if isinstance(result, BaseException):
                raise result
            if key == "single":
                data[regular[0]] = [result]
            elif key in {"stats", "summary", "legacy_stats"}:
                data[key] = [result]
            else:
                data.update(result)
        return data
