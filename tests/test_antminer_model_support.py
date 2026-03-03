import ipaddress

from pyasic.miners.antminer.bmminer.X19 import BMMinerS19XPPlusHydro
from pyasic.miners.factory import MinerFactory, MinerTypes


def test_factory_supports_s19_xp_plus_hydro_model_string():
    miner = MinerFactory._select_miner_from_classes(
        ip=ipaddress.ip_address("10.10.101.10"),
        miner_model="Antminer S19 XP+ Hyd.",
        miner_type=MinerTypes.ANTMINER,
    )

    assert isinstance(miner, BMMinerS19XPPlusHydro)
    assert str(miner.raw_model) == "S19 XP+ Hydro"
