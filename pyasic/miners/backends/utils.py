from __future__ import annotations

from typing import Any

_INVALID_SERIAL_NUMBER_VALUES = {
    "",
    "n/a",
    "na",
    "none",
    "null",
    "unknown",
}


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
