import asyncio
import time

from pyasic.miners.elphapex.daoge.DGX import ElphapexDG1Plus
from pyasic.miners.backends.utils import parse_last_share_to_timestamp

# captured from real DG1+ miners (farm DA01-AR-US-W)
WEB_POOLS_HEALTHY = {
    "POOLS": [
        {
            "index": 0,
            "url": "stratum+tcp://stratum-ltc.antpool.com:8888",
            "user": "nodg1.5.165",
            "status": "Alive",
            "priority": 0,
            "accepted": 9389,
            "rejected": 0,
            "stale": 0,
            "getworks": 9389,
            "lstime": "00:00:45",
        },
        {
            "index": 1,
            "url": "stratum+tcp://stratum-ltc.antpool.com:443",
            "user": "nodg1.5.165",
            "status": "Standby",
            "priority": 1,
            "accepted": 0,
            "rejected": 0,
            "stale": 0,
            "getworks": 0,
            "lstime": "",
        },
    ],
}

WEB_POOLS_FAILOVER = {
    "POOLS": [
        {
            "index": 0,
            "url": "stratum+tcp://stratum-ltc.antpool.com:8888",
            "user": "nodg1.5.196",
            "status": "Unreachable",
            "priority": 0,
            "accepted": 69620,
            "rejected": 4,
            "stale": 35,
            "getworks": 69659,
            "lstime": "00:00:37",
        },
        {
            "index": 1,
            "url": "stratum+tcp://stratum-ltc.antpool.com:443",
            "user": "nodg1.5.196",
            "status": "Alive",
            "priority": 1,
            "accepted": 44146,
            "rejected": 0,
            "stale": 26,
            "getworks": 44172,
            "lstime": "00:00:01",
        },
    ],
}


def test_elphapex_pools_parse_last_share_from_lstime():
    miner = ElphapexDG1Plus("10.10.101.10")

    pools = asyncio.run(miner._get_pools(WEB_POOLS_HEALTHY))

    expected = int(time.time()) - 45
    assert abs(pools[0].last_share_ts - expected) <= 2


def test_elphapex_pools_standby_pool_returns_zero():
    miner = ElphapexDG1Plus("10.10.101.10")

    pools = asyncio.run(miner._get_pools(WEB_POOLS_HEALTHY))

    assert pools[1].last_share_ts == 0
    assert pools[1].alive is False


def test_elphapex_pools_failover_history_is_parsed_faithfully():
    miner = ElphapexDG1Plus("10.10.101.10")

    pools = asyncio.run(miner._get_pools(WEB_POOLS_FAILOVER))

    expected = int(time.time()) - 37
    assert abs(pools[0].last_share_ts - expected) <= 2
    assert pools[0].alive is False
    assert pools[1].alive is True


def test_elphapex_pools_keep_existing_fields():
    miner = ElphapexDG1Plus("10.10.101.10")

    pools = asyncio.run(miner._get_pools(WEB_POOLS_HEALTHY))

    assert pools[0].accepted == 9389
    assert pools[0].user == "nodg1.5.165"
    assert str(pools[0].url) == "stratum+tcp://stratum-ltc.antpool.com:8888"


def test_elphapex_parse_last_share_defensive_values():
    parse = parse_last_share_to_timestamp

    assert parse("") == 0
    assert parse("0") == 0
    assert parse(None) == 0
    assert parse("garbage") == 0
