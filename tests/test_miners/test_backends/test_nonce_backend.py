import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from pyasic.data import MinerData
from pyasic.data.boards import HashBoard
from pyasic.errors import APIError, APITransportError
from pyasic.miners.antminer.nonce import NonceS21Plus
from pyasic.rpc.base import BaseMinerRPCAPI

FIXTURE = Path(__file__).parent / "fixtures" / "nonce-s21plus-stats.json"


def responses():
    """STATS comes from CGMiner's production exporter with test measurements."""
    return {
        "version": [
            {
                "VERSION": [
                    {
                        "Firmware": "Nonce",
                        "Nonce API": 2,
                        "Model": "Antminer S21+",
                        "CGMiner": "4.13.7",
                        "API": "3.7",
                    }
                ]
            }
        ],
        "stats": [json.loads(FIXTURE.read_text())],
        "summary": [
            json.loads(FIXTURE.with_name("nonce-s21plus-summary.json").read_text())
        ],
        "legacy_stats": [
            json.loads(FIXTURE.with_name("nonce-s21plus-legacy-stats.json").read_text())
        ],
        "pools": [
            {
                "POOLS": [
                    {
                        "POOL": 0,
                        "URL": "stratum+tcp://pool.example:3333",
                        "User": "test.worker",
                        "Status": "Alive",
                        "Stratum Active": True,
                        "Accepted": 0,
                        "Rejected": 0,
                    }
                ]
            }
        ],
        "multicommand": True,
    }


def read(response=None):
    miner = NonceS21Plus("192.0.2.1")
    payload = response if response is not None else responses()
    miner.rpc.multicommand = AsyncMock(return_value=payload)
    for command in ("stats", "summary", "legacy_stats", "version", "pools"):
        setattr(
            miner.rpc, command, AsyncMock(return_value=payload.get(command, [None])[0])
        )
    return miner, asyncio.run(miner.get_data_with_errors())


def test_nonce_returns_unextended_standard_data():
    _, result = read()
    assert type(result.data) is MinerData
    assert all(type(board) is HashBoard for board in result.data.hashboards)
    dumped = result.data.model_dump(mode="json")
    assert "mining_state" not in dumped
    assert "field_errors" not in dumped
    assert set(dumped["hashboards"][0]) == set(HashBoard.model_fields)
    assert dumped["temperature_raw"][0] == {
        "source": "nonce",
        "chain_index": 0,
        "temp_pcb": [30, None, 40, None],
    }


def test_native_snapshot_maps_to_serialized_data_without_http():
    miner, result = read()
    data = result.data
    assert result.field_parse_errors == {}
    assert miner.web is None and miner.ssh is None
    assert float(data.hashrate) == 200
    assert data.uptime == 120 and data.fw_ver == "4.13.7"
    assert data.mac == "02:11:22:33:44:55" and data.serial_number is None
    assert data.is_mining is True
    assert len(data.hashboards) == 3 and data.expected_chips == 165
    board = data.hashboards[0]
    assert (board.inlet_temp, board.outlet_temp, board.temp, board.chip_temp) == (
        30,
        40,
        None,
        None,
    )
    assert data.temperature_raw[0]["temp_pcb"] == [30, None, 40, None]
    assert data.fans[0].speed == 0 and data.fans[1].speed == 3000
    assert data.pools[0].user == "test.worker"
    dumped = data.model_dump(mode="json")
    assert dumped["hashboards"][0]["serial_number"] is None
    commands = miner.rpc.multicommand.call_args.args
    assert set(commands) == {"version", "stats", "summary", "legacy_stats", "pools"}


def test_partial_arrays_keep_slots_and_valid_zero():
    response = responses()
    stats = response["stats"][0]["STATS"][0]
    stats["chain"][0]["temp_pcb"] = [None, None, 55, None]
    stats["chain"][1]["temp_pcb"] = []
    stats["chain"][2]["temp_pcb"] = [0, None, float("nan"), None]
    stats["fan"][2] = None
    _, result = read(response)
    assert [board.outlet_temp for board in result.data.hashboards] == [55, None, None]
    assert result.data.hashboards[2].inlet_temp == 0
    assert all(board.temp is None for board in result.data.hashboards)
    assert result.data.fans[0].speed == 0 and result.data.fans[2].speed is None
    assert result.data.temperature_raw[0]["temp_pcb"] == [None, None, 55, None]


def test_physical_slots_use_index_even_when_reordered_or_missing():
    response = responses()
    stats = response["stats"][0]["STATS"][0]
    stats["chain"] = [stats["chain"][2], stats["chain"][0]]
    _, result = read(response)
    assert [board.slot for board in result.data.hashboards] == [0, 1, 2]
    assert result.data.hashboards[1].missing is True
    assert result.data.hashboards[2].chips == 55
    assert result.data.hashboards[1].hashrate is None


@pytest.mark.parametrize("value", [0, 200000])
def test_mining_status_uses_real_short_window(value):
    response = responses()
    response["summary"][0]["SUMMARY"][0]["rate_5s"] = value
    _, result = read(response)
    assert float(result.data.hashrate) == value / 1000
    assert result.data.is_mining is (value > 0)
    assert all(board.hashrate is None for board in result.data.hashboards)


def test_missing_five_second_rate_does_not_use_average():
    response = responses()
    response["summary"][0]["SUMMARY"][0]["rate_5s"] = None
    _, result = read(response)
    assert result.data.hashrate is None and result.data.is_mining is False
    assert "hashrate" in result.field_parse_errors


@pytest.mark.parametrize(
    "stats", [None, {}, {"STATUS": [{"STATUS": "S"}], "STATS": [{"nonce_schema": 1}]}]
)
def test_missing_or_legacy_stats_preserves_summary_without_fallback(stats):
    response = responses()
    response["stats"] = [stats]
    miner, result = read(response)
    assert result.data.mac == "02:11:22:33:44:55"
    assert all(board.missing and board.temp is None for board in result.data.hashboards)
    assert "hashboards" in result.field_parse_errors
    assert float(result.data.hashrate) == 200
    miner.rpc.multicommand.assert_awaited_once()


def test_optional_parser_failure_isolated():
    miner = NonceS21Plus("192.0.2.1")
    miner.rpc.multicommand = AsyncMock(return_value=responses())
    miner._get_fans = AsyncMock(side_effect=ValueError("bad fans"))
    result = asyncio.run(miner.get_data_with_errors())
    assert set(result.field_parse_errors) == {"fans"}
    assert result.data.hashboards[0].inlet_temp == 30


@pytest.mark.parametrize("value", [None, -1, True, float("inf"), 0, 525.25])
def test_frequency_is_mhz_and_missing_is_not_replaced(value):
    response = responses()
    response["stats"][0]["STATS"][0]["chain"][0].update(
        freq_avg=value, sn="HB-0", eeprom_loaded=True
    )
    _, result = read(response)
    assert result.data.hashboards[0].chip_frequency == (
        value
        if type(value) in (int, float) and value >= 0 and value != float("inf")
        else None
    )
    assert result.data.hashboards[0].serial_number == "HB-0"
    assert result.data.voltage == 15.003
    assert result.data.psus[0].serial_number == "KLKT347BEJBAJ3889"
    assert result.data.wattage == 3500


def test_no_template_extensions_leak_to_standard_model():
    response = responses()
    response["legacy_stats"][0]["STATS"][0].pop("MAC")
    response["stats"][0]["INFO"]["mac"] = "02:11:22:33:44:55"
    response["stats"][0]["STATS"][0].update(mining_state="fault", psu={"voltage_v": 13})
    _, result = read(response)
    assert result.data.mac is None and result.data.voltage == 15.003
    assert result.data.is_mining is True
    assert "mining_state" not in result.data.model_dump()


@pytest.mark.parametrize(
    "include, exclude",
    [
        ([], None),
        (["fans"], None),
        (None, ["is_mining"]),
        (["is_mining"], ["is_mining"]),
    ],
)
def test_unrequested_mining_state_keeps_standard_default(include, exclude):
    miner, _ = read()
    data = asyncio.run(miner.get_data(include=include, exclude=exclude))
    assert data.is_mining is MinerData.model_fields["is_mining"].default
    assert data.expected_chips == 165


def test_errors_do_not_send_requests():
    miner = NonceS21Plus("192.0.2.1")
    miner.rpc.multicommand = AsyncMock()
    assert asyncio.run(miner.get_errors()) == []
    data = asyncio.run(miner.get_data(include=["errors"]))
    assert data.serial_number is None and data.errors == []
    miner.rpc.multicommand.assert_not_awaited()


@pytest.mark.parametrize("missing", ["Accepted", "Rejected"])
def test_missing_pool_counter_preserves_live_pool(missing):
    response = responses()
    response["pools"][0]["POOLS"][0][missing] = None
    _, result = read(response)
    assert "pools" not in result.field_parse_errors
    pool = result.data.model_dump(mode="json")["pools"][0]
    assert pool["alive"] is True and pool["active"] is True
    assert pool["pool_rejected_percent"] == pool["pool_stale_percent"] == 0


@pytest.mark.parametrize(
    "failed", [(), ("stats",), ("legacy_stats",), ("stats", "legacy_stats")]
)
@pytest.mark.parametrize("first", ["stats", "legacy_stats"])
@pytest.mark.parametrize("failure_kind", ["transport", "decode", "api"])
def test_stats_requests_keep_independent_transport_outcomes(
    failed, first, failure_kind
):
    async def collect():
        miner = NonceS21Plus("192.0.2.1")
        payload = responses()
        failures = set(failed)
        first_done = asyncio.Event()
        requests = []

        async def respond(raw, **kwargs):
            request = json.loads(raw)
            requests.append(request)
            assert request["command"] == "stats"
            kind = "stats" if request.get("new_api") else "legacy_stats"
            if kind != first:
                await first_done.wait()
            try:
                if kind in failures:
                    if failure_kind == "decode":
                        return b"broken JSON"
                    if failure_kind == "api":
                        return json.dumps(
                            {"STATUS": {"STATUS": "E", "Msg": "unavailable"}}
                        ).encode()
                    raise APITransportError(f"{kind} unavailable")
                return json.dumps(payload[kind][0]).encode() + b"\x00"
            finally:
                if kind == first:
                    first_done.set()

        with patch.object(BaseMinerRPCAPI, "_send_bytes", side_effect=respond):
            result = await miner.get_data_with_errors(
                include=["fans", "mac", "wattage", "voltage", "psus", "serial_number"]
            )
            expected_fields = set()
            if "stats" in failed:
                expected_fields.add("fans")
            if "legacy_stats" in failed:
                expected_fields.update(
                    ["mac", "wattage", "voltage", "psus", "serial_number"]
                )
            assert set(result.field_transport_errors) == expected_fields
            assert set(result.field_parse_errors) == (
                {"fans"} if "stats" in failed else set()
            )
            assert result.all_requests_failed is (len(failed) == 2)
            assert miner.rpc.request_count == 2
            assert miner.rpc.failure_count == len(failed)
            assert set(miner.rpc.transport_errors) == set(failed)
            expected_error_type = (
                APIError if failure_kind == "api" else APITransportError
            )
            assert all(
                type(error) is expected_error_type
                for error in miner.rpc.transport_errors.values()
            )
            assert len(requests) == 2
            assert result.data.mac == (
                None if "legacy_stats" in failed else "02:11:22:33:44:55"
            )
            if "stats" not in failed:
                assert result.data.fans[0].speed == 0

            failures.clear()
            recovered = await miner.get_data_with_errors(include=["fans", "mac"])
            assert (
                recovered.field_parse_errors == recovered.field_transport_errors == {}
            )
            assert recovered.all_requests_failed is False
            assert miner.rpc.request_count == 2 and miner.rpc.failure_count == 0

    asyncio.run(asyncio.wait_for(collect(), timeout=2))


@pytest.mark.parametrize(
    "value, expected",
    [
        (3500, 3500),
        (0, 0),
        (3500.49, 3500),
        (3500.5, 3501),
        (3501.5, 3502),
        (-1, None),
        (True, None),
        ("3500", None),
        (None, None),
        (float("nan"), None),
        (float("inf"), None),
        (-float("inf"), None),
    ],
)
def test_psu_power_watts_and_half_up_rounding(value, expected):
    response = responses()
    response["legacy_stats"][0]["STATS"][0]["PSU Power W"] = value
    _, result = read(response)
    assert result.data.wattage == expected
    assert (
        type(result.data.wattage) is int
        if expected is not None
        else result.data.wattage is None
    )
    assert result.data.psus[0].temperature is None
    assert result.data.model_dump(mode="json")["wattage"] == expected
    assert result.data.efficiency == (
        round(expected / 200) if expected is not None else None
    )


@pytest.mark.parametrize(
    "age, expected",
    [
        (0, 3500),
        (30000, 3500),
        (30001, None),
        (-1, None),
        (None, None),
        (True, None),
        (float("inf"), None),
        (float("nan"), None),
    ],
)
def test_psu_sample_age_bounds(age, expected):
    response = responses()
    response["legacy_stats"][0]["STATS"][0]["PSU Sample Age ms"] = age
    _, result = read(response)
    assert result.data.wattage == expected
    assert result.data.voltage == (15.003 if expected is not None else None)


@pytest.mark.parametrize("flag", [False, None, 1, "true"])
def test_invalid_power_flag_does_not_hide_other_fields(flag):
    response = responses()
    response["legacy_stats"][0]["STATS"][0]["PSU Power Valid"] = flag
    _, result = read(response)
    assert result.data.wattage is None
    assert result.data.voltage == 15.003
    assert float(result.data.hashrate) == 200


def test_partial_psu_failure_preserves_valid_power_and_identity():
    response = responses()
    response["legacy_stats"][0]["STATS"][0].update(
        {
            "PSU Telemetry Valid": False,
            "PSU Telemetry Error": 5,
            "PSU Read Errors": 12,
            "PSU Temperature Valid": False,
        }
    )
    _, result = read(response)
    assert result.data.wattage == 3500
    assert result.data.voltage == 15.003
    assert result.data.psus[0].serial_number == "KLKT347BEJBAJ3889"


@pytest.mark.parametrize("legacy", [None, {}, {"STATUS": [{"STATUS": "E"}]}])
def test_missing_psu_supplement_is_optional(legacy):
    response = responses()
    response["legacy_stats"] = [legacy]
    _, result = read(response)
    assert result.field_parse_errors == {}
    assert result.data.wattage is None and result.data.voltage is None
    assert result.data.psus == []
    assert float(result.data.hashrate) == 200


def test_ambiguous_psu_rows_are_not_summed():
    response = responses()
    response["legacy_stats"][0]["STATS"] *= 2
    _, result = read(response)
    assert result.data.wattage is None and result.data.psus == []


def test_psu_read_ignores_pool_stats_rows():
    response = responses()
    response["legacy_stats"][0]["STATS"].insert(0, {"ID": "POOL0"})
    _, result = read(response)
    assert result.data.wattage == 3500


def test_individual_power_getters_reuse_collection():
    miner, _ = read()
    assert asyncio.run(miner.get_wattage()) == 3500
    assert asyncio.run(miner.get_voltage()) == 15.003
    assert asyncio.run(miner.get_psus())[0].serial_number == "KLKT347BEJBAJ3889"


@pytest.mark.parametrize(
    "changes, expected",
    [
        ({"PSU Voltage Valid": False}, None),
        ({"PSU Voltage V": float("nan")}, None),
        ({"PSU Voltage V": -1}, None),
        ({"PSU Voltage V": True}, None),
        ({"PSU Voltage V": 0}, 0),
    ],
)
def test_voltage_validity_is_independent_of_power(changes, expected):
    response = responses()
    response["legacy_stats"][0]["STATS"][0].update(changes)
    _, result = read(response)
    assert result.data.voltage == expected
    assert result.data.wattage == 3500


@pytest.mark.parametrize(
    "valid, serial, expected",
    [
        (True, " PSU-1 ", "PSU-1"),
        (True, "", None),
        (True, " ", None),
        (True, 123, "123"),
        (False, "PSU-1", None),
        (1, "PSU-1", None),
    ],
)
def test_psu_identity_validity_does_not_control_power(valid, serial, expected):
    response = responses()
    response["legacy_stats"][0]["STATS"][0].update(
        {"PSU Identity Valid": valid, "PSU Serial": serial}
    )
    _, result = read(response)
    assert [psu.serial_number for psu in result.data.psus] == (
        [] if expected is None else [expected]
    )
    assert result.data.wattage == 3500


@pytest.mark.parametrize(
    "mac",
    [
        None,
        "",
        "00:00:00:00:00:00",
        "ff:ff:ff:ff:ff:ff",
        "01:11:22:33:44:55",
        "02:11:22:33:44",
        "02:11:22:33:44:55 extra",
        123,
        True,
    ],
)
def test_missing_or_invalid_mac_is_not_identity(mac):
    response = responses()
    response["legacy_stats"][0]["STATS"][0]["MAC"] = mac
    _, result = read(response)
    assert result.data.mac is None
    assert result.data.wattage == 3500
    assert float(result.data.hashrate) == 200


@pytest.mark.parametrize("error", [None, 19, -1, True, False, "0"])
def test_mac_requires_successful_current_read(error):
    response = responses()
    response["legacy_stats"][0]["STATS"][0]["MAC Error"] = error
    _, result = read(response)
    assert result.data.mac is None


def test_mac_is_independent_of_psu_and_normalized():
    response = responses()
    response["legacy_stats"][0]["STATS"] = [
        {"MAC": "02:AB:CD:EF:00:01", "MAC Error": 0}
    ]
    miner, result = read(response)
    assert result.data.mac == "02:ab:cd:ef:00:01"
    assert result.data.psus == [] and result.data.wattage is None
    assert asyncio.run(miner.get_mac()) == "02:ab:cd:ef:00:01"
    miner.rpc.legacy_stats.assert_awaited()


def test_ambiguous_mac_rows_are_rejected():
    response = responses()
    response["legacy_stats"][0]["STATS"] *= 2
    _, result = read(response)
    assert result.data.mac is None


@pytest.mark.parametrize("api_fields", [{}, {"Nonce API": 1}, {"Nonce API": 2}])
def test_firmware_version_does_not_require_nonce_api_marker(api_fields):
    response = responses()
    version = response["version"][0]["VERSION"][0]
    version.pop("Nonce API")
    version.update(api_fields)
    _, result = read(response)
    assert result.data.fw_ver == "4.13.7"
    assert "fw_ver" not in result.field_parse_errors


def test_firmware_version_still_requires_nonce_firmware():
    response = responses()
    response["version"][0]["VERSION"][0]["Firmware"] = "Other"
    _, result = read(response)
    assert result.data.fw_ver is None
    assert "fw_ver" in result.field_parse_errors


@pytest.mark.parametrize(
    "value",
    [
        None,
        12,
        True,
        [],
        {},
        "",
        "unknown",
        "N/A",
        "na",
        "None",
        "null",
        "000000",
        "read error",
    ],
)
def test_invalid_miner_serial(value):
    miner = NonceS21Plus("192.0.2.1")
    response = {"STATUS": [{"STATUS": "S"}], "STATS": [{"Miner Serial": value}]}
    assert asyncio.run(miner._get_serial_number(response)) is None


def test_serial_selection_and_legacy_request_reuse():
    response = responses()
    response["legacy_stats"][0]["STATS"][-1]["Miner Serial"] = " \tTestSn2162\r\n"
    miner, result = read(response)
    assert result.data.serial_number == "TestSn2162"
    assert result.field_parse_errors == {}
    assert asyncio.run(miner.get_serial_number()) == "TestSn2162"
    miner.rpc.legacy_stats.assert_awaited()
    data = asyncio.run(miner.get_data(include=["serial_number", "mac", "psus"]))
    assert data.serial_number == "TestSn2162"
    miner.rpc.legacy_stats.assert_awaited()
    miner.rpc.multicommand.reset_mock()
    assert (
        asyncio.run(
            miner.get_data(include=["serial_number"], exclude=["serial_number"])
        ).serial_number
        is None
    )
    miner.rpc.multicommand.assert_not_awaited()
    response["legacy_stats"][0]["STATS"].append({"Miner Serial": "Other"})
    assert asyncio.run(miner.get_serial_number()) is None


@pytest.mark.parametrize(
    "value", [" HB-1 ", "unknown", "read error", "000000", "000", "A B", "é", "A" * 129]
)
def test_serials_follow_antminer_normalization(value):
    from pyasic.miners.backends.utils import normalize_antminer_like_serial_number

    payload = responses()
    row = payload["legacy_stats"][0]["STATS"][0]
    row.update({"Miner Serial": value, "PSU Serial": value})
    payload["stats"][0]["STATS"][0]["chain"][0].update(sn=value, eeprom_loaded=True)
    _, result = read(payload)
    expected = normalize_antminer_like_serial_number(value)
    assert result.data.serial_number == expected
    assert result.data.hashboards[0].serial_number == expected
    assert [psu.serial_number for psu in result.data.psus] == (
        [] if expected is None else [expected]
    )


@pytest.mark.parametrize(
    "asic_num, serial, missing",
    [
        (None, "HB-1", False),
        (None, "unknown", True),
        (None, "read error", True),
        (None, "000000", True),
        (55, "unknown", False),
    ],
)
def test_hashboard_presence_uses_normalized_serial(asic_num, serial, missing):
    payload = responses()
    payload["stats"][0]["STATS"][0]["chain"][0].update(
        asic_num=asic_num, sn=serial, eeprom_loaded=True
    )
    _, result = read(payload)
    board = result.data.hashboards[0]
    assert board.missing is missing
    assert board.serial_number == ("HB-1" if serial == "HB-1" else None)


@pytest.mark.parametrize("failure", ["transport", "decode", "api"])
def test_summary_failure_does_not_retry_and_preserves_status_attribution(failure):
    async def collect():
        miner = NonceS21Plus("192.0.2.1")
        calls = 0

        async def respond(raw, **kwargs):
            nonlocal calls
            calls += 1
            assert json.loads(raw)["command"] == "summary"
            if failure == "decode":
                return b"broken JSON"
            if failure == "api":
                return json.dumps(
                    {"STATUS": {"STATUS": "E", "Msg": "unsupported"}}
                ).encode()
            raise APITransportError("offline")

        with patch.object(BaseMinerRPCAPI, "_send_bytes", side_effect=respond):
            result = await miner.get_data_with_errors(include=["is_mining"])
        # A failed batch response is not evidence of stopped mining, and its
        # placeholder prevents the parser from sending a second request.
        assert result.data.is_mining is True
        assert "is_mining" in result.field_transport_errors
        assert "is_mining" in result.field_parse_errors
        expected_error_type = APIError if failure == "api" else APITransportError
        assert type(result.field_transport_errors["is_mining"]) is expected_error_type
        assert result.all_requests_failed is True
        assert calls == 1
        assert miner.rpc.request_count == 1

    asyncio.run(collect())


@pytest.mark.parametrize(
    "getter,command",
    [
        ("get_serial_number", "legacy_stats"),
        ("get_mac", "legacy_stats"),
        ("get_api_ver", "version"),
        ("get_fw_ver", "version"),
        ("get_hashrate", "summary"),
        ("get_uptime", "summary"),
        ("is_mining", "summary"),
        ("get_hashboards", "stats"),
        ("get_fans", "stats"),
        ("get_pools", "pools"),
        ("get_voltage", "legacy_stats"),
        ("get_wattage", "legacy_stats"),
        ("get_psus", "legacy_stats"),
    ],
)
def test_public_getters_fetch_directly(getter, command):
    miner, _ = read()
    miner.rpc.multicommand.reset_mock()
    asyncio.run(getattr(miner, getter)())
    getattr(miner.rpc, command).assert_awaited_once()
    miner.rpc.multicommand.assert_not_awaited()


@pytest.mark.parametrize(
    "getter,command",
    [
        ("get_serial_number", "legacy_stats"),
        ("get_mac", "legacy_stats"),
        ("get_hashrate", "summary"),
        ("get_uptime", "summary"),
        ("is_mining", "summary"),
        ("get_hashboards", "stats"),
        ("get_fans", "stats"),
        ("get_voltage", "legacy_stats"),
        ("get_wattage", "legacy_stats"),
        ("get_psus", "legacy_stats"),
    ],
)
def test_public_getters_do_not_retry_failed_reads(getter, command):
    miner = NonceS21Plus("192.0.2.1")
    request = AsyncMock(side_effect=APIError("unavailable"))
    setattr(miner.rpc, command, request)
    try:
        asyncio.run(getattr(miner, getter)())
    except (TypeError, ValueError):
        pass
    request.assert_awaited_once()


def test_voltage_is_a_standard_selectable_option():
    from pyasic.miners.data import DataOptions

    miner, _ = read()
    miner.rpc.multicommand.reset_mock()
    result = asyncio.run(miner.get_data(include=[DataOptions.VOLTAGE]))
    assert result.voltage == 15.003
    assert miner.rpc.multicommand.call_args.args == ("legacy_stats",)
    miner.rpc.multicommand.reset_mock()
    result = asyncio.run(
        miner.get_data(include=[DataOptions.VOLTAGE], exclude=[DataOptions.VOLTAGE])
    )
    assert result.voltage is None
    miner.rpc.multicommand.assert_not_awaited()


def test_unknown_nonce_uses_reported_slots_without_s21_expectations():
    from pyasic.miners.factory import NonceUnknown
    from pyasic.miners.device.firmware import StockFirmware

    miner = NonceUnknown("192.0.2.1")
    payload = responses()
    row = payload["stats"][0]["STATS"][0]
    row["chain"] = [dict(row["chain"][0], index=5)]
    row["fan"] = [1200, 1300]
    miner.rpc.multicommand = AsyncMock(return_value=payload)
    result = asyncio.run(miner.get_data_with_errors())
    assert not isinstance(miner, StockFirmware)
    assert result.field_parse_errors == {}
    assert miner.expected_chips is None
    assert result.data.expected_chips == 0
    assert [(b.slot, b.expected_chips) for b in result.data.hashboards] == [(5, None)]
    assert len(result.data.fans) == 2
    assert miner.web is None and miner.ssh is None


@pytest.mark.parametrize("fans", [None, {}, "bad"])
@pytest.mark.parametrize("unknown_model", [False, True])
def test_invalid_fan_container_returns_empty_list(fans, unknown_model):
    from pyasic.miners.factory import NonceUnknown

    miner = NonceUnknown("192.0.2.1") if unknown_model else NonceS21Plus("192.0.2.1")
    payload = responses()
    payload["stats"][0]["STATS"][0]["fan"] = fans
    miner.rpc.multicommand = AsyncMock(return_value=payload)
    result = asyncio.run(miner.get_data_with_errors(include=["fans"]))
    assert result.data.fans == []
    assert result.field_parse_errors == {}


@pytest.mark.parametrize(
    "fans, speeds",
    [
        ([], []),
        ([1200], [1200]),
        ([0, 1300], [0, 1300]),
        ([1200, 1300, 1400], [1200, 1300, 1400]),
    ],
)
def test_unknown_model_uses_actual_valid_fan_list(fans, speeds):
    from pyasic.miners.factory import NonceUnknown

    miner = NonceUnknown("192.0.2.1")
    payload = responses()
    payload["stats"][0]["STATS"][0]["fan"] = fans
    miner.rpc.multicommand = AsyncMock(return_value=payload)
    result = asyncio.run(miner.get_data_with_errors(include=["fans"]))
    assert [fan.speed for fan in result.data.fans] == speeds
    assert result.field_parse_errors == {}
