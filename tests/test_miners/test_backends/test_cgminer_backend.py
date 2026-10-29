import asyncio

import pytest

from pyasic.miners.antminer.bmminer.X21.S21 import BMMinerS21Plus, BMMinerS21XP
from pyasic.miners.antminer.nonce import NonceS21Plus, NonceS21XP
from pyasic.miners.backends.cgminer import parse_cgminer_pools


@pytest.mark.parametrize("miner_class", [NonceS21Plus, NonceS21XP])
def test_nonce_preserves_pool_time_and_difficulty(miner_class):
    response = {
        "POOLS": [
            {
                "POOL": 0,
                "URL": "stratum+tcp://pool.example:3333",
                "User": "test.worker",
                "Status": "Alive",
                "Stratum Active": True,
                "Accepted": 12,
                "Rejected": 1,
                "Last Share Time": 1793187000,
                "Difficulty Accepted": 1048576.0,
                "Difficulty Rejected": 65536.0,
                "Difficulty Stale": 0.0,
            }
        ]
    }
    miner = miner_class("192.0.2.1")
    pool = asyncio.run(miner._get_pools(response))[0].model_dump(mode="json")
    assert pool["last_share_ts"] == 1793187000
    assert pool["difficulty_accepted"] == 1048576.0
    assert pool["difficulty_rejected"] == 65536.0
    assert pool["difficulty_stale"] == 0.0
    assert pool["accepted"] == 12
    assert pool["active"] is True


@pytest.mark.parametrize("value", [None, True, -1, 1.5, "00:00:07", "invalid"])
def test_invalid_epoch_is_unknown(value):
    pool = parse_cgminer_pools({"POOLS": [{"Last Share Time": value}]})[0]
    assert pool.last_share_ts is None


def test_no_share_and_absent_share_are_distinct():
    pools = parse_cgminer_pools({"POOLS": [{"Last Share Time": 0}, {}]})
    assert pools[0].last_share_ts == 0
    assert pools[1].last_share_ts is None


@pytest.mark.parametrize("miner_class", [BMMinerS21Plus, BMMinerS21XP])
@pytest.mark.parametrize("value", [None, 0, 100000])
def test_stock_adapter_preserves_unknown_ideal_hashrate(miner_class, value):
    miner = miner_class("192.0.2.1")
    result = asyncio.run(
        miner._get_expected_hashrate(
            {"STATS": [{}, {"total_rateideal": value, "rate_unit": "GH"}]}
        )
    )
    assert (float(result) if result is not None else None) == (
        value / 1000 if value is not None else None
    )
