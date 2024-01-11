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

from typing import List, Optional, Union

from pyasic.API import APIError
from pyasic.config import MinerConfig, MiningModeConfig
from pyasic.data import Fan, HashBoard
from pyasic.data.error_codes import MinerErrorData, X19Error
from pyasic.miners.backends.bmminer import BMMiner
from pyasic.miners.backends.cgminer import CGMiner
from pyasic.miners.base import (
    DataFunction,
    DataLocations,
    DataOptions,
    RPCAPICommand,
    WebAPICommand,
)
from pyasic.web.antminer import AntminerModernWebAPI, AntminerOldWebAPI

ANTMINER_MODERN_DATA_LOC = DataLocations(
    **{
        str(DataOptions.MAC): DataFunction(
            "_get_mac", [WebAPICommand("web_get_system_info", "get_system_info")]
        ),
        str(DataOptions.API_VERSION): DataFunction(
            "_get_api_ver", [RPCAPICommand("api_version", "version")]
        ),
        str(DataOptions.FW_VERSION): DataFunction(
            "_get_fw_ver", [RPCAPICommand("api_version", "version")]
        ),
        str(DataOptions.HOSTNAME): DataFunction(
            "_get_hostname", [WebAPICommand("web_get_system_info", "get_system_info")]
        ),
        str(DataOptions.HASHRATE): DataFunction(
            "_get_hashrate", [RPCAPICommand("api_summary", "summary")]
        ),
        str(DataOptions.EXPECTED_HASHRATE): DataFunction(
            "_get_expected_hashrate", [RPCAPICommand("api_stats", "stats")]
        ),
        str(DataOptions.HASHBOARDS): DataFunction("_get_hashboards"),
        str(DataOptions.ENVIRONMENT_TEMP): DataFunction("_get_env_temp"),
        str(DataOptions.WATTAGE): DataFunction("_get_wattage"),
        str(DataOptions.WATTAGE_LIMIT): DataFunction("_get_wattage_limit"),
        str(DataOptions.FANS): DataFunction(
            "_get_fans", [RPCAPICommand("api_stats", "stats")]
        ),
        str(DataOptions.FAN_PSU): DataFunction("get_fan_psu"),
        str(DataOptions.ERRORS): DataFunction(
            "_get_errors", [WebAPICommand("web_summary", "summary")]
        ),
        str(DataOptions.FAULT_LIGHT): DataFunction(
            "_get_fault_light",
            [WebAPICommand("web_get_blink_status", "get_blink_status")],
        ),
        str(DataOptions.IS_MINING): DataFunction(
            "_is_mining", [WebAPICommand("web_get_conf", "get_miner_conf")]
        ),
        str(DataOptions.UPTIME): DataFunction(
            "_get_uptime", [RPCAPICommand("api_stats", "stats")]
        ),
        str(DataOptions.CONFIG): DataFunction("get_config"),
    }
)


class AntminerModern(BMMiner):
    def __init__(self, ip: str, api_ver: str = "0.0.0") -> None:
        super().__init__(ip, api_ver)
        # interfaces
        self.web = AntminerModernWebAPI(ip)

        # static data
        # data gathering locations
        self.data_locations = ANTMINER_MODERN_DATA_LOC
        # autotuning/shutdown support
        self.supports_shutdown = True

    async def get_config(self) -> MinerConfig:
        data = await self.web.get_miner_conf()
        if data:
            self.config = MinerConfig.from_am_modern(data)
        return self.config

    async def send_config(self, config: MinerConfig, user_suffix: str = None) -> None:
        self.config = config
        await self.web.set_miner_conf(config.as_am_modern(user_suffix=user_suffix))
        # if data:
        #     if data.get("code") == "M000":
        #         return
        #
        # for i in range(7):
        #     data = await self.get_config()
        #     if data == self.config:
        #         break
        #     await asyncio.sleep(1)

    async def fault_light_on(self) -> bool:
        data = await self.web.blink(blink=True)
        if data:
            if data.get("code") == "B000":
                self.light = True
        return self.light

    async def fault_light_off(self) -> bool:
        data = await self.web.blink(blink=False)
        if data:
            if data.get("code") == "B100":
                self.light = False
        return self.light

    async def reboot(self) -> bool:
        data = await self.web.reboot()
        if data:
            return True
        return False

    async def stop_mining(self) -> bool:
        cfg = await self.get_config()
        cfg.miner_mode = MiningModeConfig.sleep
        await self.send_config(cfg)
        return True

    async def resume_mining(self) -> bool:
        cfg = await self.get_config()
        cfg.miner_mode = MiningModeConfig.normal
        await self.send_config(cfg)
        return True

    async def _get_hostname(self, web_get_system_info: dict = None) -> Union[str, None]:
        if not web_get_system_info:
            try:
                web_get_system_info = await self.web.get_system_info()
            except APIError:
                pass

        if web_get_system_info:
            try:
                return web_get_system_info["hostname"]
            except KeyError:
                pass

    async def _get_mac(self, web_get_system_info: dict = None) -> Union[str, None]:
        if not web_get_system_info:
            try:
                web_get_system_info = await self.web.get_system_info()
            except APIError:
                pass

        if web_get_system_info:
            try:
                return web_get_system_info["macaddr"]
            except KeyError:
                pass

        try:
            data = await self.web.get_network_info()
            if data:
                return data["macaddr"]
        except KeyError:
            pass

    async def _get_errors(self, web_summary: dict = None) -> List[MinerErrorData]:
        if not web_summary:
            try:
                web_summary = await self.web.summary()
            except APIError:
                pass

        errors = []
        if web_summary:
            try:
                for item in web_summary["SUMMARY"][0]["status"]:
                    try:
                        if not item["status"] == "s":
                            errors.append(X19Error(item["msg"]))
                    except KeyError:
                        continue
            except (KeyError, IndexError):
                pass
        return errors

    async def _get_hashboards(self) -> List[HashBoard]:
        hashboards = [
            HashBoard(idx, expected_chips=self.expected_chips)
            for idx in range(self.expected_hashboards)
        ]

        try:
            api_stats = await self.api.send_command("stats", new_api=True)
        except APIError:
            return hashboards

        if api_stats:
            try:
                for board in api_stats["STATS"][0]["chain"]:
                    hashboards[board["index"]].hashrate = round(
                        board["rate_real"] / 1000, 2
                    )
                    hashboards[board["index"]].chips = board["asic_num"]
                    board_temp_data = list(
                        filter(lambda x: not x == 0, board["temp_pcb"])
                    )
                    hashboards[board["index"]].temp = sum(board_temp_data) / len(
                        board_temp_data
                    )
                    chip_temp_data = list(
                        filter(lambda x: not x == 0, board["temp_chip"])
                    )
                    hashboards[board["index"]].chip_temp = sum(chip_temp_data) / len(
                        chip_temp_data
                    )
                    hashboards[board["index"]].serial_number = board["sn"]
                    hashboards[board["index"]].missing = False
            except LookupError:
                pass
        return hashboards

    async def _get_fault_light(self, web_get_blink_status: dict = None) -> bool:
        if self.light:
            return self.light

        if not web_get_blink_status:
            try:
                web_get_blink_status = await self.web.get_blink_status()
            except APIError:
                pass

        if web_get_blink_status:
            try:
                self.light = web_get_blink_status["blink"]
            except KeyError:
                pass
        return self.light

    async def _get_expected_hashrate(self, api_stats: dict = None) -> Optional[float]:
        if not api_stats:
            try:
                api_stats = await self.api.stats()
            except APIError:
                pass

        if api_stats:
            try:
                expected_rate = api_stats["STATS"][1]["total_rateideal"]
                try:
                    rate_unit = api_stats["STATS"][1]["rate_unit"]
                except KeyError:
                    rate_unit = "GH"
                if rate_unit == "GH":
                    return round(expected_rate / 1000, 2)
                if rate_unit == "MH":
                    return round(expected_rate / 1000000, 2)
                else:
                    return round(expected_rate, 2)
            except (KeyError, IndexError):
                pass

    async def set_static_ip(
        self,
        ip: str,
        dns: str,
        gateway: str,
        subnet_mask: str = "255.255.255.0",
        hostname: str = None,
    ):
        if not hostname:
            hostname = await self.get_hostname()
        await self.web.set_network_conf(
            ip=ip,
            dns=dns,
            gateway=gateway,
            subnet_mask=subnet_mask,
            hostname=hostname,
            protocol=2,
        )

    async def set_dhcp(self, hostname: str = None):
        if not hostname:
            hostname = await self.get_hostname()
        await self.web.set_network_conf(
            ip="", dns="", gateway="", subnet_mask="", hostname=hostname, protocol=1
        )

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

    async def _is_mining(self, web_get_conf: dict = None) -> Optional[bool]:
        if not web_get_conf:
            try:
                web_get_conf = await self.web.get_miner_conf()
            except APIError:
                pass

        if web_get_conf:
            try:
                if web_get_conf["bitmain-work-mode"].isdigit():
                    return (
                        False if int(web_get_conf["bitmain-work-mode"]) == 1 else True
                    )
                return False
            except LookupError:
                pass

    async def _get_uptime(self, api_stats: dict = None) -> Optional[int]:
        if not api_stats:
            try:
                api_stats = await self.api.stats()
            except APIError:
                pass

        if api_stats:
            try:
                return int(api_stats["STATS"][1]["Elapsed"])
            except LookupError:
                pass


ANTMINER_OLD_DATA_LOC = DataLocations(
    **{
        str(DataOptions.MAC): DataFunction("_get_mac"),
        str(DataOptions.API_VERSION): DataFunction(
            "_get_api_ver", [RPCAPICommand("api_version", "version")]
        ),
        str(DataOptions.FW_VERSION): DataFunction(
            "_get_fw_ver", [RPCAPICommand("api_version", "version")]
        ),
        str(DataOptions.HOSTNAME): DataFunction(
            "_get_hostname", [WebAPICommand("web_get_system_info", "get_system_info")]
        ),
        str(DataOptions.HASHRATE): DataFunction(
            "_get_hashrate", [RPCAPICommand("api_summary", "summary")]
        ),
        str(DataOptions.EXPECTED_HASHRATE): DataFunction(
            "_get_expected_hashrate", [RPCAPICommand("api_stats", "stats")]
        ),
        str(DataOptions.HASHBOARDS): DataFunction(
            "_get_hashboards", [RPCAPICommand("api_stats", "stats")]
        ),
        str(DataOptions.ENVIRONMENT_TEMP): DataFunction("_get_env_temp"),
        str(DataOptions.WATTAGE): DataFunction("_get_wattage"),
        str(DataOptions.WATTAGE_LIMIT): DataFunction("_get_wattage_limit"),
        str(DataOptions.FANS): DataFunction(
            "_get_fans", [RPCAPICommand("api_stats", "stats")]
        ),
        str(DataOptions.FAN_PSU): DataFunction("_get_fan_psu"),
        str(DataOptions.ERRORS): DataFunction("_get_errors"),
        str(DataOptions.FAULT_LIGHT): DataFunction(
            "_get_fault_light",
            [WebAPICommand("web_get_blink_status", "get_blink_status")],
        ),
        str(DataOptions.IS_MINING): DataFunction(
            "_is_mining", [WebAPICommand("web_get_conf", "get_miner_conf")]
        ),
        str(DataOptions.UPTIME): DataFunction(
            "_get_uptime", [RPCAPICommand("api_stats", "stats")]
        ),
        str(DataOptions.CONFIG): DataFunction("get_config"),
    }
)


class AntminerOld(CGMiner):
    def __init__(self, ip: str, api_ver: str = "0.0.0") -> None:
        super().__init__(ip, api_ver)
        # interfaces
        self.web = AntminerOldWebAPI(ip)

        # static data
        # data gathering locations
        self.data_locations = ANTMINER_OLD_DATA_LOC

    async def get_config(self) -> MinerConfig:
        data = await self.web.get_miner_conf()
        if data:
            self.config = MinerConfig.from_am_old(data)
        return self.config

    async def send_config(self, config: MinerConfig, user_suffix: str = None) -> None:
        self.config = config
        await self.web.set_miner_conf(config.as_am_old(user_suffix=user_suffix))

    async def _get_mac(self) -> Union[str, None]:
        try:
            data = await self.web.get_system_info()
            if data:
                return data["macaddr"]
        except KeyError:
            pass

    async def fault_light_on(self) -> bool:
        # this should time out, after it does do a check
        await self.web.blink(blink=True)
        try:
            data = await self.web.get_blink_status()
            if data:
                if data["isBlinking"]:
                    self.light = True
        except KeyError:
            pass
        return self.light

    async def fault_light_off(self) -> bool:
        await self.web.blink(blink=False)
        try:
            data = await self.web.get_blink_status()
            if data:
                if not data["isBlinking"]:
                    self.light = False
        except KeyError:
            pass
        return self.light

    async def reboot(self) -> bool:
        data = await self.web.reboot()
        if data:
            return True
        return False

    async def _get_fault_light(self, web_get_blink_status: dict = None) -> bool:
        if self.light:
            return self.light

        if not web_get_blink_status:
            try:
                web_get_blink_status = await self.web.get_blink_status()
            except APIError:
                pass

        if web_get_blink_status:
            try:
                self.light = web_get_blink_status["isBlinking"]
            except KeyError:
                pass
        return self.light

    async def _get_hostname(self, web_get_system_info: dict = None) -> Optional[str]:
        if not web_get_system_info:
            try:
                web_get_system_info = await self.web.get_system_info()
            except APIError:
                pass

        if web_get_system_info:
            try:
                return web_get_system_info["hostname"]
            except KeyError:
                pass

    async def _get_fans(self, api_stats: dict = None) -> List[Fan]:
        if not api_stats:
            try:
                api_stats = await self.api.stats()
            except APIError:
                pass

        fans_data = [Fan() for _ in range(self.expected_fans)]
        if api_stats:
            try:
                fan_offset = -1

                for fan_num in range(1, 8, 4):
                    for _f_num in range(4):
                        f = api_stats["STATS"][1].get(f"fan{fan_num + _f_num}")
                        if f and not f == 0 and fan_offset == -1:
                            fan_offset = fan_num + 2
                if fan_offset == -1:
                    fan_offset = 3

                for fan in range(self.expected_fans):
                    fans_data[fan].speed = api_stats["STATS"][1].get(
                        f"fan{fan_offset+fan}", 0
                    )
            except (KeyError, IndexError):
                pass
        return fans_data

    async def _get_hashboards(self, api_stats: dict = None) -> List[HashBoard]:
        hashboards = []

        if not api_stats:
            try:
                api_stats = await self.api.stats()
            except APIError:
                pass

        if api_stats:
            try:
                board_offset = -1
                boards = api_stats["STATS"]
                if len(boards) > 1:
                    for board_num in range(1, 16, 5):
                        for _b_num in range(5):
                            b = boards[1].get(f"chain_acn{board_num + _b_num}")

                            if b and not b == 0 and board_offset == -1:
                                board_offset = board_num
                    if board_offset == -1:
                        board_offset = 1

                    for i in range(
                        board_offset, board_offset + self.expected_hashboards
                    ):
                        hashboard = HashBoard(
                            slot=i - board_offset, expected_chips=self.expected_chips
                        )

                        chip_temp = boards[1].get(f"temp{i}")
                        if chip_temp:
                            hashboard.chip_temp = round(chip_temp)

                        temp = boards[1].get(f"temp2_{i}")
                        if temp:
                            hashboard.temp = round(temp)

                        hashrate = boards[1].get(f"chain_rate{i}")
                        if hashrate:
                            hashboard.hashrate = round(float(hashrate) / 1000, 2)

                        chips = boards[1].get(f"chain_acn{i}")
                        if chips:
                            hashboard.chips = chips
                            hashboard.missing = False
                        if (not chips) or (not chips > 0):
                            hashboard.missing = True
                        hashboards.append(hashboard)
            except (IndexError, KeyError, ValueError, TypeError):
                pass

        return hashboards

    async def _is_mining(self, web_get_conf: dict = None) -> Optional[bool]:
        if not web_get_conf:
            try:
                web_get_conf = await self.web.get_miner_conf()
            except APIError:
                pass

        if web_get_conf:
            try:
                return False if int(web_get_conf["bitmain-work-mode"]) == 1 else True
            except LookupError:
                pass

        api_summary = None
        try:
            api_summary = await self.api.summary()
        except APIError:
            pass

        if api_summary is not None:
            if not api_summary == {}:
                return True
            else:
                return False

    async def _get_uptime(self, api_stats: dict = None) -> Optional[int]:
        if not api_stats:
            try:
                api_stats = await self.api.stats()
            except APIError:
                pass

        if api_stats:
            try:
                return int(api_stats["STATS"][1]["Elapsed"])
            except LookupError:
                pass
