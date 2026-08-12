import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pyasic.config import MinerConfig, MiningModeConfig
from pyasic.data import Fan, HashBoard
from pyasic.data.error_codes import MinerErrorData, X19Error
from pyasic.data.pools import PoolMetrics, PoolUrl
from pyasic.device.algorithm import AlgoHashRate
from pyasic.data.network import MinerNetworkConfig, NetworkMode
from pyasic.errors import APIError
from pyasic.miners.backends.bmminer import BMMiner
from pyasic.miners.data import (
    DataFunction,
    DataLocations,
    DataOptions,
    RPCAPICommand,
    WebAPICommand,
)
from pyasic.miners.device.firmware import SpiderOSFirmware
from pyasic.miners.backends.utils import (
    parse_bitmain_network_info,
    build_bitmain_network_conf,
    is_bitmain_write_success,
    parse_last_share_to_timestamp,
    apply_antminer_temperature_layout,
    build_antminer_temperature_raw,
    get_antminer_temperature_layout,
    normalize_antminer_like_serial_number,
)
from pyasic.rpc.spideros import SpiderOSRPCAPI
from pyasic.ssh.antminer import AntminerModernSSH
from pyasic.web.spideros import SpiderOSWebAPI

SPIDER_OS_DATA_LOC = DataLocations(
    **{
        str(DataOptions.MAC): DataFunction(
            "_get_mac",
            [
                WebAPICommand("web_get_system_info", "get_system_info"),
                WebAPICommand("web_get_network_info", "get_network_info"),
            ],
        ),
        str(DataOptions.NETWORK): DataFunction(
            "_get_network",
            [WebAPICommand("web_get_network_info", "get_network_info")],
        ),
        str(DataOptions.API_VERSION): DataFunction(
            "_get_api_ver",
            [RPCAPICommand("rpc_version", "version")],
        ),
        str(DataOptions.FW_VERSION): DataFunction(
            "_get_fw_ver",
            [RPCAPICommand("rpc_version", "version")],
        ),
        str(DataOptions.WATTAGE): DataFunction(
            "_get_wattage",
            [WebAPICommand("web_get_system_info", "get_system_info")],
        ),
        str(DataOptions.CONTROL_BOARD): DataFunction(
            "_get_control_board",
            [WebAPICommand("web_get_miner_type", "miner_type")],
        ),
        str(DataOptions.HOSTNAME): DataFunction(
            "_get_hostname",
            [WebAPICommand("web_get_system_info", "get_system_info")],
        ),
        str(DataOptions.HASHRATE): DataFunction(
            "_get_hashrate",
            [RPCAPICommand("rpc_summary", "summary")],
        ),
        str(DataOptions.SERIAL_NUMBER): DataFunction(
            "_get_serial_number",
            [WebAPICommand("web_get_system_info", "get_system_info")],
        ),
        str(DataOptions.EXPECTED_HASHRATE): DataFunction(
            "_get_expected_hashrate",
            [RPCAPICommand("rpc_stats", "stats")],
        ),
        str(DataOptions.FANS): DataFunction(
            "_get_fans",
            [RPCAPICommand("rpc_stats", "stats")],
        ),
        str(DataOptions.ERRORS): DataFunction(
            "_get_errors",
            [WebAPICommand("web_summary", "summary")],
        ),
        str(DataOptions.FAULT_LIGHT): DataFunction(
            "_get_fault_light",
            [WebAPICommand("web_get_blink_status", "get_blink_status")],
        ),
        str(DataOptions.HASHBOARDS): DataFunction("_get_hashboards", []),
        str(DataOptions.IS_MINING): DataFunction(
            "_is_mining",
            [WebAPICommand("web_get_conf", "get_miner_conf")],
        ),
        str(DataOptions.UPTIME): DataFunction(
            "_get_uptime",
            [RPCAPICommand("rpc_stats", "stats")],
        ),
        str(DataOptions.POOLS): DataFunction(
            "_get_pools",
            [RPCAPICommand("rpc_pools", "pools")],
        ),
        str(DataOptions.CONFIG): DataFunction(
            "_get_config",
            [WebAPICommand("web_get_conf", "get_miner_conf")],
        ),
    }
)


class SpiderOSMiner(SpiderOSFirmware):

    _web_cls = SpiderOSWebAPI
    web: SpiderOSWebAPI

    _rpc_cls = SpiderOSRPCAPI
    rpc: SpiderOSRPCAPI

    _ssh_cls = AntminerModernSSH
    ssh: AntminerModernSSH

    data_locations = SPIDER_OS_DATA_LOC

    supports_shutdown = True
    supports_power_modes = True

    async def get_config(self) -> MinerConfig:
        return await self._get_config()

    async def _get_config(self, web_get_conf: dict = None) -> MinerConfig:
        if web_get_conf is None:
            try:
                web_get_conf = await self.web.get_miner_conf()
            except APIError:
                pass
        if web_get_conf:
            self.config = MinerConfig.from_am_modern(web_get_conf)
        return self.config

    async def _get_api_ver(self, rpc_version: dict = None) -> Optional[str]:
        if rpc_version is None:
            try:
                rpc_version = await self.rpc.version()
            except APIError:
                pass

        if rpc_version is not None:
            try:
                self.api_ver = rpc_version["VERSION"][0]["API"]
            except LookupError:
                pass

        return self.api_ver

    async def _get_fw_ver(self, rpc_version: dict = None) -> Optional[str]:
        if rpc_version is None:
            try:
                rpc_version = await self.rpc.version()
            except APIError:
                pass

        if rpc_version is not None:
            try:
                self.fw_ver = rpc_version["VERSION"][0]["CompileTime"]
            except LookupError:
                pass

        return self.fw_ver

    async def send_config(self, config: MinerConfig, user_suffix: str = None) -> None:
        self.config = config
        await self.web.set_miner_conf(config.as_am_modern(user_suffix=user_suffix))

    async def update_configuration_lock(self, file: Path) -> str:
        result = await self.web.update_config_lock(file=file)
        if result.get("success"):
            logging.info(
                "Configuration lock process completed successfully for SpiderOS."
            )
            return "Configuration lock update completed successfully."

        error_message = result.get("message", "Unknown error")
        logging.error(f"Configuration lock update failed. Response: {error_message}")
        raise ValueError(f"Configuration lock update failed. Response: {error_message}")

    async def upgrade_firmware(self, file: Path, keep_settings: bool = True) -> str:
        if not file:
            raise ValueError("File location must be provided for firmware upgrade.")

        try:
            result = await self.web.update_firmware(
                file=file, keep_settings=keep_settings
            )
            if result.get("success"):
                logging.info(
                    "Firmware upgrade process completed successfully for SpiderOS."
                )
                return "Firmware upgrade completed successfully."
            error_message = result.get("message", "Unknown error")
            logging.error(f"Firmware upgrade failed. Response: {error_message}")
            return f"Firmware upgrade failed. Response: {error_message}"
        except Exception as e:
            logging.error(
                f"An error occurred during the firmware upgrade process: {e}",
                exc_info=True,
            )
            raise

    async def fault_light_on(self) -> bool:
        data = await self.web.blink(blink=True)
        if data and data.get("code") == "B000":
            self.light = True
        return self.light

    async def fault_light_off(self) -> bool:
        data = await self.web.blink(blink=False)
        if data and data.get("code") == "B100":
            self.light = False
        return self.light

    async def reboot(self) -> bool:
        data = await self.web.reboot()
        if data:
            return True
        return False

    async def stop_mining(self) -> bool:
        cfg = await self.get_config()
        cfg.mining_mode = MiningModeConfig.sleep()
        await self.send_config(cfg)
        return True

    async def resume_mining(self) -> bool:
        cfg = await self.get_config()
        cfg.mining_mode = MiningModeConfig.normal()
        await self.send_config(cfg)
        return True

    async def _get_control_board(
        self, web_get_miner_type: dict = None
    ) -> Optional[str]:
        if self.control_board:
            return self.control_board

        if web_get_miner_type is None:
            try:
                web_get_miner_type = await self.web.get_miner_type()
            except APIError:
                return self.control_board

        if isinstance(web_get_miner_type, dict):
            control_board = web_get_miner_type.get("subtype")
            if control_board:
                self.control_board = control_board

        return self.control_board

    async def _get_serial_number(
        self, web_get_system_info: dict = None
    ) -> Optional[str]:
        if web_get_system_info is None:
            try:
                web_get_system_info = await self.web.get_system_info()
            except APIError:
                pass

        if web_get_system_info is not None and "serinum" in web_get_system_info:
            return normalize_antminer_like_serial_number(web_get_system_info["serinum"])

        try:
            web_custom_api_result = await self.web.get_serial_number()
            if web_custom_api_result is not None and "serinum" in web_custom_api_result:
                return normalize_antminer_like_serial_number(
                    web_custom_api_result["serinum"]
                )
        except APIError:
            pass

        return None

    async def _get_wattage(self, web_get_system_info: dict = None) -> Optional[int]:
        if web_get_system_info is None:
            try:
                web_get_system_info = await self.web.get_system_info()
            except APIError:
                pass

        if web_get_system_info is not None and "wattage" in web_get_system_info:
            return web_get_system_info["wattage"]

        try:
            web_custom_api_result = await self.web.get_wattage()
            if web_custom_api_result is not None and "wattage" in web_custom_api_result:
                return web_custom_api_result["wattage"]
        except APIError:
            pass

    async def _get_hostname(self, web_get_system_info: dict = None) -> Optional[str]:
        if web_get_system_info is None:
            try:
                web_get_system_info = await self.web.get_system_info()
            except APIError:
                pass

        if web_get_system_info is not None:
            try:
                return web_get_system_info["hostname"]
            except KeyError:
                pass

    async def _get_mac(
        self, web_get_system_info: dict = None, web_get_network_info: dict = None
    ) -> Optional[str]:
        if web_get_system_info is None:
            try:
                web_get_system_info = await self.web.get_system_info()
            except APIError:
                pass

        if web_get_system_info is not None:
            try:
                return web_get_system_info["macaddr"]
            except KeyError:
                pass

        if web_get_network_info is None:
            try:
                web_get_network_info = await self.web.get_network_info()
            except APIError:
                pass

        if web_get_network_info is not None:
            try:
                return web_get_network_info["macaddr"]
            except KeyError:
                pass

    async def _get_network(
        self, web_get_network_info: dict = None
    ) -> Optional[MinerNetworkConfig]:
        if web_get_network_info is None:
            try:
                web_get_network_info = await self.web.get_network_info()
            except APIError:
                pass

        return parse_bitmain_network_info(web_get_network_info)

    async def _get_errors(self, web_summary: dict = None) -> List[MinerErrorData]:
        if web_summary is None:
            try:
                web_summary = await self.web.summary()
            except APIError:
                pass

        errors = []
        if web_summary is not None:
            try:
                for item in web_summary["SUMMARY"][0]["status"]:
                    try:
                        if item["status"] != "s":
                            errors.append(X19Error(error_message=item["msg"]))
                    except KeyError:
                        continue
            except LookupError:
                pass
        return errors

    async def _get_hashrate(self, rpc_summary: dict = None) -> Optional[AlgoHashRate]:
        if rpc_summary is None:
            try:
                rpc_summary = await self.rpc.summary()
            except APIError:
                pass

        if rpc_summary is not None:
            try:
                return self.algo.hashrate(
                    rate=float(rpc_summary["SUMMARY"][0]["GHS 5s"]),
                    unit=self.algo.unit.GH,
                ).into(self.algo.unit.default)
            except (LookupError, ValueError, TypeError):
                pass

    async def _get_hashboards(self) -> List[HashBoard]:
        if self.expected_hashboards is None:
            return []

        hashboards = [
            HashBoard(slot=idx, expected_chips=self.expected_chips)
            for idx in range(self.expected_hashboards)
        ]

        try:
            rpc_stats = await self.rpc.stats(new_api=True)
        except APIError:
            return hashboards

        if rpc_stats is not None:
            try:
                for board in rpc_stats["STATS"][0]["chain"]:
                    hashboards[board["index"]].hashrate = self.algo.hashrate(
                        rate=board["rate_real"], unit=self.algo.unit.GH
                    ).into(self.algo.unit.default)
                    hashboards[board["index"]].chips = board["asic_num"]

                    apply_antminer_temperature_layout(
                        hashboards[board["index"]],
                        board,
                        get_antminer_temperature_layout(
                            self.raw_model,
                            self.firmware,
                        ),
                    )

                    hashboards[board["index"]].serial_number = board["sn"]
                    hashboards[board["index"]].missing = False
                    hashboards[board["index"]].chip_frequency = board["freq_avg"]
            except LookupError:
                pass
        return hashboards

    async def _get_temperature_raw(self) -> list[dict]:
        try:
            rpc_stats = await self.rpc.stats(new_api=True)
        except APIError:
            return []
        return build_antminer_temperature_raw("spideros", rpc_stats)

    async def _get_fans(self, rpc_stats: dict = None) -> List[Fan]:
        if self.expected_fans is None:
            return []

        if rpc_stats is None:
            try:
                rpc_stats = await self.rpc.stats()
            except APIError:
                pass

        fans = [Fan() for _ in range(self.expected_fans)]
        if rpc_stats is not None:
            try:
                fan_offset = -1

                for fan_num in range(1, 8, 4):
                    for _f_num in range(4):
                        f = rpc_stats["STATS"][1].get(f"fan{fan_num + _f_num}", 0)
                        if f and f != 0 and fan_offset == -1:
                            fan_offset = fan_num
                if fan_offset == -1:
                    fan_offset = 1

                for fan in range(self.expected_fans):
                    fans[fan].speed = rpc_stats["STATS"][1].get(
                        f"fan{fan_offset + fan}", 0
                    )
            except LookupError:
                pass

        return fans

    async def _get_fault_light(
        self, web_get_blink_status: dict = None
    ) -> Optional[bool]:
        if self.light:
            return self.light

        if web_get_blink_status is None:
            try:
                web_get_blink_status = await self.web.get_blink_status()
            except APIError:
                pass

        if web_get_blink_status is not None:
            try:
                self.light = web_get_blink_status["blink"]
            except KeyError:
                pass
        return self.light

    async def _get_expected_hashrate(
        self, rpc_stats: dict = None
    ) -> Optional[AlgoHashRate]:
        if rpc_stats is None:
            try:
                rpc_stats = await self.rpc.stats(new_api=True)
            except APIError:
                pass

        if rpc_stats is not None:
            try:
                expected_rate = rpc_stats["STATS"][1]["total_rateideal"]
                try:
                    rate_unit = rpc_stats["STATS"][1]["rate_unit"]
                except KeyError:
                    rate_unit = "GH"
                return self.algo.hashrate(
                    rate=float(expected_rate), unit=self.algo.unit.from_str(rate_unit)
                ).into(self.algo.unit.default)
            except LookupError:
                try:
                    rpc_stats = await self.rpc.stats(new_api=True)
                    expected_rate = rpc_stats["STATS"][1]["total_rateideal"]
                    try:
                        rate_unit = rpc_stats["STATS"][1]["rate_unit"]
                    except KeyError:
                        rate_unit = "GH"
                    return self.algo.hashrate(
                        rate=float(expected_rate),
                        unit=self.algo.unit.from_str(rate_unit),
                    ).into(self.algo.unit.default)
                except (APIError, LookupError):
                    pass

    async def set_static_ip(
        self,
        ip: str,
        dns: str,
        gateway: str,
        subnet_mask: str = None,
        hostname: str = None,
    ) -> bool:
        """Give the miner a static address.

        Args:
            ip: Address to set.
            dns: DNS servers to set.
            gateway: Gateway to set.
            subnet_mask: Subnet mask to set.  There is no default on purpose,
                guessing it writes the wrong mask onto miners off a /24.
            hostname: Hostname to keep, read from the miner when not given.

        Returns:
            Whether the miner accepted the write.
        """
        if hostname is None:
            hostname = await self.get_hostname()
        response = await self.web.set_network_conf(
            **build_bitmain_network_conf(
                NetworkMode.STATIC, ip, subnet_mask, gateway, dns, hostname
            )
        )
        return is_bitmain_write_success(response)

    async def set_dhcp(self, hostname: str = None) -> bool:
        """Hand the address back to DHCP.

        Args:
            hostname: Hostname to keep, read from the miner when not given.

        Returns:
            Whether the miner accepted the write.
        """
        if hostname is None:
            hostname = await self.get_hostname()
        response = await self.web.set_network_conf(
            **build_bitmain_network_conf(NetworkMode.DHCP, hostname=hostname)
        )
        return is_bitmain_write_success(response)

    async def set_hostname(self, hostname: str):
        cfg = await self.web.get_network_info()
        dns = cfg["conf_dnsservers"]
        gateway = cfg["conf_gateway"]
        ip = cfg["conf_ipaddress"]
        subnet_mask = cfg["conf_netmask"]
        protocol = 1 if cfg["conf_nettype"] == "DHCP" else 2
        await self.web.set_network_conf(
            ip=ip,
            dns=dns,
            gateway=gateway,
            subnet_mask=subnet_mask,
            hostname=hostname,
            protocol=protocol,
        )

    async def download_logs(self, category: str = "history") -> dict | None:
        try:
            data = await self.web.download_logs(category)
            return data
        except APIError:
            pass
        return {"success": False, "message": "Failed to download logs, unknown error."}

    async def _is_mining(self, web_get_conf: dict = None) -> Optional[bool]:
        if web_get_conf is None:
            try:
                web_get_conf = await self.web.get_miner_conf()
            except APIError:
                pass

        if web_get_conf is not None:
            try:
                if str(web_get_conf["bitmain-work-mode"]).isdigit():
                    return (
                        False if int(web_get_conf["bitmain-work-mode"]) == 1 else True
                    )
                return False
            except LookupError:
                pass

    async def _get_uptime(self, rpc_stats: dict = None) -> Optional[int]:
        if rpc_stats is None:
            try:
                rpc_stats = await self.rpc.stats()
            except APIError:
                pass

        if rpc_stats is not None:
            try:
                return int(rpc_stats["STATS"][1]["Elapsed"])
            except LookupError:
                pass

    async def _get_pools(self, rpc_pools: dict = None) -> List[PoolMetrics]:
        if rpc_pools is None:
            try:
                rpc_pools = await self.rpc.pools()
            except APIError:
                pass

        pools_data = []
        if rpc_pools is not None:
            try:
                pools = rpc_pools.get("POOLS", [])
                for pool_info in pools:
                    url = pool_info.get("URL")
                    pool_url = PoolUrl.from_str(url) if url else None
                    pool_data = PoolMetrics(
                        last_share_ts=parse_last_share_to_timestamp(
                            pool_info.get("Last Share Time", "0")
                        ),
                        accepted=pool_info.get("Accepted"),
                        rejected=pool_info.get("Rejected"),
                        difficulty_accepted=pool_info.get(
                            "Difficulty Accepted", pool_info.get("diffa")
                        ),
                        difficulty_rejected=pool_info.get(
                            "Difficulty Rejected", pool_info.get("diffr")
                        ),
                        difficulty_stale=pool_info.get(
                            "Difficulty Stale", pool_info.get("diffs")
                        ),
                        get_failures=pool_info.get("Get Failures"),
                        remote_failures=pool_info.get("Remote Failures"),
                        active=pool_info.get("Stratum Active"),
                        alive=pool_info.get("Status") == "Alive",
                        url=pool_url,
                        user=pool_info.get("User"),
                        index=pool_info.get("POOL"),
                    )
                    pools_data.append(pool_data)
            except LookupError:
                pass
        return pools_data
