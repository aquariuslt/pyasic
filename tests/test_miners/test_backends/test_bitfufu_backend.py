import asyncio
from unittest.mock import AsyncMock

from pyasic.miners.antminer.bitfufu.X19 import BitfufuS19XPEx, BitfufuS19XPHydroEx


def _rpc_stats_for_board(board):
    return {
        "STATS": [
            {
                "chain": [
                    {
                        "index": 0,
                        "rate_real": 257000,
                        "asic_num": 144,
                        "sn": "HB-BITFUFU-001",
                        "freq_avg": 700,
                        **board,
                    }
                ]
            }
        ]
    }


def test_bitfufu_air_hashboards_preserve_master_temp_values_and_add_air_layout(
    monkeypatch,
):
    miner = BitfufuS19XPEx("10.10.101.10")
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


def test_bitfufu_hydro_hashboards_parse_master_extended_temp_layout(monkeypatch):
    miner = BitfufuS19XPHydroEx("10.10.101.10")
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
