"""Read-only Nonce CGMiner telemetry, schema 2 (PROD-2126)."""

import math
import re
from decimal import Decimal, ROUND_HALF_UP

from pyasic.errors import APIError
from pyasic.data.boards import HashBoard
from pyasic.data.fans import Fan
from pyasic.data.pools import PoolMetrics
from pyasic.data.power_supplies import PowerSupply
from pyasic.device.algorithm.hashrate import AlgoHashRateType
from pyasic.miners.backends.cgminer import parse_cgminer_pools
from pyasic.miners.backends.utils import normalize_antminer_like_serial_number
from pyasic.miners.base import MinerDataReadResult
from pyasic.miners.data import DataFunction, DataLocations, DataOptions, RPCAPICommand
from pyasic.miners.device.firmware import NonceFirmware
from pyasic.rpc.nonce import NonceRPCAPI


def _location(method: str, *commands: str) -> DataFunction:
    return DataFunction(
        method, [RPCAPICommand(f"rpc_{command}", command) for command in commands]
    )


NONCE_DATA_LOC = DataLocations(
    serial_number=_location("_get_serial_number", "legacy_stats"),
    mac=_location("_get_mac", "legacy_stats"),
    api_ver=_location("_get_api_ver", "version"),
    fw_ver=_location("_get_fw_ver", "version"),
    hashrate=_location("_get_hashrate", "summary"),
    hashboards=_location("_get_hashboards", "stats"),
    temperature_raw=_location("_get_temperature_raw", "stats"),
    fans=_location("_get_fans", "stats"),
    uptime=_location("_get_uptime", "summary"),
    pools=_location("_get_pools", "pools"),
    is_mining=_location("_is_mining", "summary"),
    psus=_location("_get_psus", "legacy_stats"),
    voltage=_location("_get_voltage", "legacy_stats"),
    wattage=_location("_get_wattage", "legacy_stats"),
    config=DataFunction("_get_monitoring_config"),
)


class Nonce(NonceFirmware):
    data_locations = NONCE_DATA_LOC
    # Do not inherit stock HTTP, configuration writes or power-mode capabilities.
    _rpc_cls = NonceRPCAPI
    _web_cls = None
    _ssh_cls = None

    @staticmethod
    def _stats(response: dict | None) -> dict:
        response = response or {}
        if not isinstance(response.get("STATUS"), dict) or not isinstance(
            response.get("INFO"), dict
        ):
            raise ValueError("nested Nonce stats response unavailable")
        rows = response.get("STATS", [])
        if (
            not isinstance(rows, list)
            or len(rows) != 1
            or not isinstance(rows[0], dict)
        ):
            raise ValueError("missing or ambiguous Nonce telemetry schema 2")
        return rows[0]

    def _chains(self, stats: dict) -> list[tuple[int, dict]]:
        chains = stats.get("chain")
        if not isinstance(chains, list):
            raise ValueError("chain array unavailable")
        by_slot = {}
        for chain in chains:
            if not isinstance(chain, dict):
                raise ValueError("invalid chain object")
            slot = chain.get("index")
            if (
                type(slot) is not int
                or slot < 0
                or (
                    self.expected_hashboards is not None
                    and slot >= self.expected_hashboards
                )
                or slot in by_slot
            ):
                raise ValueError("invalid or duplicate physical chain index")
            by_slot[slot] = chain
        slots = (
            range(self.expected_hashboards)
            if self.expected_hashboards is not None
            else sorted(by_slot)
        )
        return [(slot, by_slot.get(slot, {})) for slot in slots]

    @staticmethod
    def _number(value: object) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value) if math.isfinite(value) else None

    @classmethod
    def _reading(cls, stats: dict, key: str, index: int) -> float | None:
        values = stats.get(key, [])
        if not isinstance(values, list) or index >= len(values):
            return None
        return cls._number(values[index])

    async def _get_serial_number(
        self, rpc_legacy_stats: dict | None = None
    ) -> str | None:
        if rpc_legacy_stats is None:
            try:
                rpc_legacy_stats = await self.rpc.legacy_stats()
            except APIError:
                pass
        serial = self._legacy_stats(rpc_legacy_stats, "Miner Serial").get(
            "Miner Serial"
        )
        return (
            normalize_antminer_like_serial_number(serial)
            if isinstance(serial, str)
            else None
        )

    async def _get_mac(self, rpc_legacy_stats: dict | None = None) -> str | None:
        if rpc_legacy_stats is None:
            try:
                rpc_legacy_stats = await self.rpc.legacy_stats()
            except APIError:
                pass
        stats = self._legacy_stats(rpc_legacy_stats, "MAC Error")
        error, mac = stats.get("MAC Error"), stats.get("MAC")
        if type(error) is not int or error != 0 or not isinstance(mac, str):
            return None
        if re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", mac) is None:
            return None
        octets = bytes.fromhex(mac.replace(":", ""))
        if octets[0] & 1 or not any(octets):
            return None
        return mac.lower()

    async def _get_api_ver(self, rpc_version: dict | None = None) -> str:
        if rpc_version is None:
            try:
                rpc_version = await self.rpc.version()
            except APIError:
                pass
        return str(rpc_version["VERSION"][0]["API"])

    async def _get_fw_ver(self, rpc_version: dict | None = None) -> str:
        if rpc_version is None:
            try:
                rpc_version = await self.rpc.version()
            except APIError:
                pass
        version = rpc_version["VERSION"][0]
        if version.get("Firmware") != "Nonce":
            raise ValueError("not Nonce firmware")
        return version["CGMiner"]

    @staticmethod
    def _summary(response: dict | None) -> dict:
        response = response or {}
        rows = response.get("SUMMARY")
        if (
            not isinstance(response.get("STATUS"), dict)
            or response["STATUS"].get("STATUS") != "S"
            or not isinstance(response.get("INFO"), dict)
            or not isinstance(rows, list)
            or len(rows) != 1
            or not isinstance(rows[0], dict)
        ):
            raise ValueError("nested Nonce summary response unavailable")
        return rows[0]

    async def _get_hashrate(self, rpc_summary: dict | None = None) -> AlgoHashRateType:
        if rpc_summary is None:
            try:
                rpc_summary = await self.rpc.summary()
            except APIError:
                pass
        summary = self._summary(rpc_summary)
        value = self._number(summary.get("rate_5s"))
        if value is None or value < 0 or summary.get("rate_unit") != "GH/s":
            raise ValueError("valid five-second Nonce hashrate unavailable")
        return self.algo.hashrate(rate=value, unit=self.algo.unit.GH).into(
            self.algo.unit.default
        )

    async def _get_uptime(self, rpc_summary: dict | None = None) -> int:
        if rpc_summary is None:
            try:
                rpc_summary = await self.rpc.summary()
            except APIError:
                pass
        elapsed = self._number(self._summary(rpc_summary).get("elapsed"))
        if elapsed is None or elapsed < 0 or not elapsed.is_integer():
            raise ValueError("invalid Nonce uptime")
        return int(elapsed)

    async def _get_monitoring_config(self) -> None:
        return None

    async def _get_pools(self, rpc_pools: dict | None = None) -> list[PoolMetrics]:
        if rpc_pools is None:
            try:
                rpc_pools = await self.rpc.pools()
            except APIError:
                pass
        return parse_cgminer_pools(rpc_pools)

    @staticmethod
    def _legacy_stats(response: dict | None, marker: str) -> dict:
        if not response:
            return {}
        statuses = response.get("STATUS", [])
        if (
            not isinstance(statuses, list)
            or not statuses
            or any(
                not isinstance(status, dict) or status.get("STATUS") != "S"
                for status in statuses
            )
        ):
            return {}
        rows = response.get("STATS", [])
        if not isinstance(rows, list):
            return {}
        candidates = [row for row in rows if isinstance(row, dict) and marker in row]
        return candidates[0] if len(candidates) == 1 else {}

    @classmethod
    def _psu_reading(cls, response: dict | None, kind: str, unit: str) -> float | None:
        stats = cls._legacy_stats(response, "PSU Identity Valid")
        age = cls._number(stats.get("PSU Sample Age ms"))
        value = cls._number(stats.get(f"PSU {kind} {unit}"))
        if (
            stats.get(f"PSU {kind} Valid") is not True
            or age is None
            or not 0 <= age <= 30000
            or value is None
            or value < 0
        ):
            return None
        # The per-measurement flag permits partial telemetry success; a previous
        # read error or a failed temperature channel does not invalidate power.
        return value

    async def _get_psus(
        self, rpc_legacy_stats: dict | None = None
    ) -> list[PowerSupply]:
        if rpc_legacy_stats is None:
            try:
                rpc_legacy_stats = await self.rpc.legacy_stats()
            except APIError:
                pass
        stats = self._legacy_stats(rpc_legacy_stats, "PSU Identity Valid")
        serial = normalize_antminer_like_serial_number(stats.get("PSU Serial"))
        if (
            stats.get("PSU Identity Valid") is True
            and isinstance(serial, str)
            and serial.strip()
        ):
            return [PowerSupply(serial_number=serial)]
        return []

    async def _get_voltage(self, rpc_legacy_stats: dict | None = None) -> float | None:
        if rpc_legacy_stats is None:
            try:
                rpc_legacy_stats = await self.rpc.legacy_stats()
            except APIError:
                pass
        return self._psu_reading(rpc_legacy_stats, "Voltage", "V")

    async def _get_wattage(self, rpc_legacy_stats: dict | None = None) -> int | None:
        if rpc_legacy_stats is None:
            try:
                rpc_legacy_stats = await self.rpc.legacy_stats()
            except APIError:
                pass
        power = self._psu_reading(rpc_legacy_stats, "Power", "W")
        if power is None:
            return None
        return int(Decimal(str(power)).to_integral_value(rounding=ROUND_HALF_UP))

    async def _get_hashboards(self, rpc_stats: dict | None = None) -> list[HashBoard]:
        if rpc_stats is None:
            try:
                rpc_stats = await self.rpc.stats()
            except APIError:
                pass
        stats = self._stats(rpc_stats)
        boards = []
        for slot, chain in self._chains(stats):
            pcb = [self._reading(chain, "temp_pcb", index) for index in (1, 3)]
            available = [value for value in pcb if value is not None]
            frequency = self._number(chain.get("freq_avg"))
            serial_number = (
                normalize_antminer_like_serial_number(chain.get("sn"))
                if chain.get("eeprom_loaded") is True
                else None
            )
            boards.append(
                HashBoard(
                    slot=slot,
                    missing=chain.get("asic_num") is None and serial_number is None,
                    expected_chips=self.expected_chips,
                    chips=chain.get("asic_num"),
                    serial_number=serial_number,
                    chip_frequency=(
                        frequency if frequency is not None and frequency >= 0 else None
                    ),
                    inlet_temp=self._reading(chain, "temp_pcb", 0),
                    outlet_temp=self._reading(chain, "temp_pcb", 2),
                    temp=sum(available) / len(available) if available else None,
                    chip_temp=None,
                )
            )
        return boards

    async def _get_temperature_raw(self, rpc_stats: dict | None = None) -> list[dict]:
        if rpc_stats is None:
            try:
                rpc_stats = await self.rpc.stats()
            except APIError:
                pass
        return [
            {
                "source": "nonce",
                "chain_index": slot,
                "temp_pcb": [
                    self._reading(chain, "temp_pcb", index) for index in range(4)
                ],
            }
            for slot, chain in self._chains(self._stats(rpc_stats))
        ]

    async def _get_fans(self, rpc_stats: dict | None = None) -> list[Fan]:
        if rpc_stats is None:
            try:
                rpc_stats = await self.rpc.stats()
            except APIError:
                pass
        stats = self._stats(rpc_stats)
        fans = stats.get("fan")
        if not isinstance(fans, list):
            return []
        result = []
        for index in range(
            self.expected_fans if self.expected_fans is not None else len(fans)
        ):
            rpm = self._reading(stats, "fan", index)
            result.append(Fan() if rpm is None or rpm < 0 else Fan(speed=round(rpm)))
        return result

    async def _is_mining(self, rpc_summary: dict | None = None) -> bool:
        return float(await self._get_hashrate(rpc_summary)) > 0

    async def get_data_with_errors(
        self,
        allow_warning: bool = False,
        include: list[str | DataOptions] | None = None,
        exclude: list[str | DataOptions] | None = None,
    ) -> MinerDataReadResult:
        result = await super().get_data_with_errors(
            allow_warning=allow_warning, include=include, exclude=exclude
        )
        if (
            "is_mining" in result.field_parse_errors
            and "is_mining" not in result.field_transport_errors
        ):
            result.data.is_mining = False
        return result
