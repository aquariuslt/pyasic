import asyncio

from pyasic.miners.antminer.luxos.X21 import LUXMinerS21PlusHydro


def test_luxminer_hashboards_ignore_nan_temperatures():
    miner = LUXMinerS21PlusHydro("10.2.0.1")
    rpc_stats = {
        "STATS": [
            {},
            {
                "chain_rate1": "132000",
                "chain_rate2": "133000",
                "chain_rate3": "134000",
                "chain_acn1": "95",
                "chain_acn2": "95",
                "chain_acn3": "95",
                "temp_chip1": "NaN-NaN-NaN-NaN",
                "temp_chip2": "58.25-59-60-61.75",
                "temp_chip3": "62-63-64-65",
                "temp_pcb1": "NaN-NaN-NaN-NaN",
                "temp_pcb2": "42-43.25-44.75-45",
                "temp_pcb3": "46-47-48-49",
            },
        ]
    }

    hashboards = asyncio.run(
        miner._get_hashboards(rpc_stats=rpc_stats, rpc_devdetails={})
    )

    assert len(hashboards) == 3
    assert hashboards[0].missing is False
    assert hashboards[0].chips == 95
    assert hashboards[0].temp is None
    assert hashboards[0].chip_temp is None
    assert hashboards[1].temp == 44.0
    assert hashboards[1].chip_temp == 60.0


def test_luxminer_reads_serial_number_from_config():
    miner = LUXMinerS21PlusHydro("10.2.0.1")
    rpc_config = {"CONFIG": [{"SerialNumber": "YNAHG5UBEJDJG02ER"}]}

    serial_number = asyncio.run(miner._get_serial_number(rpc_config=rpc_config))

    assert serial_number == "YNAHG5UBEJDJG02ER"


def test_luxminer_serial_number_handles_missing_config_fields():
    miner = LUXMinerS21PlusHydro("10.2.0.1")

    assert asyncio.run(miner._get_serial_number(rpc_config={"CONFIG": [{}]})) is None
    assert asyncio.run(miner._get_serial_number(rpc_config={"CONFIG": []})) is None


def test_luxminer_hashboards_read_serial_numbers_from_devdetails():
    miner = LUXMinerS21PlusHydro("10.2.0.1")
    rpc_stats = {
        "STATS": [
            {},
            {
                "chain_rate1": "132000",
                "chain_rate2": "133000",
                "chain_rate3": "134000",
                "chain_acn1": "95",
                "chain_acn2": "95",
                "chain_acn3": "95",
                "temp_chip1": "58-59-60-61",
                "temp_chip2": "58-59-60-61",
                "temp_chip3": "58-59-60-61",
                "temp_pcb1": "42-43-44-45",
                "temp_pcb2": "42-43-44-45",
                "temp_pcb3": "42-43-44-45",
            },
        ]
    }
    rpc_devdetails = {
        "DEVDETAILS": [
            {"ID": 1, "Name": "Hash Chain 6", "SerialNumber": "YNAHYT1BEJECJ058T"},
            {"ID": 2, "Name": "Hash Chain 7", "SerialNumber": "YNAHYT1BEJECJ03A2"},
            {"ID": 0, "Name": "Hash Chain 5", "SerialNumber": "YNAHYT1BEJECJ02K3"},
        ]
    }

    hashboards = asyncio.run(
        miner._get_hashboards(rpc_stats=rpc_stats, rpc_devdetails=rpc_devdetails)
    )

    assert [hashboard.serial_number for hashboard in hashboards] == [
        "YNAHYT1BEJECJ02K3",
        "YNAHYT1BEJECJ058T",
        "YNAHYT1BEJECJ03A2",
    ]


def test_luxminer_hashboards_ignore_invalid_devdetails_entries():
    miner = LUXMinerS21PlusHydro("10.2.0.1")
    rpc_stats = {
        "STATS": [
            {},
            {
                "chain_rate1": "132000",
                "chain_rate2": "133000",
                "chain_rate3": "134000",
                "chain_acn1": "95",
                "chain_acn2": "95",
                "chain_acn3": "95",
                "temp_chip1": "58-59-60-61",
                "temp_chip2": "58-59-60-61",
                "temp_chip3": "58-59-60-61",
                "temp_pcb1": "42-43-44-45",
                "temp_pcb2": "42-43-44-45",
                "temp_pcb3": "42-43-44-45",
            },
        ]
    }
    rpc_devdetails = {
        "DEVDETAILS": [
            {"DEVDETAILS": 1, "Name": "Hash Chain", "SerialNumber": "fallback-slot"},
            {"Name": 1, "SerialNumber": "bad-type"},
            {"ID": -1, "Name": "Hash Chain -1", "SerialNumber": "negative-slot"},
            {"ID": 3, "Name": "Hash Chain 1", "SerialNumber": "out-of-range"},
            {"ID": 2, "Name": "Hash Chain 8", "SerialNumber": "YNAHYT1BEJECJ03A2"},
        ]
    }

    hashboards = asyncio.run(
        miner._get_hashboards(rpc_stats=rpc_stats, rpc_devdetails=rpc_devdetails)
    )
    missing_devdetails_hashboards = asyncio.run(
        miner._get_hashboards(rpc_stats=rpc_stats, rpc_devdetails={})
    )

    assert [hashboard.serial_number for hashboard in hashboards] == [
        None,
        "fallback-slot",
        "YNAHYT1BEJECJ03A2",
    ]
    assert all(
        hashboard.serial_number is None for hashboard in missing_devdetails_hashboards
    )
