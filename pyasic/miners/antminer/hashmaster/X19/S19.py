from pyasic.miners.backends.hashmaster import HashMasterMiner
from pyasic.miners.device.models import S19XP
from pyasic.miners.device.models import S19XPHydro
from pyasic.miners.device.models import S19XPPlusHydro


class HashMasterS19XP(HashMasterMiner, S19XP):
    pass


class HashMasterS19XPHydro(HashMasterMiner, S19XPHydro):
    pass


class HashMasterS19XPPlusHydro(HashMasterMiner, S19XPPlusHydro):
    pass
