import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from pyasic.config import MinerConfig, MiningModeConfig, PoolConfig
from pyasic.miners.antminer.hashmaster.X21 import HashMasterS21PlusHydro


def test_hashmaster_config_serializer_matches_current_hashmaster_payload_shape():
    config = MinerConfig(
        pools=PoolConfig.simple(
            [
                {
                    "url": "stratum+tcp://stratum.test.io:3333",
                    "user": "test.worker",
                    "password": "x",
                }
            ]
        ),
        mining_mode=MiningModeConfig.power_tuning(power=3000),
    )

    assert config.as_hashmaster_am() == {
        "miner-mode": "0",
        "pools": [
            {
                "url": "stratum+tcp://stratum.test.io:3333",
                "user": "test.worker",
                "pass": "x",
            },
            {"url": "", "user": "", "pass": ""},
            {"url": "", "user": "", "pass": ""},
        ],
    }


def test_hashmaster_config_deserializer_matches_current_hashmaster_behavior():
    web_conf = {
        "pools": [
            {"url": "stratum+tcp://stratum.test.io:3333", "user": "u1", "pass": "p1"},
            {"url": "", "user": "", "pass": ""},
            {"url": "", "user": "", "pass": ""},
        ],
        "bitmain-work-mode": "0",
        "bitmain-ex-hashrate": "4600",
        "bitmain-fan-ctrl": True,
        "bitmain-fan-pwm": "90",
    }
    web_presets = {"ModeInfo": [{"Level": {"4600W": "4600", "NPM": "NPM"}}]}

    conf = MinerConfig.from_hashmaster_am(web_conf, web_presets)
    assert conf.pools.groups[0].pools[0].url == "stratum+tcp://stratum.test.io:3333"
    assert conf.pools.groups[0].pools[0].user == "u1"
    assert conf.fan_mode.mode == "manual"
    assert conf.fan_mode.speed == 90
    assert conf.mining_mode.mode == "preset"
    assert conf.mining_mode.active_preset.name == "4600W"
    assert conf.mining_mode.active_preset.hashrate is None
    assert conf.mining_mode.active_preset.power == 4600
    assert [p.name for p in conf.mining_mode.available_presets] == [
        "4600W",
        "NPM",
    ]


def test_hashmaster_backend_uses_hashmaster_config_methods(monkeypatch):
    miner = HashMasterS21PlusHydro("10.10.101.10")
    miner.web = SimpleNamespace(
        get_miner_conf=AsyncMock(
            return_value={
                "pools": [
                    {
                        "url": "stratum+tcp://stratum.test.io:3333",
                        "user": "u1",
                        "pass": "p1",
                    },
                    {"url": "", "user": "", "pass": ""},
                    {"url": "", "user": "", "pass": ""},
                ]
            }
        ),
        get_autotune_presets=AsyncMock(return_value=None),
        set_miner_conf=AsyncMock(return_value={"success": True}),
    )

    expected_config = MinerConfig()

    def _from_hashmaster_am(cls, web_conf, web_presets):
        return expected_config

    def _from_bitfufuos_am(cls, web_conf, web_presets):
        raise AssertionError("HashMaster backend should not call from_bitfufuos_am")

    monkeypatch.setattr(
        MinerConfig, "from_hashmaster_am", classmethod(_from_hashmaster_am)
    )
    monkeypatch.setattr(
        MinerConfig, "from_bitfufuos_am", classmethod(_from_bitfufuos_am)
    )

    loaded = asyncio.run(miner.get_config())
    assert loaded == expected_config

    serialized_payload = {"_ant_work_mode": 0}

    def _as_hashmaster_am(self, user_suffix=None):
        return serialized_payload

    def _as_bitfufuos_am(self, user_suffix=None):
        raise AssertionError("HashMaster backend should not call as_bitfufuos_am")

    monkeypatch.setattr(MinerConfig, "as_hashmaster_am", _as_hashmaster_am)
    monkeypatch.setattr(MinerConfig, "as_bitfufuos_am", _as_bitfufuos_am)

    asyncio.run(miner.send_config(expected_config))
    miner.web.set_miner_conf.assert_awaited_once_with(serialized_payload)
