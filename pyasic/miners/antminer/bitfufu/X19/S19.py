from pyasic.miners.backends.bitfufu import BitfufuMiner
from pyasic.miners.device.models import (
    S19XP,
    S19,
    S19KPro,
    S19Pro,
    S19ProPlusHydro,
    S19XPHydro,
    S19jPro,
    S19jProPlus,
)


class BitfufuS19Ex(BitfufuMiner, S19):
    pass


class BitfufuS19ProEx(BitfufuMiner, S19Pro):
    pass


class BitfufuS19jProEx(BitfufuMiner, S19jPro):
    pass


class BitfufuS19jProPlusEx(BitfufuMiner, S19jProPlus):
    pass


class BitfufuS19KProEx(BitfufuMiner, S19KPro):
    pass


class BitfufuS19XPEx(BitfufuMiner, S19XP):
    pass


class BitfufuS19XPHydroEx(BitfufuMiner, S19XPHydro):
    pass


class BitfufuS19ProPlusHydroEx(BitfufuMiner, S19ProPlusHydro):
    pass
