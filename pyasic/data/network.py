from enum import Enum
from typing import Any

from pydantic import BaseModel


class NetworkMode(str, Enum):
    """The network address assignment mode of a miner."""

    DHCP = "dhcp"
    STATIC = "static"


class MinerNetworkConfig(BaseModel):
    """A Dataclass to standardize miner network configuration.

    Attributes:
        mode: Whether the address is assigned by DHCP or configured statically.
        ip: The address currently in use.
        netmask: The subnet mask currently in use.
        gateway: The gateway in use, None when the miner does not report one.
        dns: The DNS servers in use, None when the miner does not report any.
        hostname: The network hostname of the miner.
    """

    mode: NetworkMode | None = None
    ip: str | None = None
    netmask: str | None = None
    gateway: str | None = None
    dns: str | None = None
    hostname: str | None = None

    def get(self, __key: str, default: Any = None):
        try:
            val = self.__getitem__(__key)
            if val is None:
                return default
            return val
        except KeyError:
            return default

    def __getitem__(self, item: str):
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(f"{item}")
