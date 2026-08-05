import asyncio
import time

from pyasic.miners.antminer.bitfufu.X21 import BitfufuS21HydroEx
from pyasic.miners.backends.utils import parse_last_share_to_timestamp

# shape matches DZ farm rawlog captures (S21 Hydro behind fufu pool proxies)
RPC_POOLS = {
    "POOLS": [
        {
            "POOL": 0,
            "URL": "stratum+tcp://10.10.101.1:3333",
            "User": "worker.001",
            "Status": "Alive",
            "Stratum Active": True,
            "Accepted": 54878,
            "Rejected": 3,
            "Get Failures": 0,
            "Remote Failures": 0,
            "Last Share Time": "0:00:12",
        },
        {
            "POOL": 1,
            "URL": "stratum+tcp://10.10.102.1:3301",
            "User": "worker.001",
            "Status": "Alive",
            "Stratum Active": False,
            "Accepted": 0,
            "Rejected": 0,
            "Get Failures": 0,
            "Remote Failures": 0,
            "Last Share Time": "0",
        },
    ],
}


def test_bitfufu_pools_parse_last_share_from_elapsed():
    miner = BitfufuS21HydroEx("10.10.101.10")

    pools = asyncio.run(miner._get_pools(RPC_POOLS))

    expected = int(time.time()) - 12
    assert abs(pools[0].last_share_ts - expected) <= 2


def test_bitfufu_pools_never_shared_pool_returns_zero():
    miner = BitfufuS21HydroEx("10.10.101.10")

    pools = asyncio.run(miner._get_pools(RPC_POOLS))

    assert pools[1].last_share_ts == 0


def test_bitfufu_pools_never_shared_pool_ignores_boot_elapsed():
    miner = BitfufuS21HydroEx("10.10.101.10")
    pools_data = {
        "POOLS": [
            {
                "POOL": 0,
                "URL": "stratum+tcp://10.10.101.1:3333",
                "User": "worker.001",
                "Status": "Dead",
                "Stratum Active": False,
                "Accepted": 0,
                "Last Share Time": "68:40:44",
            }
        ],
    }

    pools = asyncio.run(miner._get_pools(pools_data))

    assert pools[0].last_share_ts == 0


def test_bitfufu_pools_keep_existing_fields():
    miner = BitfufuS21HydroEx("10.10.101.10")

    pools = asyncio.run(miner._get_pools(RPC_POOLS))

    assert pools[0].accepted == 54878
    assert pools[0].active is True
    assert pools[1].active is False
