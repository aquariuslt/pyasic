import asyncio
import ipaddress
import json

import pytest

from pyasic.device.firmware import MinerFirmware
from pyasic.miners.antminer.bmminer.X21 import BMMinerS21PlusHydro
from pyasic.miners.antminer.bmminer.X21 import BMMinerS21XP
from pyasic.miners.antminer.bmminer.X19 import BMMinerS19XPPlusHydro
from pyasic.miners.antminer.bitfufu.X19 import (
    BitfufuS19Ex,
    BitfufuS19KProEx,
    BitfufuS19ProEx,
    BitfufuS19ProPlusHydroEx,
    BitfufuS19XPEx,
    BitfufuS19XPHydroEx,
    BitfufuS19jXPEx,
    BitfufuS19jProEx,
    BitfufuS19jProPlusEx,
)
from pyasic.miners.antminer.bitfufu.X21 import BitfufuS21Ex, BitfufuT21Ex
from pyasic.miners.antminer.hashmaster.X21 import (
    HashMasterS21PlusHydro,
    HashMasterS21EXPHydro,
    HashMasterS21XP,
)
from pyasic.miners.antminer.hashmaster.X19 import HashMasterS19XPHydro
from pyasic.miners.factory import MinerFactory, MinerTypes


BITFUFU_MODEL_CASES = [
    ("ANTMINER S21 EX", BitfufuS21Ex, "S21"),
    ("ANTMINER T21 EX", BitfufuT21Ex, "T21"),
    ("ANTMINER S19K PRO EX", BitfufuS19KProEx, "S19K Pro"),
    ("ANTMINER S19J PRO+ EX", BitfufuS19jProPlusEx, "S19j Pro+"),
    ("ANTMINER S19J PRO EX", BitfufuS19jProEx, "S19j Pro"),
    ("ANTMINER S19J XP EX", BitfufuS19jXPEx, "S19j XP"),
    ("ANTMINER S19 PRO EX", BitfufuS19ProEx, "S19 Pro"),
    ("ANTMINER S19 EX", BitfufuS19Ex, "S19"),
    ("ANTMINER S19 PRO+ HYD EX", BitfufuS19ProPlusHydroEx, "S19 Pro+ Hydro"),
    ("ANTMINER S19 XP EX", BitfufuS19XPEx, "S19 XP"),
    ("ANTMINER S19 XP HYD EX", BitfufuS19XPHydroEx, "S19 XP Hydro"),
]

HASHMASTER_MODEL_CASES = [
    ("Antminer S19 XP Hyd (HashMaster)", HashMasterS19XPHydro, "S19 XP Hydro"),
    ("Antminer S21+ Hyd (HashMaster)", HashMasterS21PlusHydro, "S21+ Hydro"),
    ("Antminer S21e XP Hyd (HashMaster)", HashMasterS21EXPHydro, "S21e XP Hydro"),
    ("Antminer S21 XP (HashMaster)", HashMasterS21XP, "S21 XP"),
]


def test_factory_supports_s19_xp_plus_hydro_model_string():
    miner = MinerFactory._select_miner_from_classes(
        ip=ipaddress.ip_address("10.10.101.10"),
        miner_model="Antminer S19 XP+ Hyd.",
        miner_type=MinerTypes.ANTMINER,
    )

    assert isinstance(miner, BMMinerS19XPPlusHydro)
    assert str(miner.raw_model) == "S19 XP+ Hydro"


def test_factory_supports_s21_plus_hyd_model_string():
    miner = MinerFactory._select_miner_from_classes(
        ip=ipaddress.ip_address("10.10.101.10"),
        miner_model="Antminer S21+ Hyd",
        miner_type=MinerTypes.ANTMINER,
    )

    assert isinstance(miner, BMMinerS21PlusHydro)
    assert str(miner.raw_model) == "S21+ Hydro"


def test_factory_supports_s21_xp_model_string():
    miner = MinerFactory._select_miner_from_classes(
        ip=ipaddress.ip_address("10.10.101.10"),
        miner_model="Antminer S21 XP",
        miner_type=MinerTypes.ANTMINER,
    )

    assert isinstance(miner, BMMinerS21XP)
    assert str(miner.raw_model) == "S21 XP"


@pytest.mark.parametrize(
    ("miner_model", "expected_class", "expected_raw_model"),
    BITFUFU_MODEL_CASES,
)
def test_factory_supports_bitfufu_ex_model_strings(
    miner_model, expected_class, expected_raw_model
):
    miner = MinerFactory._select_miner_from_classes(
        ip=ipaddress.ip_address("10.10.101.10"),
        miner_model=miner_model,
        miner_type=MinerTypes.BITFUFU,
    )

    assert isinstance(miner, expected_class)
    assert str(miner.raw_model) == expected_raw_model


@pytest.mark.parametrize(
    ("miner_model", "expected_class", "expected_raw_model"),
    HASHMASTER_MODEL_CASES,
)
def test_factory_detects_hashmaster_backend_for_models(
    miner_model, expected_class, expected_raw_model
):
    miner = MinerFactory._select_miner_from_classes(
        ip=ipaddress.ip_address("10.10.101.10"),
        miner_model=miner_model,
        miner_type=MinerTypes.HASHMASTER,
    )

    assert isinstance(miner, expected_class)
    assert str(miner.raw_model) == expected_raw_model
    assert miner.firmware == MinerFirmware.HASHMASTER


def test_hashmaster_miner_reads_fw_version_from_rpc_version():
    miner = HashMasterS21PlusHydro("10.10.101.10")
    fw_ver = asyncio.run(
        miner._get_fw_ver(
            rpc_version={
                "VERSION": [
                    {
                        "CompileTime": "Wed Feb 25 11:26:50 CST 2026",
                        "Type": "Antminer S21+ Hyd (HashMaster)",
                    }
                ]
            }
        )
    )

    assert fw_ver == "Wed Feb 25 11:26:50 CST 2026"
    assert miner.firmware == MinerFirmware.HASHMASTER


@pytest.mark.parametrize(
    ("miner_model", "_expected_class", "_expected_raw_model"),
    HASHMASTER_MODEL_CASES,
)
def test_factory_parses_hashmaster_socket_type(
    miner_model, _expected_class, _expected_raw_model
):
    socket_payload = json.dumps(
        {
            "VERSION": [
                {
                    "Type": miner_model,
                    "API": "3.1",
                }
            ]
        }
    )

    miner_type = MinerFactory._parse_socket_type(socket_payload)

    assert miner_type == MinerTypes.HASHMASTER


@pytest.mark.parametrize(
    "miner_model",
    [model for model, _, _ in BITFUFU_MODEL_CASES],
)
def test_factory_parses_bitfufu_ex_socket_type(miner_model):
    socket_payload = json.dumps(
        {
            "VERSION": [
                {
                    "Type": miner_model,
                    "API": "3.1",
                }
            ]
        }
    )

    miner_type = MinerFactory._parse_socket_type(socket_payload)

    assert miner_type == MinerTypes.BITFUFU
