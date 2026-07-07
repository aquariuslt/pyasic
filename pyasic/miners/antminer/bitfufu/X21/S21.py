from pyasic.miners.backends.bitfufu import BitfufuMiner
from pyasic.miners.device.models import S21, S21Hydro


class BitfufuS21Ex(BitfufuMiner, S21):
    pass


class BitfufuS21HydroEx(BitfufuMiner, S21Hydro):
    pass
