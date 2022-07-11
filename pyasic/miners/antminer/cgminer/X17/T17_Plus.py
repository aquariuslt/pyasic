from pyasic.miners._backends import CGMiner  # noqa - Ignore access to _module
from pyasic.miners._types import T17Plus  # noqa - Ignore access to _module


class CGMinerT17Plus(CGMiner, T17Plus):
    def __init__(self, ip: str) -> None:
        super().__init__(ip)
        self.ip = ip