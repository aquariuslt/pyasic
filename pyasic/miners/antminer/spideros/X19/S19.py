from pyasic.miners.backends.spideros import SpiderOSMiner
from pyasic.miners.device.models import (
    S19,
    S19KPro,
    S19Pro,
    S19ProPlusHydro,
    S19XP,
    S19XPHydro,
    S19XPPlusHydro,
    S19jXP,
    S19jPro,
    S19jProPlus,
)


class SpiderOSS19(SpiderOSMiner, S19):
    pass


class SpiderOSS19Pro(SpiderOSMiner, S19Pro):
    pass


class SpiderOSS19jPro(SpiderOSMiner, S19jPro):
    pass


class SpiderOSS19jProPlus(SpiderOSMiner, S19jProPlus):
    pass


class SpiderOSS19KPro(SpiderOSMiner, S19KPro):
    pass


class SpiderOSS19jXP(SpiderOSMiner, S19jXP):
    pass


class SpiderOSS19XP(SpiderOSMiner, S19XP):
    pass


class SpiderOSS19XPHydro(SpiderOSMiner, S19XPHydro):
    uses_extended_hydro_temp_layout = False


class SpiderOSS19ProPlusHydro(SpiderOSMiner, S19ProPlusHydro):
    uses_extended_hydro_temp_layout = False


class SpiderOSS19XPPlusHydro(SpiderOSMiner, S19XPPlusHydro):
    uses_extended_hydro_temp_layout = False
