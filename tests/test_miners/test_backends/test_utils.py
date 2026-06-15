from pathlib import Path

import pytest

from pyasic.data import HashBoard
from pyasic.device.firmware import MinerFirmware
from pyasic.device.models import MinerModel
from pyasic.miners.backends.utils import (
    ANTMINER_AIR_TEMPERATURE_LAYOUT,
    ANTMINER_S19_XP_PLUS_HYDRO_TEMPERATURE_LAYOUT,
    ANTMINER_S21_PLUS_HYDRO_TEMPERATURE_LAYOUT,
    ANTMINER_S21_XP_HYDRO_TEMPERATURE_LAYOUT,
    TemperatureLayout,
    TemperatureReading,
    TemperatureSource,
    apply_antminer_temperature_layout,
    get_antminer_temperature_layout,
)


@pytest.mark.parametrize(
    ("raw_model", "firmware", "expected_layout"),
    [
        (
            MinerModel.ANTMINER.S21PlusHydro,
            MinerFirmware.STOCK,
            ANTMINER_S21_PLUS_HYDRO_TEMPERATURE_LAYOUT,
        ),
        (
            MinerModel.ANTMINER.S21XPHydro,
            MinerFirmware.STOCK,
            ANTMINER_S21_XP_HYDRO_TEMPERATURE_LAYOUT,
        ),
        (
            MinerModel.ANTMINER.S19XPPlusHydro,
            MinerFirmware.STOCK,
            ANTMINER_S19_XP_PLUS_HYDRO_TEMPERATURE_LAYOUT,
        ),
        (MinerModel.ANTMINER.S19XPHydro, MinerFirmware.STOCK, None),
        (MinerModel.ANTMINER.S21Hydro, MinerFirmware.STOCK, None),
        (
            MinerModel.ANTMINER.S21PlusHydro,
            MinerFirmware.SPIDER_OS,
            ANTMINER_S21_PLUS_HYDRO_TEMPERATURE_LAYOUT,
        ),
        (
            MinerModel.ANTMINER.S21XPHydro,
            MinerFirmware.SPIDER_OS,
            ANTMINER_S21_XP_HYDRO_TEMPERATURE_LAYOUT,
        ),
        (
            MinerModel.ANTMINER.S19XPPlusHydro,
            MinerFirmware.SPIDER_OS,
            ANTMINER_S19_XP_PLUS_HYDRO_TEMPERATURE_LAYOUT,
        ),
        (MinerModel.ANTMINER.S19XPHydro, MinerFirmware.SPIDER_OS, None),
        (MinerModel.ANTMINER.S21Hydro, MinerFirmware.SPIDER_OS, None),
        (
            MinerModel.ANTMINER.S19XPHydro,
            MinerFirmware.HASHMASTER,
            ANTMINER_S21_PLUS_HYDRO_TEMPERATURE_LAYOUT,
        ),
        (
            MinerModel.ANTMINER.S21EXPHydro,
            MinerFirmware.HASHMASTER,
            ANTMINER_S21_PLUS_HYDRO_TEMPERATURE_LAYOUT,
        ),
        (
            MinerModel.ANTMINER.S19ProPlusHydro,
            MinerFirmware.BITFUFU_OS,
            ANTMINER_S21_PLUS_HYDRO_TEMPERATURE_LAYOUT,
        ),
        (
            MinerModel.ANTMINER.S19XPHydro,
            MinerFirmware.BITFUFU_OS,
            ANTMINER_S21_PLUS_HYDRO_TEMPERATURE_LAYOUT,
        ),
        (
            MinerModel.ANTMINER.S21,
            MinerFirmware.STOCK,
            ANTMINER_AIR_TEMPERATURE_LAYOUT,
        ),
        (
            MinerModel.ANTMINER.T21,
            MinerFirmware.HASHMASTER,
            ANTMINER_AIR_TEMPERATURE_LAYOUT,
        ),
        (MinerModel.ANTMINER.S19XPHydro, MinerFirmware.VNISH, None),
        ("unknown hydro model", None, None),
    ],
)
def test_get_antminer_temperature_layout_resolves_by_model_and_firmware(
    raw_model,
    firmware,
    expected_layout,
):
    assert get_antminer_temperature_layout(raw_model, firmware) is expected_layout


def _master_avg_nonzero(values):
    values = list(filter(lambda value: value != 0, values))
    return sum(values) / len(values) if len(values) > 0 else 0


def _master_standard_temperature_values(board):
    return {
        "temp": _master_avg_nonzero(board["temp_pcb"]),
        "chip_temp": _master_avg_nonzero(board["temp_chip"]),
    }


def _master_extended_hydro_temperature_values(board):
    return {
        "inlet_temp": board["temp_pcb"][0],
        "outlet_temp": board["temp_pcb"][2],
        "chip_temp": board["temp_pic"][0],
        "temp": _master_avg_nonzero(
            [
                board["temp_pic"][1],
                board["temp_pic"][2],
                board["temp_pic"][3],
                board["temp_pcb"][1],
                board["temp_pcb"][3],
            ]
        ),
    }


def _issue_s19_xp_plus_hydro_temperature_values(board):
    return {
        "inlet_temp": board["temp_pic"][2],
        "outlet_temp": board["temp_pic"][1],
        "chip_temp": None,
        "temp": _master_avg_nonzero(
            [
                board["temp_pic"][0],
                board["temp_pic"][3],
            ]
        ),
    }


@pytest.mark.parametrize(
    (
        "raw_model",
        "firmware",
        "board",
        "master_temperature_values",
        "expected_inlet_temp",
        "expected_outlet_temp",
    ),
    [
        (
            MinerModel.ANTMINER.S21,
            MinerFirmware.STOCK,
            {
                "temp_pcb": [50, 55, 0, 60],
                "temp_chip": [70, 0, 74],
                "temp_pic": [80, 81, 0, 83],
            },
            _master_standard_temperature_values,
            70,
            74,
        ),
        (
            MinerModel.ANTMINER.S19XPHydro,
            MinerFirmware.STOCK,
            {
                "temp_pcb": [30, 35, 40, 45],
                "temp_chip": [64, 0, 68],
                "temp_pic": [70, 71, 0, 73],
            },
            _master_standard_temperature_values,
            None,
            None,
        ),
        (
            MinerModel.ANTMINER.S21PlusHydro,
            MinerFirmware.STOCK,
            {
                "temp_pcb": [30, 35, 40, 45],
                "temp_chip": [64, 0, 68],
                "temp_pic": [70, 71, 0, 73],
            },
            _master_extended_hydro_temperature_values,
            30,
            40,
        ),
        (
            MinerModel.ANTMINER.S21XPHydro,
            MinerFirmware.STOCK,
            {
                "temp_pcb": [38, 48, 46, 52],
                "temp_chip": [65, 59, 58, 61],
                "temp_pic": [55, 46, 53, 49],
            },
            _master_extended_hydro_temperature_values,
            38,
            46,
        ),
        (
            MinerModel.ANTMINER.S19XPPlusHydro,
            MinerFirmware.STOCK,
            {
                "temp_pcb": [47, 57, 47, 57],
                "temp_chip": [37, 47, 0, 0],
                "temp_pic": [50, 47, 37, 59],
            },
            _issue_s19_xp_plus_hydro_temperature_values,
            37,
            47,
        ),
        (
            MinerModel.ANTMINER.S19XPHydro,
            MinerFirmware.SPIDER_OS,
            {
                "temp_pcb": [30, 35, 40, 45],
                "temp_chip": [64, 0, 68],
                "temp_pic": [70, 71, 0, 73],
            },
            _master_standard_temperature_values,
            None,
            None,
        ),
        (
            MinerModel.ANTMINER.S21PlusHydro,
            MinerFirmware.SPIDER_OS,
            {
                "temp_pcb": [30, 35, 40, 45],
                "temp_chip": [64, 0, 68],
                "temp_pic": [70, 71, 0, 73],
            },
            _master_extended_hydro_temperature_values,
            30,
            40,
        ),
        (
            MinerModel.ANTMINER.S21XPHydro,
            MinerFirmware.SPIDER_OS,
            {
                "temp_pcb": [38, 48, 46, 52],
                "temp_chip": [65, 59, 58, 61],
                "temp_pic": [55, 46, 53, 49],
            },
            _master_extended_hydro_temperature_values,
            38,
            46,
        ),
        (
            MinerModel.ANTMINER.S19XPPlusHydro,
            MinerFirmware.SPIDER_OS,
            {
                "temp_pcb": [47, 57, 47, 57],
                "temp_chip": [37, 47, 0, 0],
                "temp_pic": [50, 47, 37, 59],
            },
            _issue_s19_xp_plus_hydro_temperature_values,
            37,
            47,
        ),
        (
            MinerModel.ANTMINER.S19XPHydro,
            MinerFirmware.HASHMASTER,
            {
                "temp_pcb": [30, 35, 40, 45],
                "temp_chip": [64, 0, 68],
                "temp_pic": [70, 71, 0, 73],
            },
            _master_extended_hydro_temperature_values,
            30,
            40,
        ),
        (
            MinerModel.ANTMINER.S19XPHydro,
            MinerFirmware.BITFUFU_OS,
            {
                "temp_pcb": [30, 35, 40, 45],
                "temp_chip": [64, 0, 68],
                "temp_pic": [70, 71, 0, 73],
            },
            _master_extended_hydro_temperature_values,
            30,
            40,
        ),
    ],
)
def test_apply_antminer_temperature_layout_matches_master_temperature_values(
    raw_model,
    firmware,
    board,
    master_temperature_values,
    expected_inlet_temp,
    expected_outlet_temp,
):
    hashboard = HashBoard()

    apply_antminer_temperature_layout(
        hashboard,
        board,
        get_antminer_temperature_layout(raw_model, firmware),
    )

    expected = master_temperature_values(board)
    assert hashboard.temp == expected["temp"]
    assert hashboard.chip_temp == expected["chip_temp"]
    assert hashboard.inlet_temp == expected_inlet_temp
    assert hashboard.outlet_temp == expected_outlet_temp


@pytest.mark.parametrize(
    ("raw_model", "firmware", "master_temperature_values"),
    [
        (
            MinerModel.ANTMINER.S21,
            MinerFirmware.STOCK,
            _master_standard_temperature_values,
        ),
        (
            MinerModel.ANTMINER.S21PlusHydro,
            MinerFirmware.STOCK,
            _master_extended_hydro_temperature_values,
        ),
    ],
)
def test_apply_antminer_temperature_layout_matches_master_zero_handling(
    raw_model,
    firmware,
    master_temperature_values,
):
    board = {
        "temp_pcb": [0, 0, 0, 0],
        "temp_chip": [0, 0, 0],
        "temp_pic": [0, 0, 0, 0],
    }
    hashboard = HashBoard()

    apply_antminer_temperature_layout(
        hashboard,
        board,
        get_antminer_temperature_layout(raw_model, firmware),
    )

    expected = master_temperature_values(board)
    assert hashboard.temp == expected["temp"]
    assert hashboard.chip_temp == expected["chip_temp"]


def test_apply_antminer_temperature_layout_custom_layout_overrides_default_fields():
    board = {
        "temp_pcb": [30, 40],
        "temp_chip": [60, 70],
        "temp_pic": [80],
    }
    hashboard = HashBoard()

    apply_antminer_temperature_layout(
        hashboard,
        board,
        TemperatureLayout(
            chip_temp=TemperatureReading((TemperatureSource("temp_pic", 0),))
        ),
    )

    assert hashboard.temp == 35
    assert hashboard.chip_temp == 80


def test_antminer_model_classes_do_not_declare_temperature_layout():
    repo_root = Path(__file__).resolve().parents[3]
    model_root = repo_root / "pyasic/miners/device/models/antminer"

    matches = [
        str(path.relative_to(repo_root))
        for path in model_root.rglob("*.py")
        if "temperature_layout" in path.read_text()
    ]

    assert matches == []
