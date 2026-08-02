import asyncio
import time

from pyasic.miners.antminer.luxos.X21 import LUXMinerS21PlusHydro
from pyasic.miners.backends.utils import parse_last_share_to_timestamp

# captured from a real S21+ Hydro running LuxOS 2026.7.3 (farm OBTX01)
RPC_POOLS = {
    "POOLS": [
        {
            "POOL": 0,
            "URL": "stratum+tcp://ss.antpool.com:3333",
            "User": "KJDTX021",
            "Status": "Alive",
            "Stratum Active": True,
            "Accepted": 17761,
            "Rejected": 1,
            "Get Failures": 0,
            "Remote Failures": 0,
            "Difficulty Accepted": 20974747648,
            "Difficulty Rejected": 1048576,
            "Difficulty Stale": 13631488,
            "Last Share Time": "00:00:33",
        },
        {
            "POOL": 1,
            "URL": "stratum+tcp://ss.antpool.com:443",
            "User": "KJDTX021",
            "Status": "Dead",
            "Stratum Active": False,
            "Accepted": 0,
            "Rejected": 0,
            "Get Failures": 0,
            "Remote Failures": 0,
            "Difficulty Accepted": 0,
            "Difficulty Rejected": 0,
            "Difficulty Stale": 0,
            # LuxOS reports elapsed-since-boot for pools without any share
            "Last Share Time": "68:40:44",
        },
    ],
    "STATUS": [{"STATUS": "S", "Msg": "2 Pool(s)"}],
    "id": 1,
}


def test_luxminer_pools_parse_last_share_from_elapsed():
    miner = LUXMinerS21PlusHydro("10.10.101.10")

    pools = asyncio.run(miner._get_pools(RPC_POOLS))

    expected = int(time.time()) - 33
    assert abs(pools[0].last_share_ts - expected) <= 2


def test_luxminer_pools_never_shared_pool_returns_zero_despite_boot_elapsed():
    miner = LUXMinerS21PlusHydro("10.10.101.10")

    pools = asyncio.run(miner._get_pools(RPC_POOLS))

    assert pools[1].last_share_ts == 0


def test_luxminer_pools_parse_cumulative_difficulty_fields():
    miner = LUXMinerS21PlusHydro("10.10.101.10")

    pools = asyncio.run(miner._get_pools(RPC_POOLS))

    assert pools[0].difficulty_accepted == 20974747648
    assert pools[0].difficulty_rejected == 1048576
    assert pools[0].difficulty_stale == 13631488


def test_luxminer_pools_keep_existing_fields():
    miner = LUXMinerS21PlusHydro("10.10.101.10")

    pools = asyncio.run(miner._get_pools(RPC_POOLS))

    assert pools[0].accepted == 17761
    assert pools[0].alive is True
    assert pools[0].active is True
    assert pools[1].alive is False


def test_luxminer_parse_last_share_defensive_values():
    parse = parse_last_share_to_timestamp

    assert parse("0") == 0
    assert parse("") == 0
    assert parse(None) == 0
    assert parse("not-a-time") == 0


def test_luxminer_parse_last_share_hours_over_24():
    parse = parse_last_share_to_timestamp

    expected = int(time.time()) - 30 * 3600
    assert abs(parse("30:00:00") - expected) <= 2
