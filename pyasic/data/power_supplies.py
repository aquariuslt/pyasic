from typing import Any

from pydantic import BaseModel


class PowerSupply(BaseModel):
    """A Dataclass to standardize power supply data.

    Attributes:
        serial_number: Serial number of power supply.
        temperature: temperature of power supply.
    """

    serial_number: str | None = None
    temperature: float | None = None

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
