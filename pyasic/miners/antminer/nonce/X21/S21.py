from pyasic.miners.backends.nonce import Nonce
from pyasic.miners.device.models import S21XP, S21Plus


class NonceS21Plus(Nonce, S21Plus):
    pass


class NonceS21XP(Nonce, S21XP):
    pass
