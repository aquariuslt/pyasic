import asyncio
from unittest.mock import AsyncMock

from pyasic.config.mining import MiningModeNormal, MiningModeSleep
from pyasic.miners.whatsminer.btminer.M6X.M63S import BTMinerM63SVK20

# captured from a real M63S (farm Kuching), firmware 20250304.15.REL
RPC_POOLS = {
    "STATUS": [{"STATUS": "S", "Msg": "2 Pool(s)"}],
    "POOLS": [
        {
            "POOL": 1,
            "URL": "stratum+tcp://btc-asia.f2pool.com:1314",
            "Status": "Alive",
            "Priority": 0,
            "Accepted": 1,
            "Rejected": 671,
            "Get Failures": 671,
            "Remote Failures": 0,
            "User": "worker.001",
            "Last Share Time": 0,
            "Stratum Active": True,
        },
        {
            "POOL": 2,
            "URL": "stratum+tcp://ss.antpool.com:3333",
            "Status": "Alive",
            "Priority": 1,
            "Accepted": 1,
            "Rejected": 0,
            "Get Failures": 0,
            "Remote Failures": 0,
            "User": "worker.001",
            # some firmwares omit "Last Share Time" entirely
            "Stratum Active": False,
        },
    ],
    "id": 1,
}


def test_btminer_pools_zero_last_share_is_kept_as_zero():
    miner = BTMinerM63SVK20("10.10.101.10")
    pools_data = dict(RPC_POOLS)

    pools = asyncio.run(miner._get_pools(pools_data))

    assert pools[0].last_share_ts == 0


def test_btminer_pools_missing_last_share_field_is_none():
    miner = BTMinerM63SVK20("10.10.101.10")

    pools = asyncio.run(miner._get_pools(RPC_POOLS))

    assert pools[1].last_share_ts is None


def test_btminer_pools_epoch_last_share_passes_through():
    miner = BTMinerM63SVK20("10.10.101.10")
    pools_data = {
        "POOLS": [
            {
                "POOL": 1,
                "URL": "stratum+tcp://ss.antpool.com:3333",
                "Status": "Alive",
                "Accepted": 100,
                "Rejected": 0,
                "User": "worker.001",
                "Last Share Time": 1784044804,
                "Stratum Active": True,
            }
        ],
    }

    pools = asyncio.run(miner._get_pools(pools_data))

    assert pools[0].last_share_ts == 1784044804


def test_btminer_get_config_uses_injected_data_without_rpc_call(monkeypatch):
    miner = BTMinerM63SVK20("10.10.101.10")
    multicommand = AsyncMock(side_effect=AssertionError("rpc should not be called"))
    monkeypatch.setattr(miner.rpc, "multicommand", multicommand)

    rpc_status = {"Msg": {"mineroff": "false"}}
    rpc_summary = {"SUMMARY": [{"Power Mode": "Normal"}]}

    config = asyncio.run(
        miner._get_config(
            rpc_pools=RPC_POOLS,
            rpc_summary=rpc_summary,
            rpc_status=rpc_status,
        )
    )

    multicommand.assert_not_awaited()
    assert isinstance(config.mining_mode, MiningModeNormal)


def test_btminer_get_config_marks_sleep_when_not_mining(monkeypatch):
    miner = BTMinerM63SVK20("10.10.101.10")
    monkeypatch.setattr(
        miner.rpc,
        "multicommand",
        AsyncMock(side_effect=AssertionError("rpc should not be called")),
    )

    rpc_status = {"Msg": {"mineroff": "true"}}
    rpc_summary = {"SUMMARY": [{"Power Mode": "Normal"}]}

    config = asyncio.run(
        miner._get_config(
            rpc_pools=RPC_POOLS,
            rpc_summary=rpc_summary,
            rpc_status=rpc_status,
        )
    )

    assert isinstance(config.mining_mode, MiningModeSleep)
