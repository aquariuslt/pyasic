import asyncio

from pyasic.miners.backends.antminer import AntminerModern
from pyasic.data.pools import PoolMetrics


def test_pool_metrics_uses_snake_case_difficulty_keys():
    pool = PoolMetrics(
        url=None,
        accepted=10,
        rejected=2,
        difficulty_accepted=1048576.0,
        difficulty_rejected=262144.0,
        difficulty_stale=0.0,
    )

    serialized = pool.model_dump()
    assert serialized["difficulty_accepted"] == 1048576.0
    assert serialized["difficulty_rejected"] == 262144.0
    assert serialized["difficulty_stale"] == 0.0


def test_antminer_pool_difficulty_from_new_api_keys():
    miner = AntminerModern("127.0.0.1")
    pools = asyncio.run(
        miner._get_pools(
            {
                "POOLS": [
                    {
                        "POOL": 0,
                        "URL": "stratum+tcp://example.pool:3333",
                        "Status": "Alive",
                        "User": "worker",
                        "Accepted": 10,
                        "Rejected": 2,
                        "diffa": 352360906752,
                        "diffr": 51380224,
                        "diffs": 0,
                        "Last Share Time": "0",
                    }
                ]
            }
        )
    )

    assert len(pools) == 1
    pool = pools[0]
    assert pool.difficulty_accepted == 352360906752
    assert pool.difficulty_rejected == 51380224
    assert pool.difficulty_stale == 0


def test_antminer_pool_difficulty_from_title_case_keys():
    miner = AntminerModern("127.0.0.1")
    pools = asyncio.run(
        miner._get_pools(
            {
                "POOLS": [
                    {
                        "POOL": 0,
                        "URL": "stratum+tcp://example.pool:3333",
                        "Status": "Alive",
                        "User": "worker",
                        "Accepted": 10,
                        "Rejected": 2,
                        "Difficulty Accepted": 1048576.0,
                        "Difficulty Rejected": 262144.0,
                        "Difficulty Stale": 0.0,
                        "Last Share Time": "0",
                    }
                ]
            }
        )
    )

    assert len(pools) == 1
    pool = pools[0]
    assert pool.difficulty_accepted == 1048576.0
    assert pool.difficulty_rejected == 262144.0
    assert pool.difficulty_stale == 0.0
