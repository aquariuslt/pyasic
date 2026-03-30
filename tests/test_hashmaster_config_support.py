import asyncio
import warnings
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import requests

from pyasic.config import MinerConfig, MiningModeConfig, PoolConfig
from pyasic.errors import APIWarning
from pyasic.miners.antminer.hashmaster.X21 import HashMasterS21PlusHydro
from pyasic.miners.data import DataOptions
from pyasic.web.hashmaster import HashMasterAntminerWebAPI, HttpClient


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


def test_hashmaster_get_data_returns_empty_serial_number_on_6060_connection_error(
    monkeypatch,
):
    miner = HashMasterS21PlusHydro("10.10.101.10")

    monkeypatch.setattr(
        miner.web,
        "multicommand",
        AsyncMock(return_value={"multicommand": True, "get_system_info": {}}),
    )
    monkeypatch.setattr(
        HttpClient,
        "get",
        AsyncMock(
            side_effect=requests.exceptions.ConnectionError(
                "HTTPConnectionPool(host='10.10.101.10', port=6060): Failed to establish a new connection"
            )
        ),
    )

    with pytest.warns(
        APIWarning,
        match=r"HashMaster 6060 endpoint get_sn on 10\.10\.101\.10",
    ):
        miner_data = asyncio.run(miner.get_data(include=[DataOptions.SERIAL_NUMBER]))

    assert miner_data.serial_number is None


def test_hashmaster_http_get_only_warns_for_6060(monkeypatch):
    api = HashMasterAntminerWebAPI("10.10.101.10")

    monkeypatch.setattr(
        HttpClient,
        "get",
        AsyncMock(
            side_effect=requests.exceptions.ConnectionError(
                "HTTPConnectionPool(host='10.10.101.10', port=80): Failed to establish a new connection"
            )
        ),
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        response = asyncio.run(api._invoke_http_get("get_system_info", 80))

    assert response["success"] is False
    assert len(caught) == 0


def test_hashmaster_http_get_keeps_timeout_handling(monkeypatch):
    api = HashMasterAntminerWebAPI("10.10.101.10")

    monkeypatch.setattr(
        HttpClient,
        "get",
        AsyncMock(side_effect=requests.exceptions.Timeout("request timed out")),
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        response = asyncio.run(api._invoke_http_get("get_sn", 6060))

    assert response["success"] is False
    assert "Timeout error occurred" in response["message"]
    assert len(caught) == 0
