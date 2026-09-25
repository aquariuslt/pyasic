"""Field mapping of the GridFW backend, fed with responses captured from an
S21 XP on GridFW v1.1.10, with site and account identifiers replaced."""

import asyncio
import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from pyasic.config.mining import (
    MiningModeHashrateTune,
    MiningModeManual,
    MiningModeNormal,
    MiningModeSleep,
    MiningModeUnknown,
)
from pyasic.data.network import NetworkMode
from pyasic.device.firmware import MinerFirmware
from pyasic.errors import APITransportError
from pyasic.miners.antminer.sdminer import SDMinerS21XP
from pyasic.rpc.bmminer import BMMinerRPCAPI
from pyasic.web.sdminer import SDMinerWebAPI

DATA_DIR = Path(__file__).parent / "data"
WEB_COMMANDS = (
    "overview",
    "hashboards",
    "system",
    "pools",
    "miner_config",
    "system_info",
    "network",
    "find_miner",
)


def load_fixture(name):
    return json.loads((DATA_DIR / f"{name}.json").read_text())


def build_web_answers(**overrides):
    answers = {command: load_fixture(command) for command in WEB_COMMANDS}
    answers.update(overrides)
    return answers


def build_fake_multicommand(interface, answers, refused_commands=()):
    # counts every command as sent and records a failure for the refused ones
    # while the read runs, as the real clients do; a refused command answers
    # empty
    async def multicommand(*commands, **kwargs):
        for command in commands:
            interface._start_command(command)
            if command in refused_commands:
                interface._record_transport_error(
                    command, APITransportError("HTTP 403")
                )
        answered = {
            command: {} if command in refused_commands else answers[command]
            for command in commands
        }
        return {**answered, "multicommand": True}

    return multicommand


def read_miner(monkeypatch, *, refused_commands=(), **web_overrides):
    miner = SDMinerS21XP("10.10.101.10")
    monkeypatch.setattr(
        miner.web,
        "multicommand",
        build_fake_multicommand(
            miner.web, build_web_answers(**web_overrides), refused_commands
        ),
    )
    monkeypatch.setattr(
        miner.rpc,
        "multicommand",
        build_fake_multicommand(miner.rpc, {"version": [load_fixture("rpc_version")]}),
    )
    return asyncio.run(miner.get_data_with_errors())


@pytest.fixture
def miner_data(monkeypatch):
    return read_miner(monkeypatch).data


def test_backend_reports_gridfw_firmware():
    assert SDMinerS21XP("10.10.101.10").firmware == MinerFirmware.SDMINER


def test_backend_uses_sdminer_web_and_bmminer_rpc():
    miner = SDMinerS21XP("10.10.101.10")

    assert (type(miner.web), type(miner.rpc)) == (SDMinerWebAPI, BMMinerRPCAPI)


def test_a_full_read_has_no_field_errors(monkeypatch):
    result = read_miner(monkeypatch)

    assert (result.field_parse_errors, result.field_transport_errors) == ({}, {})


def test_mac_is_the_control_board_mac_in_upper_case(miner_data):
    assert miner_data.mac == "02:00:00:00:00:01"


def test_empty_machine_serial_is_reported_as_none(miner_data):
    assert miner_data.serial_number is None


def test_fw_ver_is_the_image_version(miner_data):
    assert miner_data.fw_ver == "v1.1.10"


def test_api_ver_comes_from_rpc_version(miner_data):
    assert miner_data.api_ver == "3.7"


def test_hostname_and_control_board_come_from_system(miner_data):
    assert (miner_data.hostname, miner_data.control_board) == ("Antminer", "A113D")


def test_hashrate_is_the_current_overview_hashrate(miner_data):
    assert round(float(miner_data.hashrate), 3) == 303.218


def test_expected_hashrate_scales_the_board_ideals_to_the_expected_boards(
    miner_data,
):
    assert round(float(miner_data.expected_hashrate), 3) == 308.781


def test_missing_board_does_not_lower_expected_hashrate(monkeypatch):
    hashboards = load_fixture("hashboards")
    hashboards["hashboards"][2]["present"] = False

    miner_data = read_miner(monkeypatch, hashboards=hashboards).data

    assert round(float(miner_data.expected_hashrate), 3) == 308.781


def test_present_boards_are_not_missing(miner_data):
    assert [board.missing for board in miner_data.hashboards] == [False, False, False]


def test_board_carries_chips_frequency_and_serial(miner_data):
    board = miner_data.hashboards[0]

    assert (board.chips, round(board.chip_frequency), board.serial_number) == (
        91,
        554,
        "BOARDSERIAL0000A",
    )


def test_board_hashrate_is_the_realtime_board_rate(miner_data):
    assert round(float(miner_data.hashboards[0].hashrate), 3) == 100.275


def test_board_temperatures_follow_the_stock_air_layout(miner_data):
    board = miner_data.hashboards[0]

    # inlet/outlet are chip sensors 0 and 2, temp and chip_temp the averages
    assert (board.inlet_temp, board.outlet_temp, board.temp, board.chip_temp) == (
        71,
        62,
        48,
        63,
    )


def test_board_absent_from_the_answer_stays_missing(monkeypatch):
    hashboards = load_fixture("hashboards")
    hashboards["hashboards"][1]["present"] = False

    miner_data = read_miner(monkeypatch, hashboards=hashboards).data

    assert miner_data.hashboards[1].missing is True


def test_temperature_raw_keeps_the_sensor_arrays(miner_data):
    assert miner_data.temperature_raw[0] == {
        "source": "sdminer",
        "chain_index": 0,
        "temp_chip": [71, 68, 62, 51],
        "temp_pcb": [56, 53, 47, 36],
    }


def test_wattage_and_efficiency_come_from_overview_power(miner_data):
    assert (miner_data.wattage, round(miner_data.efficiency)) == (4290, 14)


def test_fans_report_rpm(miner_data):
    assert [fan.speed for fan in miner_data.fans] == [6360, 6420, 6240, 5880]


def test_uptime_is_the_process_elapsed_time(miner_data):
    assert miner_data.uptime == 3263


def test_tuning_counts_as_mining(miner_data):
    assert miner_data.is_mining is True


def test_fault_light_comes_from_find_miner(miner_data):
    assert miner_data.fault_light is False


def test_pools_carry_state_and_last_share(miner_data):
    pool = miner_data.pools[0]

    assert (pool.user, pool.accepted, pool.alive, pool.active, pool.last_share_ts) == (
        "account.worker1",
        230,
        True,
        True,
        1790265732,
    )


def test_pool_without_a_share_has_no_last_share(miner_data):
    assert miner_data.pools[1].last_share_ts is None


def test_config_carries_the_saved_pools(miner_data):
    assert [pool.url for pool in miner_data.config.pools.groups[0].pools] == [
        "stratum+tcp://pool-a.example.com:3333",
        "stratum+tcp://pool-a.example.com:443",
        "stratum+tcp://pool-b.example.com:1314",
    ]


def test_config_mining_mode_is_the_mode_in_effect(miner_data):
    mode = miner_data.config.mining_mode

    assert (type(mode), mode.hashrate) == (MiningModeHashrateTune, 270)


def test_network_reports_runtime_values_under_dhcp(miner_data):
    network = miner_data.network

    assert (network.mode, network.ip, network.gateway, network.dns) == (
        NetworkMode.DHCP,
        "192.0.2.10",
        "192.0.2.1",
        "8.8.8.8 1.1.1.1",
    )


def test_healthy_miner_reports_no_errors(miner_data):
    assert miner_data.errors == []


def build_overview(**miner_fields):
    overview = load_fixture("overview")
    overview["miner"].update(miner_fields)
    return overview


def test_latched_fault_becomes_an_error(monkeypatch):
    overview = build_overview(error_code=1101, error="No chains detected")

    errors = read_miner(monkeypatch, overview=overview).data.errors

    assert [(e.error_code, e.error_message) for e in errors] == [
        (1101, "No chains detected")
    ]


def test_protection_becomes_an_error(monkeypatch):
    overview = build_overview(
        protection_code=1405, protection="Power supply protection is suspected"
    )

    errors = read_miner(monkeypatch, overview=overview).data.errors

    assert [e.error_code for e in errors] == [1405]


def test_degraded_state_becomes_an_error(monkeypatch):
    overview = build_overview(degraded=True, degraded_reason="tuning_incomplete")

    errors = read_miner(monkeypatch, overview=overview).data.errors

    assert [e.error_message for e in errors] == ["degraded: tuning_incomplete"]


def test_license_that_is_not_valid_becomes_an_error(monkeypatch):
    overview = load_fixture("overview")
    overview["license"].update(state="expired", last_error="sync failed")

    errors = read_miner(monkeypatch, overview=overview).data.errors

    assert [e.error_message for e in errors] == ["license expired: sync failed"]


@pytest.mark.parametrize(
    # "unknown" and "future_status" stand for values the firmware may add
    "status",
    ["initializing", "waiting", "sleeping", "error", "unknown", "future_status"],
)
def test_status_that_is_not_mining_reports_false(monkeypatch, status):
    overview = build_overview(status=status)

    assert read_miner(monkeypatch, overview=overview).data.is_mining is False


def test_overview_without_a_status_leaves_is_mining_unset(monkeypatch):
    miner = SDMinerS21XP("10.10.101.10")

    assert asyncio.run(miner._is_mining(web_overview={})) is None


@pytest.mark.parametrize(
    ("work_mode", "expected_type"),
    [
        ("stock", MiningModeNormal),
        ("sleep", MiningModeSleep),
        ("fixed", MiningModeManual),
        ("unknown", MiningModeUnknown),
    ],
)
def test_work_mode_maps_to_a_mining_mode(monkeypatch, work_mode, expected_type):
    overview = build_overview(work_mode=work_mode)

    mode = read_miner(monkeypatch, overview=overview).data.config.mining_mode

    assert type(mode) is expected_type


def test_fixed_mode_carries_the_saved_operating_point(monkeypatch):
    overview = build_overview(work_mode="fixed")

    mode = read_miner(monkeypatch, overview=overview).data.config.mining_mode

    assert (mode.global_freq, mode.global_volt) == (490, 14.3)


def test_refused_web_leaves_web_fields_as_transport_errors(monkeypatch):
    result = read_miner(monkeypatch, refused_commands=WEB_COMMANDS)

    assert {"mac", "wattage", "hashboards", "network"} <= set(
        result.field_transport_errors
    )


def test_refused_saved_config_leaves_config_unread(monkeypatch):
    # the work mode alone would read as a miner with no pools
    result = read_miner(monkeypatch, refused_commands=("miner_config",))

    assert result.data.config is None


def test_refused_saved_config_stays_a_transport_error(monkeypatch):
    result = read_miner(monkeypatch, refused_commands=("miner_config",))

    assert "config" in result.field_transport_errors


def test_refused_saved_config_leaves_the_other_requests_answered(monkeypatch):
    result = read_miner(monkeypatch, refused_commands=("miner_config",))

    assert result.all_requests_failed is False


def test_refused_web_with_answering_rpc_is_not_a_read_where_all_failed(
    monkeypatch,
):
    result = read_miner(monkeypatch, refused_commands=WEB_COMMANDS)

    assert result.all_requests_failed is False


def test_direct_call_requests_its_own_endpoint(monkeypatch):
    miner = SDMinerS21XP("10.10.101.10")
    system = AsyncMock(return_value=copy.deepcopy(load_fixture("system")))
    monkeypatch.setattr(miner.web, "system", system)

    asyncio.run(miner.get_mac())

    assert system.await_count == 1
