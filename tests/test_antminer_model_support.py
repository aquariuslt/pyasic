import asyncio
import ipaddress
import json

from pyasic.device.firmware import MinerFirmware
from pyasic.miners.antminer.bmminer.X21 import BMMinerS21PlusHydro
from pyasic.miners.antminer.bmminer.X19 import BMMinerS19XPPlusHydro
from pyasic.miners.antminer.hashmaster.X21 import HashMasterS21PlusHydro
from pyasic.miners.factory import MinerFactory, MinerTypes


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


def test_factory_detects_hashmaster_backend_for_s21_plus_hyd():
    miner = MinerFactory._select_miner_from_classes(
        ip=ipaddress.ip_address("10.10.101.10"),
        miner_model="Antminer S21+ Hyd (HashMaster)",
        miner_type=MinerTypes.HASHMASTER,
    )

    assert isinstance(miner, HashMasterS21PlusHydro)
    assert str(miner.raw_model) == "S21+ Hydro"
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


def test_factory_parses_hashmaster_socket_type():
    socket_payload = json.dumps(
        {
            "VERSION": [
                {
                    "Type": "Antminer S21+ Hyd (HashMaster)",
                    "API": "3.1",
                }
            ]
        }
    )

    miner_type = MinerFactory._parse_socket_type(socket_payload)

    assert miner_type == MinerTypes.HASHMASTER
