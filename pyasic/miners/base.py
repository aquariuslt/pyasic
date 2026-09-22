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
import asyncio
import ipaddress
import warnings
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Tuple, Type, TypeVar, Union

from pyasic.config import MinerConfig
from pyasic.data import Fan, HashBoard, MinerData, PowerSupply
from pyasic.data.device import DeviceInfo
from pyasic.data.error_codes import MinerErrorData
from pyasic.data.network import MinerNetworkConfig
from pyasic.data.pools import PoolMetrics
from pyasic.device.algorithm import MinerAlgoType
from pyasic.device.algorithm.base import GenericAlgo
from pyasic.device.algorithm.hashrate import AlgoHashRate
from pyasic.device.firmware import MinerFirmware
from pyasic.device.makes import MinerMake
from pyasic.device.models import MinerModelType
from pyasic.errors import APIError
from pyasic.logger import logger
from pyasic.miners.data import DataLocations, DataOptions, RPCAPICommand, WebAPICommand

# each interface's failures by command, then the requests sent and lost
_TransportSnapshot = Tuple[Dict[str, Exception], Dict[str, Exception], int, int]


def _carries_device_data(value: Any) -> bool:
    """Whether a parsed value holds anything the device answered. Parsers
    answer a failed request with what the model definition alone can build,
    so an empty container, or one holding nothing but empty values, proves
    nothing; zero and False are answers and count. This reads the shape only,
    so a container the parser refills with values of its own reads as data."""
    if value is None:
        return False
    if isinstance(value, str):
        return len(value) > 0
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        value = dump()
    if isinstance(value, dict):
        return any(_carries_device_data(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_carries_device_data(item) for item in value)
    return True


@dataclass
class MinerDataReadResult:
    """Outcome of `get_data_with_errors`: `data` carries every field that was
    read, and the two maps say why each of the others is missing. A field
    served by a fallback source is in neither, however many requests behind
    it failed; a field can be in both.

    `field_parse_errors`: what this field's parser raised. The field keeps
    its default value on `data`.

    `field_transport_errors`: the failure of a request behind this field,
    which was left without device data as a result. It says "not read", as
    opposed to "the device has nothing here", which is what a caller keeping
    the last known value needs. Reliable for the scalar fields; a parser that
    refills a container from the model definition reads as data.

    `all_requests_failed`: not one of the requests this read sent got an
    answer. Counted per request, and False as soon as one gets through. It is
    a transport verdict, not a reachability or a data one."""

    data: MinerData
    field_parse_errors: Dict[str, Exception] = field(default_factory=dict)
    field_transport_errors: Dict[str, Exception] = field(default_factory=dict)
    all_requests_failed: bool = False


class MinerProtocol(Protocol):
    _rpc_cls: Type = None
    _web_cls: Type = None
    _ssh_cls: Type = None

    ip: str = None
    rpc: _rpc_cls = None
    web: _web_cls = None
    ssh: _ssh_cls = None

    make: MinerMake = None
    raw_model: MinerModelType = None
    firmware: MinerFirmware = None
    algo: type[MinerAlgoType] = GenericAlgo
    control_board: str | None = None

    expected_hashboards: int = None
    expected_chips: int = None
    expected_fans: int = None

    data_locations: DataLocations = None

    supports_shutdown: bool = False
    supports_power_modes: bool = False
    supports_presets: bool = False
    supports_autotuning: bool = False

    api_ver: str = None
    fw_ver: str = None
    light: bool = None
    config: MinerConfig = None

    def __repr__(self):
        return f"{self.model}: {str(self.ip)}"

    def __lt__(self, other):
        return ipaddress.ip_address(self.ip) < ipaddress.ip_address(other.ip)

    def __gt__(self, other):
        return ipaddress.ip_address(self.ip) > ipaddress.ip_address(other.ip)

    def __eq__(self, other):
        return ipaddress.ip_address(self.ip) == ipaddress.ip_address(other.ip)

    @property
    def model(self) -> str:
        if self.raw_model is not None:
            model_data = [self.raw_model]
        elif self.make is not None:
            model_data = [self.make]
        else:
            model_data = ["Unknown"]
        if self.firmware is not None:
            model_data.append(f"({self.firmware})")
        return " ".join(model_data)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            make=self.make,
            model=self.raw_model,
            firmware=self.firmware,
            algo=self.algo,
        )

    @property
    def api(self):
        return self.rpc

    async def check_light(self) -> bool:
        """Get the status of the fault light as a boolean.

        Returns:
            A boolean value representing the fault light status.
        """
        return await self.get_fault_light()

    async def fault_light_on(self) -> bool:
        """Turn the fault light of the miner on and return success as a boolean.

        Returns:
            A boolean value of the success of turning the light on.
        """
        return False

    async def fault_light_off(self) -> bool:
        """Turn the fault light of the miner off and return success as a boolean.

        Returns:
            A boolean value of the success of turning the light off.
        """
        return False

    async def get_config(self) -> MinerConfig:
        # Not a data gathering function, since this is used for configuration
        """Get the mining configuration of the miner and return it as a [`MinerConfig`][pyasic.config.MinerConfig].

        Returns:
            A [`MinerConfig`][pyasic.config.MinerConfig] containing the pool information and mining configuration.
        """
        return MinerConfig()

    async def reboot(self) -> bool:
        """Reboot the miner and return success as a boolean.

        Returns:
            A boolean value of the success of rebooting the miner.
        """
        return False

    async def restart_backend(self) -> bool:
        """Restart the mining process of the miner (bosminer, bmminer, cgminer, etc) and return success as a boolean.

        Returns:
            A boolean value of the success of restarting the mining process.
        """
        return False

    async def send_config(self, config: MinerConfig, user_suffix: str = None) -> None:
        """Set the mining configuration of the miner.

        Parameters:
            config: A [`MinerConfig`][pyasic.config.MinerConfig] containing the mining config you want to switch the miner to.
            user_suffix: A suffix to append to the username when sending to the miner.
        """
        return None

    async def stop_mining(self) -> bool:
        """Stop the mining process of the miner.

        Returns:
            A boolean value of the success of stopping the mining process.
        """
        return False

    async def resume_mining(self) -> bool:
        """Resume the mining process of the miner.

        Returns:
            A boolean value of the success of resuming the mining process.
        """
        return False

    async def set_power_limit(self, wattage: int) -> bool:
        """Set the power limit to be used by the miner.

        Parameters:
            wattage: The power limit to set on the miner.

        Returns:
            A boolean value of the success of setting the power limit.
        """
        return False

    async def upgrade_firmware(
        self,
        *,
        file: str = None,
        url: str = None,
        version: str = None,
        keep_settings: bool = True,
    ) -> bool:
        """Upgrade the firmware of the miner.

        Parameters:
            file: The file path to the firmware to upgrade from. Must be a valid file path if provided.
            url: The URL to download the firmware from. Must be a valid URL if provided.
            version: The version of the firmware to upgrade to. If None, the version will be inferred from the file or URL.
            keep_settings: Whether to keep the current settings during the upgrade. Defaults to True.

        Returns:
            A boolean value of the success of the firmware upgrade.
        """
        return False

    ##################################################
    ### DATA GATHERING FUNCTIONS (get_{some_data}) ###
    ##################################################

    async def get_mac(self) -> Optional[str]:
        """Get the MAC address of the miner and return it as a string.

        Returns:
            A string representing the MAC address of the miner.
        """
        return await self._get_mac()

    async def get_model(self) -> Optional[str]:
        """Get the model of the miner and return it as a string.

        Returns:
            A string representing the model of the miner.
        """
        return self.model

    async def get_device_info(self) -> Optional[DeviceInfo]:
        """Get device information, including model, make, and firmware.

        Returns:
            A dataclass containing device information.
        """
        return self.device_info

    async def get_api_ver(self) -> Optional[str]:
        """Get the API version of the miner and is as a string.

        Returns:
            API version as a string.
        """
        return await self._get_api_ver()

    async def get_fw_ver(self) -> Optional[str]:
        """Get the firmware version of the miner and is as a string.

        Returns:
            Firmware version as a string.
        """
        return await self._get_fw_ver()

    async def get_version(self) -> Tuple[Optional[str], Optional[str]]:
        """Get the API version and firmware version of the miner and return them as strings.

        Returns:
            A tuple of (API version, firmware version) as strings.
        """
        api_ver = await self.get_api_ver()
        fw_ver = await self.get_fw_ver()
        return api_ver, fw_ver

    async def get_hostname(self) -> Optional[str]:
        """Get the hostname of the miner and return it as a string.

        Returns:
            A string representing the hostname of the miner.
        """
        return await self._get_hostname()

    async def get_serial_number(self) -> Optional[str]:
        """Get the serial number of the miner and return it as a string.

        Returns:
            A string representing the serial number of the miner.
        """
        return await self._get_serial_number()

    async def get_hashrate(self) -> Optional[AlgoHashRate]:
        """Get the hashrate of the miner and return it as a float in TH/s.

        Returns:
            Hashrate of the miner in TH/s as a float.
        """
        return await self._get_hashrate()

    async def get_hashboards(self) -> List[HashBoard]:
        """Get hashboard data from the miner in the form of [`HashBoard`][pyasic.data.HashBoard].

        Returns:
            A [`HashBoard`][pyasic.data.HashBoard] instance containing hashboard data from the miner.
        """
        return await self._get_hashboards()

    async def get_env_temp(self) -> Optional[float]:
        """Get environment temp from the miner as a float.

        Returns:
            Environment temp of the miner as a float.
        """
        return await self._get_env_temp()

    async def get_wattage(self) -> Optional[int]:
        """Get wattage from the miner as an int.

        Returns:
            Wattage of the miner as an int.
        """
        return await self._get_wattage()

    async def get_voltage(self) -> Optional[float]:
        """Get output voltage of the PSU as a float.

        Returns:
            Output voltage of the PSU as an float.
        """
        return await self._get_voltage()

    async def get_wattage_limit(self) -> Optional[int]:
        """Get wattage limit from the miner as an int.

        Returns:
            Wattage limit of the miner as an int.
        """
        return await self._get_wattage_limit()

    async def get_fans(self) -> List[Fan]:
        """Get fan data from the miner in the form [fan_1, fan_2, fan_3, fan_4].

        Returns:
            A list of fan data.
        """
        return await self._get_fans()

    async def get_psus(self) -> List[PowerSupply]:
        """Get PSU data from the miner in the form [psu_1, psu_2].

        Returns:
            A list of PSU data.
        """
        return await self._get_psus()

    async def get_fan_psu(self) -> Optional[int]:
        """Get PSU fan speed from the miner.

        Returns:
            PSU fan speed.
        """
        return await self._get_fan_psu()

    async def get_errors(self) -> List[MinerErrorData]:
        """Get a list of the errors the miner is experiencing.

        Returns:
            A list of error classes representing different errors.
        """
        return await self._get_errors()

    async def get_fault_light(self) -> bool:
        """Check the status of the fault light and return on or off as a boolean.

        Returns:
            A boolean value where `True` represents on and `False` represents off.
        """
        return await self._get_fault_light()

    async def get_expected_hashrate(self) -> Optional[AlgoHashRate]:
        """Get the nominal hashrate from factory if available.

        Returns:
            A float value of nominal hashrate in TH/s.
        """
        return await self._get_expected_hashrate()

    async def is_mining(self) -> Optional[bool]:
        """Check whether the miner is mining.

        Returns:
            A boolean value representing if the miner is mining.
        """
        return await self._is_mining()

    async def get_uptime(self) -> Optional[int]:
        """Get the uptime of the miner in seconds.

        Returns:
            The uptime of the miner in seconds.
        """
        return await self._get_uptime()

    async def get_pools(self) -> List[PoolMetrics]:
        """Get the pools information from Miner.

        Returns:
            The pool information of the miner.
        """
        return await self._get_pools()

    async def _get_mac(self) -> Optional[str]:
        pass

    async def _get_api_ver(self) -> Optional[str]:
        pass

    async def _get_fw_ver(self) -> Optional[str]:
        pass

    async def _get_hostname(self) -> Optional[str]:
        pass

    async def _get_serial_number(self) -> Optional[str]:
        pass

    async def _get_control_board(self) -> Optional[str]:
        return None

    async def _get_hashrate(self) -> Optional[AlgoHashRate]:
        pass

    async def _get_hashboards(self) -> List[HashBoard]:
        return []

    async def _get_env_temp(self) -> Optional[float]:
        pass

    async def _get_wattage(self) -> Optional[int]:
        pass

    async def _get_voltage(self) -> Optional[float]:
        pass

    async def _get_wattage_limit(self) -> Optional[int]:
        pass

    async def _get_fans(self) -> List[Fan]:
        return []

    async def _get_psus(self) -> List[PowerSupply]:
        return []

    async def _get_fan_psu(self) -> Optional[int]:
        pass

    async def _get_errors(self) -> List[MinerErrorData]:
        return []

    async def _get_fault_light(self) -> Optional[bool]:
        pass

    async def _get_expected_hashrate(self) -> Optional[AlgoHashRate]:
        pass

    async def _is_mining(self) -> Optional[bool]:
        pass

    async def _get_uptime(self) -> Optional[int]:
        pass

    async def _get_pools(self) -> List[PoolMetrics]:
        pass

    async def _get_temperature_raw(self) -> list[dict]:
        return []

    async def _get_network(self) -> Optional[MinerNetworkConfig]:
        pass

    async def _get_data(
        self,
        allow_warning: bool,
        include: List[Union[str, DataOptions]] = None,
        exclude: List[Union[str, DataOptions]] = None,
    ) -> Tuple[dict, Dict[str, Exception], Dict[str, Exception], bool]:
        # one parser raising must not discard the fields already parsed: the
        # commands were all sent before parsing started, so every failure is
        # collected and the caller decides whether to raise
        # only the failures of this read count: the interfaces keep recording
        # across single commands sent outside get_data
        for interface in (self.rpc, self.web):
            if interface is not None:
                interface._clear_transport_errors()
        # handle include
        if include is not None:
            include = [str(i) for i in include]
        else:
            # everything
            include = [str(enum_value.value) for enum_value in DataOptions]

        # handle exclude
        # prioritized over include, including x and excluding x will exclude x
        if exclude is not None:
            for item in exclude:
                if str(item) in include:
                    include.remove(str(item))

        rpc_multicommand = set()
        web_multicommand = set()
        # create multicommand
        for data_name in include:
            try:
                # get kwargs needed for the _get_xyz function
                fn_args = getattr(self.data_locations, data_name).kwargs

                # keep track of which RPC/Web commands need to be sent
                for arg in fn_args:
                    if isinstance(arg, RPCAPICommand):
                        rpc_multicommand.add(arg.cmd)
                    if isinstance(arg, WebAPICommand):
                        web_multicommand.add(arg.cmd)
            except KeyError as e:
                logger.error(type(e), e, data_name)
                continue

        api_command_data, web_command_data = await asyncio.gather(
            self._send_multicommand(self.rpc, rpc_multicommand, allow_warning),
            self._send_multicommand(self.web, web_multicommand, allow_warning),
        )
        # read before any parser runs, since a parser asking the device again
        # rewrites the interface's record for that command. _settle_field
        # charges what a parser loses to that parser's own field
        rpc_failures, web_failures, *_ = self._transport_snapshot()
        field_transport_errors = self._collect_transport_errors(
            include, rpc_failures, web_failures
        )
        miner_data = {}
        field_parse_errors: Dict[str, Exception] = {}

        for data_name in include:
            try:
                fn_args = getattr(self.data_locations, data_name).kwargs
                args_to_send = {k.name: None for k in fn_args}
                for arg in fn_args:
                    try:
                        if isinstance(arg, RPCAPICommand):
                            if api_command_data.get("multicommand"):
                                args_to_send[arg.name] = api_command_data[arg.cmd][0]
                            else:
                                args_to_send[arg.name] = api_command_data
                        if isinstance(arg, WebAPICommand):
                            if web_command_data is not None:
                                if web_command_data.get("multicommand"):
                                    args_to_send[arg.name] = web_command_data[arg.cmd]
                                else:
                                    if not web_command_data == {"multicommand": False}:
                                        args_to_send[arg.name] = web_command_data
                    except LookupError:
                        args_to_send[arg.name] = None
            except LookupError:
                continue
            before_parser = self._transport_snapshot()
            try:
                function = getattr(self, getattr(self.data_locations, data_name).cmd)
                miner_data[data_name] = await function(**args_to_send)
            except Exception as e:
                field_parse_errors[data_name] = e
            self._settle_field(
                data_name,
                miner_data.get(data_name),
                before_parser,
                field_transport_errors,
            )
        return (
            miner_data,
            field_parse_errors,
            field_transport_errors,
            self._all_requests_failed(),
        )

    @staticmethod
    async def _send_multicommand(
        interface: Any, commands: set, allow_warning: bool
    ) -> dict:
        """The interface's answer to these commands, or an empty answer when
        there are none. A backend that raises on a failed request has that
        failure recorded under every command of the batch, leaving the other
        interface's answer intact."""
        if not commands:
            return {}
        try:
            answer = await interface.multicommand(
                *commands, allow_warning=allow_warning
            )
        except APIError as e:
            for command in commands:
                if command not in interface.transport_errors:
                    interface._start_command(command)
                    interface._record_transport_error(command, e)
            return {}
        return {} if answer is None else answer

    def _transport_snapshot(self) -> _TransportSnapshot:
        """Where transport stands right now: the rpc and web failures by
        command, and the requests sent and lost across both."""
        interfaces = [i for i in (self.rpc, self.web) if i is not None]
        return (
            dict(self.rpc.transport_errors) if self.rpc is not None else {},
            dict(self.web.transport_errors) if self.web is not None else {},
            sum(i.request_count for i in interfaces),
            sum(i.failure_count for i in interfaces),
        )

    def _failure_since(self, before: _TransportSnapshot) -> Optional[Exception]:
        """A failure recorded since `before` was taken, if any."""
        for interface, earlier in zip((self.rpc, self.web), before):
            if interface is None:
                continue
            for command, error in interface.transport_errors.items():
                if earlier.get(command) is not error:
                    return error
        return None

    def _settle_field(
        self,
        data_name: str,
        value: Any,
        before: _TransportSnapshot,
        field_transport_errors: Dict[str, Exception],
    ) -> None:
        """Record whether this field was read, now that its parser has run.
        Data from any source settles it, a fallback that answered included
        (antminer macs fall back from get_system_info to get_network_info).
        A field left empty keeps the multicommand phase's verdict when its
        parser asked nothing of its own, counts as answered when its own
        requests all got through, and carries the failure of one that did
        not."""
        if _carries_device_data(value):
            field_transport_errors.pop(data_name, None)
            return
        *_, sent_before, failed_before = before
        *_, sent_after, failed_after = self._transport_snapshot()
        if sent_after == sent_before:
            return
        if failed_after == failed_before:
            field_transport_errors.pop(data_name, None)
            return
        own_failure = self._failure_since(before)
        if own_failure is not None:
            field_transport_errors.setdefault(data_name, own_failure)

    def _all_requests_failed(self) -> bool:
        """Whether not one request this read sent got an answer. Counted per
        request, so a command sent twice with one answer counts as answered,
        and read once the parsers are done, so fallbacks count too."""
        *_, sent, failed = self._transport_snapshot()
        return sent > 0 and failed == sent

    def _collect_transport_errors(
        self,
        include: List[str],
        rpc_failures: Dict[str, Exception],
        web_failures: Dict[str, Exception],
    ) -> Dict[str, Exception]:
        """The requested fields whose rpc or web command failed during the
        multicommand phase, keyed by field. A field fed by several commands is
        listed when any of them failed: its parser then saw a partial answer,
        so its value cannot be trusted as complete."""
        field_transport_errors: Dict[str, Exception] = {}
        for data_name in include:
            # a backend reading a field through an endpoint of its own records
            # the failure under the field name
            failures = [
                rpc_failures.get(data_name),
                web_failures.get(data_name),
            ]
            location = getattr(self.data_locations, data_name, None)
            for arg in location.kwargs if location is not None else []:
                if isinstance(arg, RPCAPICommand):
                    failures.append(rpc_failures.get(arg.cmd))
                elif isinstance(arg, WebAPICommand):
                    failures.append(web_failures.get(arg.cmd))
            found = next((failure for failure in failures if failure is not None), None)
            if found is not None:
                field_transport_errors[data_name] = found
        return field_transport_errors

    async def get_data(
        self,
        allow_warning: bool = False,
        include: List[Union[str, DataOptions]] = None,
        exclude: List[Union[str, DataOptions]] = None,
    ) -> MinerData:
        """Get data from the miner in the form of [`MinerData`][pyasic.data.MinerData].

        Parameters:
            allow_warning: Allow warning when an API command fails.
            include: Names of data items you want to gather. Defaults to all data.
            exclude: Names of data items to exclude.  Exclusion happens after considering included items.

        Returns:
            A [`MinerData`][pyasic.data.MinerData] instance containing data from the miner.

        Raises:
            APIError: When the parser of any requested data item fails. Use
                `get_data_with_errors` to keep the other items instead.
        """
        result = await self.get_data_with_errors(
            allow_warning=allow_warning, include=include, exclude=exclude
        )
        for data_name, error in result.field_parse_errors.items():
            # the command that never got through is the cause; a parser
            # choking on the empty answer is the symptom
            raise APIError(
                f"Failed to call {data_name} on {self} while getting data."
            ) from result.field_transport_errors.get(data_name, error)
        return result.data

    async def get_data_with_errors(
        self,
        allow_warning: bool = False,
        include: List[Union[str, DataOptions]] = None,
        exclude: List[Union[str, DataOptions]] = None,
    ) -> MinerDataReadResult:
        """Get data from the miner, keeping every data item whose parser
        succeeded when another one fails.

        Parameters:
            allow_warning: Allow warning when an API command fails.
            include: Names of data items you want to gather. Defaults to all data.
            exclude: Names of data items to exclude.  Exclusion happens after considering included items.

        Returns:
            A [`MinerDataReadResult`][pyasic.miners.base.MinerDataReadResult]: the
            [`MinerData`][pyasic.data.MinerData] with every parsed item set, the
            exception of each requested item whose parser failed, and the
            transport failure of each requested item whose command got no
            answer, both keyed by item name. Failed items keep their default
            value on the data.
        """
        data = MinerData(
            ip=str(self.ip),
            device_info=self.device_info,
            expected_chips=(
                self.expected_chips * self.expected_hashboards
                if self.expected_chips is not None
                else 0
            ),
            expected_hashboards=self.expected_hashboards,
            expected_fans=self.expected_fans,
            hashboards=[
                HashBoard(slot=i, expected_chips=self.expected_chips)
                for i in range(
                    self.expected_hashboards
                    if self.expected_hashboards is not None
                    else 0
                )
            ],
        )

        (
            gathered_data,
            field_parse_errors,
            field_transport_errors,
            all_requests_failed,
        ) = await self._get_data(
            allow_warning=allow_warning, include=include, exclude=exclude
        )
        for item in gathered_data:
            if gathered_data[item] is not None:
                setattr(data, item, gathered_data[item])
        return MinerDataReadResult(
            data=data,
            field_parse_errors=field_parse_errors,
            field_transport_errors=field_transport_errors,
            all_requests_failed=all_requests_failed,
        )


class BaseMiner(MinerProtocol):
    def __init__(self, ip: str) -> None:
        self.ip = ip

        if self.expected_chips is None and self.raw_model is not None:
            warnings.warn(
                f"Unknown chip count for miner type {self.raw_model}, "
                f"please open an issue on GitHub (https://github.com/UpstreamData/pyasic)."
            )

        # interfaces
        if self._rpc_cls is not None:
            self.rpc = self._rpc_cls(ip)
        if self._web_cls is not None:
            self.web = self._web_cls(ip)
        if self._ssh_cls is not None:
            self.ssh = self._ssh_cls(ip)


AnyMiner = TypeVar("AnyMiner", bound=BaseMiner)
