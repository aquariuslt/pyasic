import asyncio
import ipaddress
import json
from unittest.mock import AsyncMock

import httpx

from pyasic.device.firmware import MinerFirmware
from pyasic.miners.antminer.bmminer.X21.S21 import BMMinerS21XP
from pyasic.miners.antminer.sdminer import SDMinerS21XP
from pyasic.miners.factory import (
    _TYPE_PROBE_STATE,
    MinerFactory,
    MinerIdentifyStatus,
    MinerTypes,
    SDMinerUnknown,
    _TypeProbeState,
)

IP = "10.10.101.10"
SDMINER_VERSION = {
    "STATUS": [{"STATUS": "S", "Code": 22, "Description": "sdminer api 1.0"}],
    "VERSION": [
        {
            "BMMiner": "sdminer",
            "API": "3.7",
            "CompileTime": "Sep 24 2026 02:12:53",
            "Type": "SDMiner",
            "Model": "x86",
        }
    ],
}
STOCK_REALM_RESPONSE = httpx.Response(
    401,
    headers={"www-authenticate": 'Digest realm="antMiner Configuration"'},
    request=httpx.Request("GET", f"http://{IP}/"),
)


def test_s21xp_model_selects_the_sdminer_class():
    miner = MinerFactory._select_miner_from_classes(
        ip=ipaddress.ip_address(IP), miner_model="S21XP", miner_type=MinerTypes.SDMINER
    )

    assert (type(miner), str(miner.raw_model), miner.firmware) == (
        SDMinerS21XP,
        "S21 XP",
        MinerFirmware.SDMINER,
    )


def test_unknown_model_falls_back_to_the_generic_sdminer_class():
    miner = MinerFactory._select_miner_from_classes(
        ip=ipaddress.ip_address(IP), miner_model=None, miner_type=MinerTypes.SDMINER
    )

    assert type(miner) is SDMinerUnknown


def test_socket_version_names_sdminer():
    assert (
        MinerFactory._parse_socket_type(json.dumps(SDMINER_VERSION))
        == MinerTypes.SDMINER
    )


def test_stock_socket_version_stays_antminer():
    stock = json.dumps({"VERSION": [{"BMMiner": "1.0.0", "Type": "Antminer S21 XP"}]})

    assert MinerFactory._parse_socket_type(stock) == MinerTypes.ANTMINER


def _web_factory(monkeypatch, *, is_sdminer):
    factory = MinerFactory()
    monkeypatch.setattr(
        factory, "_web_ping", AsyncMock(return_value=("", STOCK_REALM_RESPONSE))
    )
    # the stock cgi and the marathon endpoint both refuse
    monkeypatch.setattr(factory, "send_web_command", AsyncMock(return_value=None))
    monkeypatch.setattr(factory, "_is_sdminer", AsyncMock(return_value=is_sdminer))
    return factory


def test_stock_realm_with_refused_cgi_and_sdminer_rpc_is_sdminer(monkeypatch):
    factory = _web_factory(monkeypatch, is_sdminer=True)

    assert asyncio.run(factory._get_miner_web(IP)) == MinerTypes.SDMINER


def test_stock_realm_with_refused_cgi_and_stock_rpc_stays_antminer(monkeypatch):
    factory = _web_factory(monkeypatch, is_sdminer=False)

    assert asyncio.run(factory._get_miner_web(IP)) == MinerTypes.ANTMINER


def test_is_sdminer_reads_the_rpc_type(monkeypatch):
    factory = MinerFactory()
    monkeypatch.setattr(
        factory, "send_api_command", AsyncMock(return_value=SDMINER_VERSION)
    )

    assert asyncio.run(factory._is_sdminer(IP)) is True


def test_is_sdminer_is_false_without_an_rpc_answer(monkeypatch):
    factory = MinerFactory()
    monkeypatch.setattr(factory, "send_api_command", AsyncMock(return_value=None))

    assert asyncio.run(factory._is_sdminer(IP)) is False


def test_model_comes_from_the_system_endpoint(monkeypatch):
    factory = MinerFactory()
    monkeypatch.setattr(
        factory,
        "send_web_command",
        AsyncMock(return_value={"miner": {"model": "S21XP", "serial": ""}}),
    )

    assert asyncio.run(factory.get_miner_model_sdminer(IP)) == "S21XP"


def test_model_falls_back_to_the_image_info(monkeypatch):
    factory = MinerFactory()
    monkeypatch.setattr(
        factory,
        "send_web_command",
        AsyncMock(side_effect=[None, {"miner_type": "S21XP", "product": "GridFw"}]),
    )

    assert asyncio.run(factory.get_miner_model_sdminer(IP)) == "S21XP"


def test_identify_reports_an_identified_sdminer(monkeypatch):
    factory = MinerFactory()
    monkeypatch.setattr(
        factory, "_get_miner_type", AsyncMock(return_value=MinerTypes.SDMINER)
    )
    monkeypatch.setattr(
        factory, "get_miner_model_sdminer", AsyncMock(return_value="S21XP")
    )

    result = asyncio.run(factory.identify_miner(IP))

    assert (result.status, type(result.miner)) == (
        MinerIdentifyStatus.IDENTIFIED,
        SDMinerS21XP,
    )


async def _answer_never(*args, **kwargs):
    await asyncio.Event().wait()


def _stock_realm_factory(monkeypatch, *, rpc_version):
    # stock realm, the stock cgi refused, no socket answer: the web branch is
    # the only way to a type
    factory = MinerFactory()
    monkeypatch.setattr(
        factory, "_web_ping", AsyncMock(return_value=("", STOCK_REALM_RESPONSE))
    )
    monkeypatch.setattr(factory, "send_web_command", AsyncMock(return_value=None))
    monkeypatch.setattr(factory, "_get_miner_socket", AsyncMock(return_value=None))
    monkeypatch.setattr(factory, "send_api_command", rpc_version)
    return factory


def test_rpc_that_never_answers_keeps_the_antminer_type(monkeypatch):
    factory = _stock_realm_factory(monkeypatch, rpc_version=_answer_never)
    monkeypatch.setattr(
        factory, "get_miner_model_antminer", AsyncMock(return_value="Antminer S21 XP")
    )

    result = asyncio.run(factory.identify_miner(IP, timeout=0.2))

    assert (result.status, type(result.miner)) == (
        MinerIdentifyStatus.IDENTIFIED,
        BMMinerS21XP,
    )


def test_rpc_that_fails_to_decode_keeps_the_antminer_type(monkeypatch):
    async def answer_undecodable(ip, command):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    factory = _stock_realm_factory(monkeypatch, rpc_version=answer_undecodable)
    monkeypatch.setattr(
        factory, "get_miner_model_antminer", AsyncMock(return_value="Antminer S21 XP")
    )

    result = asyncio.run(factory.identify_miner(IP, timeout=0.2))

    assert (result.status, type(result.miner)) == (
        MinerIdentifyStatus.IDENTIFIED,
        BMMinerS21XP,
    )


def test_slow_sdminer_answer_inside_the_budget_is_still_detected(monkeypatch):
    async def answer_late(ip, command):
        await asyncio.sleep(0.1)
        return SDMINER_VERSION

    factory = _stock_realm_factory(monkeypatch, rpc_version=answer_late)
    monkeypatch.setattr(
        factory, "get_miner_model_sdminer", AsyncMock(return_value="S21XP")
    )

    result = asyncio.run(factory.identify_miner(IP, timeout=1))

    assert type(result.miner) is SDMinerS21XP


def test_answering_stock_cgi_records_no_fallback(monkeypatch):
    factory = MinerFactory()
    monkeypatch.setattr(
        factory, "_web_ping", AsyncMock(return_value=("", STOCK_REALM_RESPONSE))
    )
    monkeypatch.setattr(
        factory,
        "send_web_command",
        AsyncMock(side_effect=[None, {"minertype": "Antminer S21 XP"}]),
    )
    probe_state = _TypeProbeState()

    async def probe_web():
        _TYPE_PROBE_STATE.set(probe_state)
        await factory._get_miner_web(IP)

    asyncio.run(probe_web())

    assert probe_state.fallback is None
