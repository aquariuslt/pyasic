from pyasic.miners.backends.spideros import SpiderOSMiner
from pyasic.miners.device.models import (
    S21,
    S21EHydro,
    S21EXPHydro,
    S21Hydro,
    S21PlusHydro,
    S21XP,
)


class SpiderOSS21(SpiderOSMiner, S21):
    pass


class SpiderOSS21XP(SpiderOSMiner, S21XP):
    pass


class SpiderOSS21PlusHydro(SpiderOSMiner, S21PlusHydro):
    pass


class SpiderOSS21Hydro(SpiderOSMiner, S21Hydro):
    pass


class SpiderOSS21EHydro(SpiderOSMiner, S21EHydro):
    pass


class SpiderOSS21EXPHydro(SpiderOSMiner, S21EXPHydro):
    pass
