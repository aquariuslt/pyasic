import asyncio
from unittest.mock import AsyncMock

from pyasic.miners.antminer.bmminer.X19 import (
    BMMinerS19XP,
    BMMinerS19XPPlusHydro,
    BMMinerS19XPHydro,
)
from pyasic.miners.antminer.bmminer.X21 import (
    BMMinerS21PlusHydro,
    BMMinerS21XPHydro,
)


def _rpc_stats_for_board(board):
    return {
        "STATS": [
            {
                "chain": [
                    {
                        "index": 0,
                        "rate_real": 257000,
                        "asic_num": 144,
                        "sn": "HB-STOCK-001",
                        "freq_avg": 700,
                        **board,
                    }
                ]
            }
        ]
    }


def test_antminer_air_hashboards_preserve_master_temp_values_and_add_air_layout(
    monkeypatch,
):
    miner = BMMinerS19XP("10.10.101.10")
    monkeypatch.setattr(
        miner.rpc,
        "stats",
        AsyncMock(
            return_value=_rpc_stats_for_board(
                {
                    "temp_pcb": [50, 55, 0, 60],
                    "temp_chip": [70, 0, 74],
                    "temp_pic": [80, 81, 0, 83],
                }
            )
        ),
    )

    hashboards = asyncio.run(miner._get_hashboards())

    assert hashboards[0].temp == 55
    assert hashboards[0].chip_temp == 72
    assert hashboards[0].inlet_temp == 70
    assert hashboards[0].outlet_temp == 74


def test_antminer_other_hydro_hashboards_preserve_master_standard_temp_values(
    monkeypatch,
):
    miner = BMMinerS19XPHydro("10.10.101.10")
    monkeypatch.setattr(
        miner.rpc,
        "stats",
        AsyncMock(
            return_value=_rpc_stats_for_board(
                {
                    "temp_pcb": [30, 35, 40, 45],
                    "temp_chip": [64, 0, 68],
                    "temp_pic": [70, 71, 0, 73],
                }
            )
        ),
    )

    hashboards = asyncio.run(miner._get_hashboards())

    assert hashboards[0].temp == 37.5
    assert hashboards[0].chip_temp == 66
    assert hashboards[0].inlet_temp is None
    assert hashboards[0].outlet_temp is None


def test_antminer_s21_plus_hydro_hashboards_parse_master_extended_temp_layout(
    monkeypatch,
):
    miner = BMMinerS21PlusHydro("10.10.101.10")
    monkeypatch.setattr(
        miner.rpc,
        "stats",
        AsyncMock(
            return_value=_rpc_stats_for_board(
                {
                    "temp_pcb": [30, 35, 40, 45],
                    "temp_chip": [64, 0, 68],
                    "temp_pic": [70, 71, 0, 73],
                }
            )
        ),
    )

    hashboards = asyncio.run(miner._get_hashboards())

    assert hashboards[0].inlet_temp == 30
    assert hashboards[0].outlet_temp == 40
    assert hashboards[0].chip_temp == 70
    assert hashboards[0].temp == 56


def test_antminer_s21_xp_hydro_hashboards_parse_issue_temp_layout(monkeypatch):
    miner = BMMinerS21XPHydro("10.10.101.10")
    monkeypatch.setattr(
        miner.rpc,
        "stats",
        AsyncMock(
            return_value=_rpc_stats_for_board(
                {
                    "temp_pcb": [38, 48, 46, 52],
                    "temp_chip": [65, 59, 58, 61],
                    "temp_pic": [55, 46, 53, 49],
                }
            )
        ),
    )

    hashboards = asyncio.run(miner._get_hashboards())

    assert hashboards[0].inlet_temp == 38
    assert hashboards[0].outlet_temp == 46
    assert hashboards[0].chip_temp == 55
    assert hashboards[0].temp == 49.6


def test_antminer_s19_xp_plus_hydro_hashboards_parse_issue_temp_layout(
    monkeypatch,
):
    miner = BMMinerS19XPPlusHydro("10.10.101.10")
    monkeypatch.setattr(
        miner.rpc,
        "stats",
        AsyncMock(
            return_value=_rpc_stats_for_board(
                {
                    "temp_pcb": [47, 57, 47, 57],
                    "temp_chip": [37, 47, 0, 0],
                    "temp_pic": [50, 47, 37, 59],
                }
            )
        ),
    )

    hashboards = asyncio.run(miner._get_hashboards())

    assert hashboards[0].inlet_temp == 37
    assert hashboards[0].outlet_temp == 47
    assert hashboards[0].chip_temp is None
    assert hashboards[0].temp == 54.5
