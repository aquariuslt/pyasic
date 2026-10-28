import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from pyasic.errors import APIError
from pyasic.miners.antminer.bmminer.X21.S21 import BMMinerS21Plus, BMMinerS21XP
from pyasic.miners.antminer.nonce import NonceS21Plus, NonceS21XP
from pyasic.miners.factory import MinerFactory, MinerIdentifyStatus, MinerTypes

FIXTURES = Path(__file__).parent / "fixtures" / "contract"


def load(sample, command):
    return json.loads((FIXTURES / sample / f"{command}.json").read_text())


def nonce_responses(sample):
    responses = {
        "version": [load(sample, "version")],
        "stats": [load(sample, "stats-new-api")],
        "summary": [load(sample, "summary-new-api")],
        "legacy_stats": [load(sample, "stats")],
        "multicommand": True,
    }
    if (FIXTURES / sample / "pools.json").exists():
        responses["pools"] = [load(sample, "pools")]
    return responses


def read_nonce(miner_class, sample):
    responses = nonce_responses(sample)
    miner = miner_class("192.0.2.1")
    miner.rpc.multicommand = AsyncMock(return_value=responses)
    for command in ("version", "stats", "summary", "legacy_stats", "pools"):
        value = responses.get(command, [None])[0]
        setattr(miner.rpc, command, AsyncMock(return_value=value))
    return asyncio.run(miner.get_data_with_errors())


def read_stock(miner_class, sample, new_stats=None):
    """Replay the legacy RPC commands; the web interface is unavailable."""
    commands = ("version", "stats", "summary", "pools")
    responses = {
        c: load(sample, c)
        for c in commands
        if (FIXTURES / sample / f"{c}.json").exists()
    }
    miner = miner_class("192.0.2.1")

    async def stats(new_api=False):
        if new_api:
            if new_stats is None:
                raise APIError("new_api stats not recorded")
            return new_stats
        return responses["stats"]

    async def no_web(*args, **kwargs):
        raise APIError("web interface not replayed")

    miner.rpc.stats = stats
    for command in ("version", "summary", "pools"):
        setattr(miner.rpc, command, AsyncMock(return_value=responses.get(command)))
    miner.rpc.multicommand = AsyncMock(
        return_value={**{c: [v] for c, v in responses.items()}, "multicommand": True}
    )
    miner.web.send_command = no_web
    return asyncio.run(miner.get_data_with_errors())


def identify(sample):
    factory = MinerFactory()
    version = load(sample, "version")
    miner_type = MinerFactory._parse_socket_type(json.dumps(version))
    factory._get_miner_type = AsyncMock(return_value=miner_type)
    factory.send_api_command = AsyncMock(return_value=version)
    return miner_type, asyncio.run(factory.identify_miner("192.0.2.1"))


def ths(rate):
    return round(float(rate), 3) if rate is not None else None


def test_stock_s21xp_official_adapter_core_fields():
    miner_type, identified = identify("stock-s21xp")
    assert miner_type is MinerTypes.ANTMINER
    assert isinstance(identified.miner, BMMinerS21XP)
    result = read_stock(BMMinerS21XP, "stock-s21xp")
    data = result.data
    assert result.field_parse_errors == {}
    assert data.model == "S21 XP" and data.firmware == "Stock"
    assert ths(data.hashrate) == 286.573
    assert ths(data.expected_hashrate) == 301.0
    assert [fan.speed for fan in data.fans] == [3480, 3510, 3570, 3510]
    assert data.uptime == 744285
    pools = data.pools
    assert [pool.accepted for pool in pools] == [47361, 0, 2]
    assert pools[0].difficulty_accepted == 49868161024.0
    assert pools[0].last_share_ts > 0 and pools[1].last_share_ts == 0


@pytest.mark.parametrize(
    ("sample", "miner_class", "model", "chips"),
    [
        ("nonce-s21plus", NonceS21Plus, "Antminer S21+", 55),
        ("nonce-s21xp-synthetic", NonceS21XP, "Antminer S21 XP", 91),
    ],
)
def test_nonce_samples_identify_as_nonce_models(sample, miner_class, model, chips):
    miner_type, identified = identify(sample)
    assert miner_type is MinerTypes.NONCE
    assert identified.status is MinerIdentifyStatus.IDENTIFIED
    assert type(identified.miner) is miner_class
    assert identified.miner.expected_chips == chips
    assert load(sample, "stats-new-api")["INFO"]["type"] == model


def test_recorded_nonce_s21plus_core_fields():
    result = read_nonce(NonceS21Plus, "nonce-s21plus")
    data = result.data
    assert result.field_parse_errors == {}
    assert data.firmware == "Nonce" and data.fw_ver == "4.13.8+g4cc16133ef77.dirty"
    assert data.model == "S21+"
    assert data.serial_number == "FIXTUREMINER00001"
    assert data.mac == "02:00:00:00:00:01"
    assert ths(data.hashrate) == 208.277
    assert data.wattage == 3534
    assert [fan.speed for fan in data.fans] == [6450, 6480, 6180, 6150]
    assert data.uptime == 1197 and data.is_mining is True
    boards = data.hashboards
    assert [board.chips for board in boards] == [55, 55, 55]
    assert [board.hashrate for board in boards] == [None, None, None]
    assert [(board.inlet_temp, board.outlet_temp) for board in boards] == [
        (31.0, 44.8125),
        (30.625, 42.3125),
        (30.375, 43.125),
    ]
    assert [board.serial_number for board in boards] == [
        f"FIXTUREBOARD0000{index}" for index in range(3)
    ]
    pool = data.pools[0]
    assert (pool.accepted, pool.rejected) == (62, 0)
    assert pool.last_share_ts == 1793200258
    assert pool.difficulty_accepted == 47710208.0


def test_synthetic_nonce_s21xp_core_fields():
    result = read_nonce(NonceS21XP, "nonce-s21xp-synthetic")
    data = result.data
    assert result.field_parse_errors == {}
    assert data.firmware == "Nonce" and data.model == "S21 XP"
    assert data.mac == "02:11:22:33:44:66"
    assert data.wattage == 3650
    assert ths(data.hashrate) == 200.0
    assert [fan.speed for fan in data.fans] == [6000, 6010, 6020, 6030]
    chains = load("nonce-s21xp-synthetic", "stats-new-api")["STATS"][0]["chain"]
    boards = data.hashboards
    assert [board.chips for board in boards] == [91, 91, 91]
    assert [board.expected_chips for board in boards] == [91, 91, 91]
    assert [round(float(board.hashrate) * 1000, 6) for board in boards] == [
        round(chain["rate_real"], 6) for chain in chains
    ]
    assert [(board.inlet_temp, board.outlet_temp) for board in boards] == [
        (30.0, 45.0),
        (31.0, 46.0),
        (32.0, 47.0),
    ]


@pytest.mark.parametrize(
    ("sample", "miner_class", "chips"),
    [
        ("nonce-s21plus", BMMinerS21Plus, 55),
        ("nonce-s21xp-synthetic", BMMinerS21XP, 91),
    ],
)
def test_official_adapter_reads_nonce_compatibility_fields(sample, miner_class, chips):
    result = read_stock(miner_class, sample, new_stats=load(sample, "stats-new-api"))
    data = result.data
    nonce = read_nonce(NonceS21XP if chips == 91 else NonceS21Plus, sample).data
    assert result.field_parse_errors == {}
    assert ths(data.hashrate) == ths(nonce.hashrate)
    assert [fan.speed for fan in data.fans] == [fan.speed for fan in nonce.fans]
    assert [board.chips for board in data.hashboards] == [chips] * 3
    assert [board.hashrate for board in data.hashboards] == [
        board.hashrate for board in nonce.hashboards
    ]
    assert data.uptime is not None
    if sample == "nonce-s21plus":
        assert data.expected_hashrate is None
        assert data.pools[0].last_share_ts == 1793200258
        assert data.pools[0].difficulty_accepted == 47710208.0
