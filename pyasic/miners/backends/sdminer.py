from typing import Any, Awaitable, Callable, List, Optional

from pyasic.config import MinerConfig
from pyasic.data import Fan, HashBoard, X19Error
from pyasic.data.error_codes import MinerErrorData
from pyasic.data.network import MinerNetworkConfig
from pyasic.data.pools import PoolMetrics, PoolUrl
from pyasic.device.algorithm import AlgoHashRate
from pyasic.errors import APIError
from pyasic.miners.backends.utils import (
    apply_antminer_temperature_layout,
    clean_network_value,
    get_antminer_temperature_layout,
    normalize_antminer_like_serial_number,
    parse_bitmain_network_info,
)
from pyasic.miners.data import (
    DataFunction,
    DataLocations,
    DataOptions,
    RPCAPICommand,
    WebAPICommand,
)
from pyasic.miners.device.firmware import SDMinerFirmware
from pyasic.rpc.bmminer import BMMinerRPCAPI
from pyasic.web.sdminer import SDMinerWebAPI

# any other status, known or added later, is not mining
SDMINER_MINING_STATUSES = ("mining", "tuning")
SDMINER_VALID_LICENSE_STATE = "valid"
SDMINER_TEMPERATURE_RAW_SOURCE = "sdminer"
# /system/v1 scripts answer HTTP 200 on a failed write too; only this value
# in `stats` means the write took
SDMINER_WRITE_SUCCESS = "success"
# category -> (web command, file extension, log type); passed on unread, so a
# layout change in the firmware cannot break the download
SDMINER_LOG_SOURCES = {
    "current": ("logs", "json", "flat"),
    "history": ("support_bundle", "tar.gz", "compressed"),
}

SDMINER_DATA_LOC = DataLocations(
    **{
        str(DataOptions.MAC): DataFunction(
            "_get_mac",
            [WebAPICommand("web_system", "system")],
        ),
        str(DataOptions.API_VERSION): DataFunction(
            "_get_api_ver",
            [RPCAPICommand("rpc_version", "version")],
        ),
        str(DataOptions.FW_VERSION): DataFunction(
            "_get_fw_ver",
            [WebAPICommand("web_system_info", "system_info")],
        ),
        str(DataOptions.HOSTNAME): DataFunction(
            "_get_hostname",
            [WebAPICommand("web_system", "system")],
        ),
        str(DataOptions.SERIAL_NUMBER): DataFunction(
            "_get_serial_number",
            [WebAPICommand("web_system", "system")],
        ),
        str(DataOptions.CONTROL_BOARD): DataFunction(
            "_get_control_board",
            [WebAPICommand("web_system", "system")],
        ),
        str(DataOptions.HASHRATE): DataFunction(
            "_get_hashrate",
            [WebAPICommand("web_overview", "overview")],
        ),
        str(DataOptions.EXPECTED_HASHRATE): DataFunction(
            "_get_expected_hashrate",
            [WebAPICommand("web_hashboards", "hashboards")],
        ),
        str(DataOptions.HASHBOARDS): DataFunction(
            "_get_hashboards",
            [
                WebAPICommand("web_hashboards", "hashboards"),
                WebAPICommand("web_system", "system"),
            ],
        ),
        str(DataOptions.TEMPERATURE_RAW): DataFunction(
            "_get_temperature_raw",
            [WebAPICommand("web_hashboards", "hashboards")],
        ),
        str(DataOptions.WATTAGE): DataFunction(
            "_get_wattage",
            [WebAPICommand("web_overview", "overview")],
        ),
        str(DataOptions.FANS): DataFunction(
            "_get_fans",
            [WebAPICommand("web_overview", "overview")],
        ),
        str(DataOptions.ERRORS): DataFunction(
            "_get_errors",
            [WebAPICommand("web_overview", "overview")],
        ),
        str(DataOptions.FAULT_LIGHT): DataFunction(
            "_get_fault_light",
            [WebAPICommand("web_find_miner", "find_miner")],
        ),
        str(DataOptions.IS_MINING): DataFunction(
            "_is_mining",
            [WebAPICommand("web_overview", "overview")],
        ),
        str(DataOptions.UPTIME): DataFunction(
            "_get_uptime",
            [WebAPICommand("web_overview", "overview")],
        ),
        str(DataOptions.POOLS): DataFunction(
            "_get_pools",
            [WebAPICommand("web_pools", "pools")],
        ),
        str(DataOptions.CONFIG): DataFunction(
            "_get_config",
            [
                WebAPICommand("web_miner_config", "miner_config"),
                WebAPICommand("web_overview", "overview"),
            ],
        ),
        str(DataOptions.NETWORK): DataFunction(
            "_get_network",
            [WebAPICommand("web_network", "network")],
        ),
    }
)


def _find_value(data: Any, *keys: Any) -> Any:
    for key in keys:
        try:
            data = data[key]
        except (LookupError, TypeError):
            return None
    return data


class SDMiner(SDMinerFirmware):
    """Handler for Antminers running GridFW, whose sdminer process replaces the
    stock cgi endpoints with a JSON web API. Of the controls only the locator
    light and the log download are implemented."""

    _web_cls = SDMinerWebAPI
    web: SDMinerWebAPI

    _rpc_cls = BMMinerRPCAPI
    rpc: BMMinerRPCAPI

    data_locations = SDMINER_DATA_LOC

    supports_shutdown = False
    supports_power_modes = False

    async def get_config(self) -> MinerConfig:
        config = await self._get_config()
        if config is not None:
            self.config = config
        return self.config

    async def fault_light_on(self) -> Optional[bool]:
        return await self._set_fault_light(True)

    async def fault_light_off(self) -> Optional[bool]:
        return await self._set_fault_light(False)

    async def _set_fault_light(self, enabled: bool) -> Optional[bool]:
        # answers the light state the write left, as the stock handlers do;
        # None marks a write the firmware did not confirm
        answer = await self.web.set_find_miner(enabled)
        if (
            answer.get("stats") != SDMINER_WRITE_SUCCESS
            or answer.get("enabled") is not enabled
        ):
            return None
        self.light = enabled
        return enabled

    async def download_logs(self, category: str = "history") -> dict:
        if category not in SDMINER_LOG_SOURCES:
            raise ValueError(
                f"category must be one of {list(SDMINER_LOG_SOURCES)}, got {category!r}"
            )
        command, ext, log_type = SDMINER_LOG_SOURCES[category]
        content = await getattr(self.web, command)()
        if not content:
            error = self.web.transport_errors.get(command)
            return {
                "success": False,
                "message": f"failed to download {category} logs: {error or 'empty body'}",
            }
        return {
            "success": True,
            "message": f"downloaded {category} logs",
            "data": {"content": content, "ext": ext, "log_type": log_type},
        }

    ##################################################
    ### DATA GATHERING FUNCTIONS (get_{some_data}) ###
    ##################################################

    @staticmethod
    async def _get_web_answer(
        request: Callable[[], Awaitable[Any]], answer: Any
    ) -> Any:
        return answer if answer is not None else await request()

    def _build_hashrate(self, hashrate: Any, rate_key: str) -> Optional[AlgoHashRate]:
        rate = _find_value(hashrate, rate_key)
        if not isinstance(rate, (int, float)):
            return None
        unit_name = str(_find_value(hashrate, "unit") or "GH/s").split("/")[0].upper()
        unit = getattr(self.algo.unit, unit_name, self.algo.unit.GH)
        return self.algo.hashrate(rate=float(rate), unit=unit).into(
            self.algo.unit.default
        )

    async def _get_mac(self, web_system: dict = None) -> Optional[str]:
        web_system = await self._get_web_answer(self.web.system, web_system)
        mac = _find_value(web_system, "control_board", "mac")
        return mac.upper() if isinstance(mac, str) and mac else None

    async def _get_api_ver(self, rpc_version: dict = None) -> Optional[str]:
        if rpc_version is None:
            try:
                rpc_version = await self.rpc.version()
            except APIError:
                pass

        api_ver = _find_value(rpc_version, "VERSION", 0, "API")
        if api_ver is not None:
            self.api_ver = api_ver
        return self.api_ver

    async def _get_fw_ver(self, web_system_info: dict = None) -> Optional[str]:
        web_system_info = await self._get_web_answer(
            self.web.system_info, web_system_info
        )
        fw_ver = _find_value(web_system_info, "version")
        if fw_ver:
            self.fw_ver = fw_ver
        return self.fw_ver

    async def _get_hostname(self, web_system: dict = None) -> Optional[str]:
        web_system = await self._get_web_answer(self.web.system, web_system)
        return _find_value(web_system, "operating_system", "hostname") or None

    async def _get_serial_number(self, web_system: dict = None) -> Optional[str]:
        # GridFW leaves the whole-machine serial empty; only the hashboard
        # serials are reported
        web_system = await self._get_web_answer(self.web.system, web_system)
        return normalize_antminer_like_serial_number(
            _find_value(web_system, "miner", "serial")
        )

    async def _get_control_board(self, web_system: dict = None) -> Optional[str]:
        web_system = await self._get_web_answer(self.web.system, web_system)
        return _find_value(web_system, "control_board", "model") or None

    async def _get_hashrate(self, web_overview: dict = None) -> Optional[AlgoHashRate]:
        web_overview = await self._get_web_answer(self.web.overview, web_overview)
        return self._build_hashrate(_find_value(web_overview, "hashrate"), "current")

    async def _get_expected_hashrate(
        self, web_hashboards: dict = None
    ) -> Optional[AlgoHashRate]:
        # scaled from the boards present to the boards expected, so a missing
        # board lowers the hashrate but not what the hashrate is measured against
        web_hashboards = await self._get_web_answer(self.web.hashboards, web_hashboards)
        ideals = []
        for board in _find_value(web_hashboards, "hashboards") or []:
            if not board.get("present"):
                continue
            ideal = self._build_hashrate(board.get("hashrate"), "ideal")
            if ideal is not None:
                ideals.append(float(ideal.into(self.algo.unit.default)))
        expected_count = (
            _find_value(web_hashboards, "expected_count") or self.expected_hashboards
        )
        if not ideals or not expected_count:
            return None
        return self.algo.hashrate(
            rate=sum(ideals) / len(ideals) * expected_count,
            unit=self.algo.unit.default,
        )

    async def _get_hashboards(
        self, web_hashboards: dict = None, web_system: dict = None
    ) -> Optional[List[HashBoard]]:
        if self.expected_hashboards is None:
            return []

        web_hashboards = await self._get_web_answer(self.web.hashboards, web_hashboards)
        # without an answer, keep the default placeholder boards: returning
        # them would read as device data and clear the transport error
        if not web_hashboards:
            return None
        web_system = await self._get_web_answer(self.web.system, web_system)
        boards = _find_value(web_hashboards, "hashboards") or []
        board_count = max(
            [self.expected_hashboards]
            + [
                board["index"] + 1
                for board in boards
                if isinstance(board.get("index"), int)
            ]
        )
        hashboards = [
            HashBoard(slot=idx, expected_chips=self.expected_chips)
            for idx in range(board_count)
        ]
        serials = {
            item.get("index"): item.get("serial")
            for item in _find_value(web_system, "hashboard_serials") or []
        }
        layout = get_antminer_temperature_layout(self.raw_model, self.firmware)

        for board in boards:
            idx = board.get("index")
            if not isinstance(idx, int) or not board.get("present"):
                continue
            hashboard = hashboards[idx]
            hashboard.missing = False
            hashboard.hashrate = self._build_hashrate(
                board.get("hashrate"), "realtime_5s"
            )
            hashboard.chips = board.get("asic_count")
            hashboard.chip_frequency = board.get("frequency_average_mhz")
            hashboard.serial_number = normalize_antminer_like_serial_number(
                serials.get(idx)
            )
            temperatures = board.get("temperatures") or {}
            # the stock layout's temp_pcb and temp_chip are sdminer's board_c
            # and chip_c
            apply_antminer_temperature_layout(
                hashboard,
                {
                    "temp_pcb": temperatures.get("board_c"),
                    "temp_chip": temperatures.get("chip_c"),
                },
                layout,
            )
        return hashboards

    async def _get_temperature_raw(self, web_hashboards: dict = None) -> list[dict]:
        web_hashboards = await self._get_web_answer(self.web.hashboards, web_hashboards)
        temperature_raw = []
        for board in _find_value(web_hashboards, "hashboards") or []:
            temperatures = board.get("temperatures") or {}
            item: dict[str, Any] = {
                "source": SDMINER_TEMPERATURE_RAW_SOURCE,
                "chain_index": board.get("index"),
            }
            if "chip_c" in temperatures:
                item["temp_chip"] = temperatures["chip_c"]
            if "board_c" in temperatures:
                item["temp_pcb"] = temperatures["board_c"]
            temperature_raw.append(item)
        return temperature_raw

    async def _get_wattage(self, web_overview: dict = None) -> Optional[int]:
        web_overview = await self._get_web_answer(self.web.overview, web_overview)
        watts = _find_value(web_overview, "power", "watts")
        return int(watts) if isinstance(watts, (int, float)) else None

    async def _get_fans(self, web_overview: dict = None) -> List[Fan]:
        web_overview = await self._get_web_answer(self.web.overview, web_overview)
        return [
            Fan(speed=fan.get("rpm"))
            for fan in _find_value(web_overview, "fans") or []
            if fan.get("present")
        ]

    async def _get_errors(self, web_overview: dict = None) -> List[MinerErrorData]:
        web_overview = await self._get_web_answer(self.web.overview, web_overview)
        miner = _find_value(web_overview, "miner")
        if not isinstance(miner, dict):
            return []

        errors = []
        if miner.get("error_code"):
            errors.append(
                X19Error(
                    error_message=miner.get("error") or "miner error",
                    error_code=miner["error_code"],
                )
            )
        if miner.get("protection_code"):
            errors.append(
                X19Error(
                    error_message=miner.get("protection") or "miner protection",
                    error_code=miner["protection_code"],
                )
            )
        if miner.get("degraded"):
            errors.append(
                X19Error(
                    error_message=f"degraded: {miner.get('degraded_reason') or 'unknown'}"
                )
            )
        # an expired license makes the firmware force the stock work mode
        license_state = _find_value(web_overview, "license", "state")
        if license_state is not None and license_state != SDMINER_VALID_LICENSE_STATE:
            last_error = _find_value(web_overview, "license", "last_error")
            errors.append(
                X19Error(
                    error_message=f"license {license_state}"
                    + (f": {last_error}" if last_error else "")
                )
            )
        return errors

    async def _get_fault_light(self, web_find_miner: dict = None) -> Optional[bool]:
        web_find_miner = await self._get_web_answer(self.web.find_miner, web_find_miner)
        enabled = _find_value(web_find_miner, "enabled")
        if isinstance(enabled, bool):
            self.light = enabled
        return self.light

    async def _is_mining(self, web_overview: dict = None) -> Optional[bool]:
        web_overview = await self._get_web_answer(self.web.overview, web_overview)
        status = _find_value(web_overview, "miner", "status")
        if status is None:
            return None
        return status in SDMINER_MINING_STATUSES

    async def _get_uptime(self, web_overview: dict = None) -> Optional[int]:
        web_overview = await self._get_web_answer(self.web.overview, web_overview)
        elapsed = _find_value(web_overview, "elapsed_seconds")
        return int(elapsed) if isinstance(elapsed, (int, float)) else None

    async def _get_pools(self, web_pools: list = None) -> List[PoolMetrics]:
        web_pools = await self._get_web_answer(self.web.pools, web_pools)
        if not isinstance(web_pools, list):
            return []

        pools_data = []
        for pool in web_pools:
            if pool.get("enabled") is False:
                continue
            url = pool.get("url")
            last_share_time = pool.get("last_share_time")
            pools_data.append(
                PoolMetrics(
                    url=PoolUrl.from_str(url) if url else None,
                    user=pool.get("user") or pool.get("worker"),
                    index=pool.get("index"),
                    accepted=pool.get("accepted"),
                    rejected=pool.get("rejected"),
                    active=pool.get("active"),
                    alive=pool.get("state") == "ready",
                    # 0 means no share yet
                    last_share_ts=last_share_time or None,
                )
            )
        return pools_data

    async def _get_config(
        self, web_miner_config: dict = None, web_overview: dict = None
    ) -> Optional[MinerConfig]:
        web_miner_config = await self._get_web_answer(
            self.web.miner_config, web_miner_config
        )
        # the pools come only from the saved config: without it a config built
        # from the work mode alone would read as a miner with no pools
        if not web_miner_config:
            return None
        web_overview = await self._get_web_answer(self.web.overview, web_overview)
        return MinerConfig.from_sdminer(
            web_miner_config, _find_value(web_overview, "miner", "work_mode")
        )

    async def _get_network(
        self, web_network: dict = None
    ) -> Optional[MinerNetworkConfig]:
        web_network = await self._get_web_answer(self.web.network, web_network)
        network = parse_bitmain_network_info(web_network)
        if network is None:
            return None
        # the stock parser reads the saved conf_* gateway and dns, which stay
        # empty under DHCP; sdminer also reports the ones in effect
        return network.model_copy(
            update={
                "gateway": clean_network_value(web_network.get("gateway"))
                or network.gateway,
                "dns": clean_network_value(web_network.get("effective_dnsservers"))
                or network.dns,
            }
        )
