import asyncio
from unittest.mock import AsyncMock

import pytest

from pyasic.miners.backends.unknown import UnknownMiner
from pyasic.miners.factory import (
    MinerFactory,
    MinerIdentifyStatus,
    MinerTypes,
    identify_miner,
)

IP = "10.10.101.10"


def _factory(monkeypatch, type_probe, model_probe=None):
    factory = MinerFactory()
    monkeypatch.setattr(factory, "_get_miner_type", type_probe)
    if model_probe is not None:
        monkeypatch.setattr(factory, "get_miner_model_antminer", model_probe)
    return factory


async def _hang(ip):
    await asyncio.sleep(30)


def test_found_when_type_and_model_both_resolve(monkeypatch):
    factory = _factory(
        monkeypatch,
        AsyncMock(return_value=MinerTypes.ANTMINER),
        AsyncMock(return_value="ANTMINER S19"),
    )

    result = asyncio.run(factory.identify_miner(IP))

    assert result.status is MinerIdentifyStatus.IDENTIFIED
    assert result.miner is not None and result.miner.raw_model == "S19"
    assert result.errors == {}


def test_model_unresolved_keeps_the_generic_class_when_the_model_probe_times_out(
    monkeypatch,
):
    monkeypatch.setattr("pyasic.settings._settings", {"factory_get_timeout": 0.05})
    factory = _factory(monkeypatch, AsyncMock(return_value=MinerTypes.ANTMINER), _hang)

    result = asyncio.run(factory.identify_miner(IP))

    assert result.status is MinerIdentifyStatus.MODEL_UNRESOLVED
    assert result.miner is not None and result.miner.raw_model is None
    assert result.errors == {}


def test_timeout_when_every_type_probe_attempt_gets_no_answer(monkeypatch):
    monkeypatch.setattr("pyasic.settings._settings", {"factory_get_timeout": 0.05})
    factory = _factory(monkeypatch, _hang)

    result = asyncio.run(factory.identify_miner(IP))

    assert result.status is MinerIdentifyStatus.TIMEOUT
    assert result.miner is None


def test_unrecognized_when_the_device_answers_but_no_type_matches(monkeypatch):
    factory = _factory(monkeypatch, AsyncMock(return_value=None))

    result = asyncio.run(factory.identify_miner(IP))

    assert result.status is MinerIdentifyStatus.UNRECOGNIZED
    assert result.miner is None


def test_unrecognized_when_the_type_has_no_implementation(monkeypatch):
    monkeypatch.setattr(
        MinerFactory,
        "_select_miner_from_classes",
        staticmethod(lambda ip, miner_model, miner_type: UnknownMiner(ip)),
    )
    factory = _factory(
        monkeypatch,
        AsyncMock(return_value=MinerTypes.ANTMINER),
        AsyncMock(return_value="NOT A REAL MODEL"),
    )

    result = asyncio.run(factory.identify_miner(IP))

    assert result.status is MinerIdentifyStatus.UNRECOGNIZED
    assert isinstance(result.miner, UnknownMiner)


def test_probe_errors_are_collected_and_identification_continues(monkeypatch):
    factory = _factory(
        monkeypatch,
        AsyncMock(return_value=MinerTypes.ANTMINER),
        AsyncMock(side_effect=RuntimeError("model probe exploded")),
    )

    result = asyncio.run(factory.identify_miner(IP))

    assert result.status is MinerIdentifyStatus.MODEL_UNRESOLVED
    assert isinstance(result.errors["model"], RuntimeError)


def test_get_miner_keeps_raising_a_probe_error(monkeypatch):
    factory = _factory(
        monkeypatch, AsyncMock(side_effect=ValueError("type probe exploded"))
    )

    with pytest.raises(ValueError, match="type probe exploded"):
        asyncio.run(factory.get_miner(IP))


def test_get_miner_returns_the_same_miner_or_none(monkeypatch):
    factory = _factory(monkeypatch, AsyncMock(return_value=None))
    assert asyncio.run(factory.get_miner(IP)) is None

    factory = _factory(
        monkeypatch,
        AsyncMock(return_value=MinerTypes.ANTMINER),
        AsyncMock(return_value="ANTMINER S19"),
    )
    assert asyncio.run(factory.get_miner(IP)).raw_model == "S19"


def test_module_level_wrapper_returns_the_result(monkeypatch):
    monkeypatch.setattr(
        "pyasic.miners.factory.miner_factory._get_miner_type",
        AsyncMock(return_value=None),
    )

    result = asyncio.run(identify_miner(IP))

    assert result.status is MinerIdentifyStatus.UNRECOGNIZED


def test_explicit_timeout_and_retries_override_the_settings(monkeypatch):
    monkeypatch.setattr(
        "pyasic.settings._settings",
        {"factory_get_timeout": 30, "factory_get_retries": 1},
    )
    attempts = []

    async def slow_type_probe(ip):
        attempts.append(ip)
        await asyncio.sleep(30)

    factory = _factory(monkeypatch, slow_type_probe)

    result = asyncio.run(factory.identify_miner(IP, timeout=0.05, retries=3))

    assert result.status is MinerIdentifyStatus.TIMEOUT
    assert len(attempts) == 3
