import asyncio
import ipaddress
import json
from unittest.mock import AsyncMock, call

from pyasic.device.firmware import MinerFirmware
from pyasic.miners.antminer.spideros.X19 import (
    SpiderOSS19,
    SpiderOSS19KPro,
    SpiderOSS19Pro,
    SpiderOSS19ProPlusHydro,
    SpiderOSS19XP,
    SpiderOSS19XPHydro,
    SpiderOSS19XPPlusHydro,
    SpiderOSS19jXP,
    SpiderOSS19jPro,
    SpiderOSS19jProPlus,
)
from pyasic.miners.antminer.spideros.X21 import (
    SpiderOSS21,
    SpiderOSS21EHydro,
    SpiderOSS21EXPHydro,
    SpiderOSS21Hydro,
    SpiderOSS21PlusHydro,
    SpiderOSS21XP,
    SpiderOST21,
)
from pyasic.miners.factory import MinerFactory, MinerTypes


SPIDEROS_MODEL_CASES = [
    ("Antminer S19 (SPOS)", SpiderOSS19, "S19"),
    ("Antminer S19 Pro (SPOS)", SpiderOSS19Pro, "S19 Pro"),
    ("Antminer S19j Pro (SPOS)", SpiderOSS19jPro, "S19j Pro"),
    ("Antminer S19j Pro+ (SPOS)", SpiderOSS19jProPlus, "S19j Pro+"),
    ("Antminer S19K Pro (SPOS)", SpiderOSS19KPro, "S19K Pro"),
    ("Antminer S19j XP (SPOS)", SpiderOSS19jXP, "S19j XP"),
    ("Antminer S19 XP (SPOS)", SpiderOSS19XP, "S19 XP"),
    ("Antminer S19 XP Hyd (SPOS)", SpiderOSS19XPHydro, "S19 XP Hydro"),
    ("Antminer S19 Pro+ Hyd (SPOS)", SpiderOSS19ProPlusHydro, "S19 Pro+ Hydro"),
    ("Antminer S19 XP+ Hyd (SPOS)", SpiderOSS19XPPlusHydro, "S19 XP+ Hydro"),
    ("Antminer S21 (SPOS)", SpiderOSS21, "S21"),
    ("Antminer T21 (SPOS)", SpiderOST21, "T21"),
    ("Antminer S21 XP (SPOS)", SpiderOSS21XP, "S21 XP"),
    ("Antminer S21+ Hyd (SPOS)", SpiderOSS21PlusHydro, "S21+ Hydro"),
    ("Antminer S21 Hyd (SPOS)", SpiderOSS21Hydro, "S21 Hydro"),
    ("Antminer S21E Hyd (SPOS)", SpiderOSS21EHydro, "S21e Hydro"),
    ("Antminer S21E XP Hyd (SPOS)", SpiderOSS21EXPHydro, "S21e XP Hydro"),
]


def test_factory_supports_spideros_model_strings():
    for miner_model, expected_class, expected_raw_model in SPIDEROS_MODEL_CASES:
        miner = MinerFactory._select_miner_from_classes(
            ip=ipaddress.ip_address("10.10.101.10"),
            miner_model=miner_model,
            miner_type=MinerTypes.SPIDER_OS,
        )

        assert isinstance(miner, expected_class)
        assert str(miner.raw_model) == expected_raw_model
        assert miner.firmware == MinerFirmware.SPIDER_OS


def test_factory_parses_spideros_socket_type():
    socket_payload = json.dumps(
        {
            "VERSION": [
                {
                    "Type": SPIDEROS_MODEL_CASES[0][0],
                    "API": "3.1",
                }
            ]
        }
    )

    miner_type = MinerFactory._parse_socket_type(socket_payload)

    assert miner_type == MinerTypes.SPIDER_OS


def test_factory_roundtrip_detects_spideros_model(monkeypatch):
    miner_model, expected_class, expected_raw_model = SPIDEROS_MODEL_CASES[0]
    factory = MinerFactory()
    send_api_command = AsyncMock(
        return_value={"VERSION": [{"Type": miner_model, "API": "3.1"}]}
    )

    monkeypatch.setattr(
        factory, "_get_miner_type", AsyncMock(return_value=MinerTypes.SPIDER_OS)
    )
    monkeypatch.setattr(factory, "send_api_command", send_api_command)

    miner = asyncio.run(factory.get_miner("10.10.101.10"))

    assert send_api_command.await_args_list == [call("10.10.101.10", "version")]
    assert isinstance(miner, expected_class)
    assert str(miner.raw_model) == expected_raw_model
    assert miner.firmware == MinerFirmware.SPIDER_OS
