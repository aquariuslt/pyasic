import asyncio
from unittest.mock import AsyncMock

from pyasic.miners.antminer.bmminer.X19.S19 import BMMinerS19XPHydro
from pyasic.miners.factory import MinerFactory, MinerIdentifyStatus, MinerTypes

IP = "10.10.101.10"
BOARD_CODE = "Antminer HHB56XXX"
WEB_MODEL = "Antminer S19 XP Hyd."


def _answer_later(value, delay=0.05):
    async def probe(ip):
        await asyncio.sleep(delay)
        return value

    return probe


def _factory(monkeypatch, *, web_probe, sock_probe):
    factory = MinerFactory()
    monkeypatch.setattr(factory, "_get_model_antminer_web", web_probe)
    monkeypatch.setattr(factory, "_get_model_antminer_sock", sock_probe)
    return factory


def test_web_model_wins_over_an_rpc_answer_that_names_no_supported_model(
    monkeypatch,
):
    factory = _factory(
        monkeypatch,
        web_probe=_answer_later(WEB_MODEL),
        sock_probe=AsyncMock(return_value=BOARD_CODE),
    )

    model = asyncio.run(factory.get_miner_model_antminer(IP))

    assert model == WEB_MODEL


def test_a_supported_rpc_answer_wins_without_waiting_for_the_web(monkeypatch):
    factory = _factory(
        monkeypatch,
        web_probe=_answer_later(WEB_MODEL, delay=30),
        sock_probe=AsyncMock(return_value="Antminer S19 XP"),
    )

    model = asyncio.run(
        asyncio.wait_for(factory.get_miner_model_antminer(IP), timeout=1)
    )

    assert model == "Antminer S19 XP"


def test_a_hiveon_web_model_is_not_lost_to_a_plain_rpc_model(monkeypatch):
    # hiveon miners answer the web like stock antminers and carry the word in
    # the model, which is what moves them to the hiveon class table
    factory = _factory(
        monkeypatch,
        web_probe=AsyncMock(return_value="Antminer S19 Hiveon"),
        sock_probe=_answer_later("Antminer S19"),
    )

    model = asyncio.run(factory.get_miner_model_antminer(IP))

    assert model == "Antminer S19 Hiveon"


def test_the_first_answer_is_kept_when_neither_names_a_supported_model(monkeypatch):
    factory = _factory(
        monkeypatch,
        web_probe=_answer_later("Antminer Z99"),
        sock_probe=AsyncMock(return_value=BOARD_CODE),
    )

    model = asyncio.run(factory.get_miner_model_antminer(IP))

    assert model == BOARD_CODE


def test_an_unsupported_rpc_answer_is_kept_when_the_web_answers_nothing(monkeypatch):
    factory = _factory(
        monkeypatch,
        web_probe=_answer_later(None),
        sock_probe=AsyncMock(return_value=BOARD_CODE),
    )

    model = asyncio.run(factory.get_miner_model_antminer(IP))

    assert model == BOARD_CODE


def test_no_answer_from_either_probe_is_none(monkeypatch):
    factory = _factory(
        monkeypatch,
        web_probe=AsyncMock(return_value=None),
        sock_probe=AsyncMock(return_value=None),
    )

    assert asyncio.run(factory.get_miner_model_antminer(IP)) is None


def test_identify_resolves_the_web_model_when_rpc_reports_a_board_code(monkeypatch):
    factory = _factory(
        monkeypatch,
        web_probe=_answer_later(WEB_MODEL),
        sock_probe=AsyncMock(return_value=BOARD_CODE),
    )
    monkeypatch.setattr(
        factory, "_get_miner_type", AsyncMock(return_value=MinerTypes.ANTMINER)
    )

    result = asyncio.run(factory.identify_miner(IP))

    assert result.status is MinerIdentifyStatus.IDENTIFIED
    assert isinstance(result.miner, BMMinerS19XPHydro)
