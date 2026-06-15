import asyncio
from unittest.mock import AsyncMock

from pyasic.miners.antminer.hashmaster.X19 import HashMasterS19XPHydro
from pyasic.miners.antminer.hashmaster.X21 import HashMasterT21


def _rpc_stats_for_board(board):
    return {
        "STATS": [
            {
                "chain": [
                    {
                        "index": 0,
                        "rate_real": 257000,
                        "asic_num": 144,
                        "sn": "HB-HM-001",
                        "freq_avg": 700,
                        **board,
                    }
                ]
            }
        ]
    }


def test_hashmaster_hydro_hashboards_parse_extended_temp_layout(monkeypatch):
    miner = HashMasterS19XPHydro("10.10.101.10")
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
                                "sn": "HB-HM-HYD-001",
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
    assert hashboards[0].temp == 56


def test_hashmaster_air_hashboards_preserve_master_temp_values_and_add_air_layout(
    monkeypatch,
):
    miner = HashMasterT21("10.10.101.10")
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
