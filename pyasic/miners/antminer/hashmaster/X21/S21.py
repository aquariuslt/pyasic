from pyasic.miners.backends.hashmaster import HashMasterMiner
from pyasic.miners.device.models import (
    S21EHydro,
    S21EXPHydro,
    S21Hydro,
    S21PlusHydro,
    S21XP,
    T21,
)


class HashMasterS21XP(HashMasterMiner, S21XP):
    pass


class HashMasterS21PlusHydro(HashMasterMiner, S21PlusHydro):
    pass


class HashMasterS21Hydro(HashMasterMiner, S21Hydro):
    pass


class HashMasterS21EHydro(HashMasterMiner, S21EHydro):
    pass


class HashMasterS21EXPHydro(HashMasterMiner, S21EXPHydro):
    pass


class HashMasterT21(HashMasterMiner, T21):
    pass
