from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from pyasic.data.boards import HashBoard
from pyasic.device.firmware import MinerFirmware
from pyasic.device.models import MinerModel

_INVALID_SERIAL_NUMBER_VALUES = {
    "",
    "n/a",
    "na",
    "none",
    "null",
    "unknown",
}


def parse_last_share_to_timestamp(last_share_time: str) -> int:
    """
    Parse the last share time (elapsed since last share) to a unix timestamp.
    :params last_share_time: elapsed time in ``HH:MM:SS`` since the last share,
        e.g. ``"00:00:07"`` means the last share happened 7 seconds ago.
        Hours may exceed 24 (e.g. ``"68:40:44"``).
        ``"0"``, an empty string or ``None`` means no shares have been submitted.
    """
    if not last_share_time or last_share_time == "0":
        return 0
    try:
        h, m, s = (int(x) for x in last_share_time.split(":"))
        return int(time.time()) - (h * 3600 + m * 60 + s)
    except (ValueError, AttributeError):
        logging.debug(f"Failed to parse last share time: {last_share_time}")
        return 0


def normalize_antminer_like_serial_number(serial_number: Any) -> str | None:
    if serial_number is None:
        return None

    if not isinstance(serial_number, str):
        serial_number = str(serial_number)

    normalized = serial_number.strip()
    if normalized == "":
        return None

    lowered = normalized.lower()
    if lowered in _INVALID_SERIAL_NUMBER_VALUES:
        return None
    if "error" in lowered:
        return None

    alnum = "".join(ch for ch in normalized if ch.isalnum())
    if len(alnum) >= 6 and set(alnum) == {"0"}:
        return None

    return normalized


@dataclass(frozen=True)
class TemperatureSource:
    field: str
    index: int | None = None


@dataclass(frozen=True)
class TemperatureReading:
    sources: tuple[TemperatureSource, ...]
    average: bool = False


@dataclass(frozen=True)
class TemperatureLayout:
    inlet_temp: TemperatureReading | None = None
    outlet_temp: TemperatureReading | None = None
    chip_temp: TemperatureReading | None = None
    temp: TemperatureReading | None = None


def _temperature_reading(field: str, index: int) -> TemperatureReading:
    return TemperatureReading((TemperatureSource(field, index),))


def _empty_temperature_reading() -> TemperatureReading:
    return TemperatureReading(())


def _average_temperature_field(field: str) -> TemperatureReading:
    return TemperatureReading((TemperatureSource(field),), average=True)


def _average_temperature_sources(
    *sources: TemperatureSource,
) -> TemperatureReading:
    return TemperatureReading(sources, average=True)


ANTMINER_DEFAULT_TEMPERATURE_LAYOUT = TemperatureLayout(
    chip_temp=_average_temperature_field("temp_chip"),
    temp=_average_temperature_field("temp_pcb"),
)


ANTMINER_AIR_TEMPERATURE_LAYOUT = TemperatureLayout(
    inlet_temp=_temperature_reading("temp_chip", 0),
    outlet_temp=_temperature_reading("temp_chip", 2),
)

ANTMINER_S21_PLUS_HYDRO_TEMPERATURE_LAYOUT = TemperatureLayout(
    inlet_temp=_temperature_reading("temp_pcb", 0),
    outlet_temp=_temperature_reading("temp_pcb", 2),
    chip_temp=_temperature_reading("temp_pic", 0),
    temp=_average_temperature_sources(
        TemperatureSource("temp_pic", 1),
        TemperatureSource("temp_pic", 2),
        TemperatureSource("temp_pic", 3),
        TemperatureSource("temp_pcb", 1),
        TemperatureSource("temp_pcb", 3),
    ),
)

ANTMINER_S21_XP_HYDRO_TEMPERATURE_LAYOUT = TemperatureLayout(
    inlet_temp=_temperature_reading("temp_pcb", 0),
    outlet_temp=_temperature_reading("temp_pcb", 2),
    chip_temp=_temperature_reading("temp_pic", 0),
    temp=_average_temperature_sources(
        TemperatureSource("temp_pic", 1),
        TemperatureSource("temp_pic", 2),
        TemperatureSource("temp_pic", 3),
        TemperatureSource("temp_pcb", 1),
        TemperatureSource("temp_pcb", 3),
    ),
)

ANTMINER_S19_XP_PLUS_HYDRO_TEMPERATURE_LAYOUT = TemperatureLayout(
    inlet_temp=_temperature_reading("temp_pic", 2),
    outlet_temp=_temperature_reading("temp_pic", 1),
    chip_temp=_empty_temperature_reading(),
    temp=_average_temperature_sources(
        TemperatureSource("temp_pic", 0),
        TemperatureSource("temp_pic", 3),
    ),
)

_ANTMINER_TEMPERATURE_LAYOUT_BY_MODEL_AND_FIRMWARE = {
    (MinerModel.ANTMINER.S21PlusHydro, MinerFirmware.STOCK): (
        ANTMINER_S21_PLUS_HYDRO_TEMPERATURE_LAYOUT
    ),
    (MinerModel.ANTMINER.S21PlusHydro, MinerFirmware.SPIDER_OS): (
        ANTMINER_S21_PLUS_HYDRO_TEMPERATURE_LAYOUT
    ),
    (MinerModel.ANTMINER.S21XPHydro, MinerFirmware.STOCK): (
        ANTMINER_S21_XP_HYDRO_TEMPERATURE_LAYOUT
    ),
    (MinerModel.ANTMINER.S21XPHydro, MinerFirmware.SPIDER_OS): (
        ANTMINER_S21_XP_HYDRO_TEMPERATURE_LAYOUT
    ),
    (MinerModel.ANTMINER.S19XPPlusHydro, MinerFirmware.STOCK): (
        ANTMINER_S19_XP_PLUS_HYDRO_TEMPERATURE_LAYOUT
    ),
    (MinerModel.ANTMINER.S19XPPlusHydro, MinerFirmware.SPIDER_OS): (
        ANTMINER_S19_XP_PLUS_HYDRO_TEMPERATURE_LAYOUT
    ),
}


def _avg_nonzero(values: list[Any] | None) -> float | None:
    if not values:
        return None
    numeric_values = [
        value for value in values if isinstance(value, (int, float)) and value != 0
    ]
    if not numeric_values:
        return 0
    return sum(numeric_values) / len(numeric_values)


def _temperature_at(board: dict, source: TemperatureSource) -> Any:
    if source.index is None:
        return None

    values = board.get(source.field)
    if not isinstance(values, list):
        return None
    try:
        return values[source.index]
    except IndexError:
        return None


def _avg_temperature_sources(
    board: dict, sources: tuple[TemperatureSource, ...]
) -> float:
    values = [
        value
        for value in (_temperature_at(board, source) for source in sources)
        if isinstance(value, (int, float)) and value != 0
    ]
    return sum(values) / len(values) if values else 0


def _temperature_from_reading(
    board: dict, reading: TemperatureReading
) -> float | Any | None:
    if not reading.sources:
        return None

    if reading.average:
        if len(reading.sources) == 1 and reading.sources[0].index is None:
            return _avg_nonzero(board.get(reading.sources[0].field))
        return _avg_temperature_sources(board, reading.sources)

    return _temperature_at(board, reading.sources[0])


def _merge_temperature_layout(
    layout: TemperatureLayout | None,
) -> TemperatureLayout:
    if layout is None:
        return ANTMINER_DEFAULT_TEMPERATURE_LAYOUT

    return TemperatureLayout(
        inlet_temp=layout.inlet_temp or ANTMINER_DEFAULT_TEMPERATURE_LAYOUT.inlet_temp,
        outlet_temp=layout.outlet_temp
        or ANTMINER_DEFAULT_TEMPERATURE_LAYOUT.outlet_temp,
        chip_temp=layout.chip_temp or ANTMINER_DEFAULT_TEMPERATURE_LAYOUT.chip_temp,
        temp=layout.temp or ANTMINER_DEFAULT_TEMPERATURE_LAYOUT.temp,
    )


def apply_antminer_temperature_layout(
    hashboard: HashBoard,
    board: dict,
    layout: TemperatureLayout | None,
) -> None:
    layout = _merge_temperature_layout(layout)

    if layout.temp is not None:
        hashboard.temp = _temperature_from_reading(board, layout.temp)
    if layout.chip_temp is not None:
        hashboard.chip_temp = _temperature_from_reading(board, layout.chip_temp)
    if layout.inlet_temp is not None:
        hashboard.inlet_temp = _temperature_from_reading(board, layout.inlet_temp)
    if layout.outlet_temp is not None:
        hashboard.outlet_temp = _temperature_from_reading(board, layout.outlet_temp)


def _is_antminer_hydro_model(raw_model: Any) -> bool:
    return "hyd" in str(raw_model).casefold()


def _get_hashmaster_antminer_temperature_layout(
    raw_model: Any,
) -> TemperatureLayout | None:
    if _is_antminer_hydro_model(raw_model):
        return ANTMINER_S21_PLUS_HYDRO_TEMPERATURE_LAYOUT
    return None


def _get_bitfufu_antminer_temperature_layout(
    raw_model: Any,
) -> TemperatureLayout | None:
    if _is_antminer_hydro_model(raw_model):
        return ANTMINER_S21_PLUS_HYDRO_TEMPERATURE_LAYOUT
    return None


def get_antminer_temperature_layout(
    raw_model: Any,
    firmware: MinerFirmware | None,
) -> TemperatureLayout | None:
    # Preserve master: Stock/SpiderOS hydro uses explicit model whitelists;
    # HashMaster/Bitfufu keep extended layout for all hydro models.
    layout = _ANTMINER_TEMPERATURE_LAYOUT_BY_MODEL_AND_FIRMWARE.get(
        (raw_model, firmware)
    )
    if layout is not None:
        return layout

    # Preserve branch behavior: T21/S19XP air inlet/outlet applies to
    # all non-hydro Antminer-like models.
    if not _is_antminer_hydro_model(raw_model):
        return ANTMINER_AIR_TEMPERATURE_LAYOUT

    if firmware == MinerFirmware.HASHMASTER:
        return _get_hashmaster_antminer_temperature_layout(raw_model)

    if firmware == MinerFirmware.BITFUFU_OS:
        return _get_bitfufu_antminer_temperature_layout(raw_model)

    return None


def build_antminer_temperature_raw(
    source: str, rpc_stats: dict | None
) -> list[dict[str, Any]]:
    if rpc_stats is None:
        return []

    temperature_raw: list[dict[str, Any]] = []
    try:
        chains = rpc_stats["STATS"][0]["chain"]
    except LookupError:
        return temperature_raw

    for board in chains:
        if not isinstance(board, dict):
            continue
        item: dict[str, Any] = {
            "source": source,
            "chain_index": board.get("index"),
        }
        for field in ("temp_chip", "temp_pcb", "temp_pic"):
            if field in board:
                item[field] = board[field]
        temperature_raw.append(item)

    return temperature_raw
