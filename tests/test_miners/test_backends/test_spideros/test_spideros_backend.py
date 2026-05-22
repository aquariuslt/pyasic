import asyncio
from unittest.mock import AsyncMock

from pyasic.data.error_codes import X19Error
from pyasic.device.firmware import MinerFirmware
from pyasic.miners.antminer.spideros.X19 import SpiderOSS19XPHydro
from pyasic.rpc.spideros import SpiderOSRPCAPI
from pyasic.web.spideros import SpiderOSWebAPI


def test_spideros_backend_uses_spideros_firmware_and_apis():
    miner = SpiderOSS19XPHydro("10.10.101.10")

    assert miner.firmware == MinerFirmware.SPIDER_OS
    assert isinstance(miner.web, SpiderOSWebAPI)
    assert isinstance(miner.rpc, SpiderOSRPCAPI)


def test_spideros_backend_normalizes_invalid_serial_number(monkeypatch):
    miner = SpiderOSS19XPHydro("10.10.101.10")

    monkeypatch.setattr(
        miner.web,
        "get_system_info",
        AsyncMock(return_value={"serinum": "0000000000000000"}),
    )

    serial_number = asyncio.run(miner.get_serial_number())

    assert serial_number is None


def test_spideros_expected_hashrate_uses_new_stats_api(monkeypatch):
    miner = SpiderOSS19XPHydro("10.10.101.10")
    stats_mock = AsyncMock(
        return_value={
            "STATS": [
                {},
                {
                    "total_rateideal": 257000,
                    "rate_unit": "GH",
                },
            ]
        }
    )
    monkeypatch.setattr(miner.rpc, "stats", stats_mock)

    expected_hashrate = asyncio.run(miner._get_expected_hashrate())

    assert stats_mock.await_args.args == ()
    assert stats_mock.await_args.kwargs == {"new_api": True}
    assert expected_hashrate is not None
    assert round(expected_hashrate.into(miner.algo.unit.TH)) == 257


def test_spideros_expected_hashrate_reuses_prefetched_stats(monkeypatch):
    miner = SpiderOSS19XPHydro("10.10.101.10")
    stats_mock = AsyncMock()
    monkeypatch.setattr(miner.rpc, "stats", stats_mock)

    expected_hashrate = asyncio.run(
        miner._get_expected_hashrate(
            {
                "STATS": [
                    {},
                    {
                        "total_rateideal": 260000,
                        "rate_unit": "GH",
                    },
                ]
            }
        )
    )

    stats_mock.assert_not_awaited()
    assert expected_hashrate is not None
    assert round(expected_hashrate.into(miner.algo.unit.TH)) == 260


def test_spideros_expected_hashrate_falls_back_to_new_api_when_prefetched_stats_missing_fields(
    monkeypatch,
):
    miner = SpiderOSS19XPHydro("10.10.101.10")
    stats_mock = AsyncMock(
        return_value={
            "STATS": [
                {},
                {
                    "total_rateideal": 258000,
                    "rate_unit": "GH",
                },
            ]
        }
    )
    monkeypatch.setattr(miner.rpc, "stats", stats_mock)

    expected_hashrate = asyncio.run(
        miner._get_expected_hashrate(
            {
                "STATS": [
                    {},
                    {
                        "Elapsed": 123,
                    },
                ]
            }
        )
    )

    assert stats_mock.await_args.args == ()
    assert stats_mock.await_args.kwargs == {"new_api": True}
    assert expected_hashrate is not None
    assert round(expected_hashrate.into(miner.algo.unit.TH)) == 258


def test_spideros_hashboards_parse_standard_temp_layout(monkeypatch):
    miner = SpiderOSS19XPHydro("10.10.101.10")
    monkeypatch.setattr(
        miner.rpc,
        "stats",
        AsyncMock(
            return_value={
                "STATS": [
                    {
                        "chain": [
                            {
                                "index": 0,
                                "rate_real": 120000,
                                "asic_num": 114,
                                "temp_pcb": [50, 55, 0, 60],
                                "temp_chip": [70, 0, 74],
                                "sn": "HB-001",
                                "freq_avg": 625,
                            }
                        ]
                    }
                ]
            }
        ),
    )

    hashboards = asyncio.run(miner._get_hashboards())

    assert len(hashboards) == miner.expected_hashboards
    assert round(hashboards[0].hashrate.into(miner.algo.unit.TH)) == 120
    assert hashboards[0].chips == 114
    assert hashboards[0].temp == 55
    assert hashboards[0].chip_temp == 72
    assert hashboards[0].serial_number == "HB-001"
    assert hashboards[0].chip_frequency == 625
    assert hashboards[0].missing is False


def test_spideros_hashboards_parse_extended_hydro_temp_layout(monkeypatch):
    miner = SpiderOSS19XPHydro("10.10.101.10")
    miner.uses_extended_hydro_temp_layout = True
    monkeypatch.setattr(
        miner.rpc,
        "stats",
        AsyncMock(
            return_value={
                "STATS": [
                    {
                        "chain": [
                            {
                                "index": 0,
                                "rate_real": 257000,
                                "asic_num": 144,
                                "temp_pcb": [30, 35, 40, 45],
                                "temp_pic": [70, 71, 0, 73],
                                "sn": "HB-HYD-001",
                                "freq_avg": 700,
                            }
                        ]
                    }
                ]
            }
        ),
    )

    hashboards = asyncio.run(miner._get_hashboards())

    assert hashboards[0].inlet_temp == 30
    assert hashboards[0].outlet_temp == 40
    assert hashboards[0].chip_temp == 70
    assert round(hashboards[0].temp) == 56


def test_spideros_pools_parse_pool_metrics():
    miner = SpiderOSS19XPHydro("10.10.101.10")

    pools = asyncio.run(
        miner._get_pools(
            {
                "POOLS": [
                    {
                        "POOL": 0,
                        "URL": "stratum+tcp://pool.example.com:3333",
                        "User": "worker.001",
                        "Status": "Alive",
                        "Stratum Active": True,
                        "Accepted": 10,
                        "Rejected": 1,
                        "Difficulty Accepted": 1024,
                        "Difficulty Rejected": 2,
                        "Difficulty Stale": 3,
                        "Get Failures": 4,
                        "Remote Failures": 5,
                        "Last Share Time": "12:34:56",
                    }
                ]
            }
        )
    )

    assert len(pools) == 1
    assert str(pools[0].url) == "stratum+tcp://pool.example.com:3333"
    assert pools[0].user == "worker.001"
    assert pools[0].alive is True
    assert pools[0].active is True
    assert pools[0].accepted == 10
    assert pools[0].rejected == 1
    assert pools[0].difficulty_accepted == 1024
    assert pools[0].difficulty_rejected == 2
    assert pools[0].difficulty_stale == 3
    assert pools[0].get_failures == 4
    assert pools[0].remote_failures == 5
    assert pools[0].index == 0
    assert pools[0].last_share_ts > 0


def test_spideros_errors_ignore_success_status_entries():
    miner = SpiderOSS19XPHydro("10.10.101.10")

    errors = asyncio.run(
        miner._get_errors(
            {
                "SUMMARY": [
                    {
                        "status": [
                            {"status": "s", "msg": "ok"},
                            {"status": "e", "msg": "Fan lost"},
                            {"msg": "missing-status-key"},
                        ]
                    }
                ]
            }
        )
    )

    assert len(errors) == 1
    assert isinstance(errors[0], X19Error)
    assert errors[0].error_message == "Fan lost"
