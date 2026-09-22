import asyncio
import json
from unittest.mock import AsyncMock

import httpx

from pyasic.errors import APITransportError
from pyasic.web.antminer import AntminerModernWebAPI


class _RaisingAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, *args, **kwargs):
        raise httpx.ConnectError(
            "connection refused",
            request=httpx.Request("GET", "http://10.10.101.10:6060/get_sn"),
        )


def test_antminer_http_get_returns_failure_on_connection_error(monkeypatch):
    api = AntminerModernWebAPI("10.10.101.10")

    monkeypatch.setattr(httpx, "AsyncClient", _RaisingAsyncClient)

    response = asyncio.run(api._invoke_http_get("get_sn", 6060))

    assert response["success"] is False
    assert "Connection error occurred" in response["message"]


def test_antminer_serial_number_returns_empty_data_on_connection_error(monkeypatch):
    api = AntminerModernWebAPI("10.10.101.10")

    monkeypatch.setattr(
        api,
        "_invoke_http_get",
        AsyncMock(
            return_value={
                "success": False,
                "message": "Connection error occurred",
            }
        ),
    )

    result = asyncio.run(api.get_serial_number())

    assert result == {}


class _StatusAsyncClient(_RaisingAsyncClient):
    """Answers every request with a fixed status and body."""

    status_code = 200
    text = "not json"

    async def get(self, *args, **kwargs):
        return self

    def json(self):
        return json.loads(self.text)


class _ServerErrorAsyncClient(_StatusAsyncClient):
    status_code = 500


class _ParsingAsyncClient(_StatusAsyncClient):
    text = '{"STATUS": "S"}'


def test_antminer_send_command_records_connection_error_under_the_command(
    monkeypatch,
):
    api = AntminerModernWebAPI("10.10.101.10")
    monkeypatch.setattr(httpx, "AsyncClient", _RaisingAsyncClient)

    asyncio.run(api.send_command("get_system_info"))

    assert isinstance(api.transport_errors["get_system_info"], httpx.ConnectError)


def test_antminer_multicommand_records_every_command_that_never_answered(
    monkeypatch,
):
    api = AntminerModernWebAPI("10.10.101.10")
    monkeypatch.setattr(httpx, "AsyncClient", _RaisingAsyncClient)

    result = asyncio.run(api.multicommand("get_system_info", "get_network_info"))

    assert result == {
        "get_system_info": {},
        "get_network_info": {},
        "multicommand": True,
    }
    assert set(api.transport_errors) == {"get_system_info", "get_network_info"}


def test_antminer_serial_number_endpoint_answering_records_nothing(monkeypatch):
    api = AntminerModernWebAPI("10.10.101.10")
    monkeypatch.setattr(
        api,
        "_invoke_http_get",
        AsyncMock(return_value={"success": True, "data": "BBJ1234"}),
    )

    assert asyncio.run(api.get_serial_number()) == {"serinum": "BBJ1234"}
    assert api.transport_errors == {}


def test_antminer_error_status_is_recorded_as_a_transport_error(monkeypatch):
    api = AntminerModernWebAPI("10.10.101.10")
    monkeypatch.setattr(httpx, "AsyncClient", _ServerErrorAsyncClient)

    asyncio.run(api.multicommand("get_system_info"))

    assert isinstance(api.transport_errors["get_system_info"], APITransportError)


def test_antminer_multicommand_records_an_answer_it_cannot_parse(monkeypatch):
    api = AntminerModernWebAPI("10.10.101.10")
    monkeypatch.setattr(httpx, "AsyncClient", _StatusAsyncClient)

    asyncio.run(api.multicommand("get_system_info"))

    assert isinstance(api.transport_errors["get_system_info"], APITransportError)


def test_antminer_multicommand_still_answers_empty_when_it_cannot_parse(monkeypatch):
    api = AntminerModernWebAPI("10.10.101.10")
    monkeypatch.setattr(httpx, "AsyncClient", _StatusAsyncClient)

    result = asyncio.run(api.multicommand("get_system_info"))

    assert result == {"get_system_info": {}, "multicommand": True}


def test_antminer_send_command_records_an_answer_it_cannot_parse(monkeypatch):
    api = AntminerModernWebAPI("10.10.101.10")
    monkeypatch.setattr(httpx, "AsyncClient", _StatusAsyncClient)

    asyncio.run(api.send_command("get_system_info"))

    assert isinstance(api.transport_errors["get_system_info"], APITransportError)


def test_antminer_send_command_forgets_a_failure_once_the_command_answers(
    monkeypatch,
):
    api = AntminerModernWebAPI("10.10.101.10")
    monkeypatch.setattr(httpx, "AsyncClient", _RaisingAsyncClient)
    asyncio.run(api.send_command("get_system_info"))

    monkeypatch.setattr(httpx, "AsyncClient", _ParsingAsyncClient)
    asyncio.run(api.send_command("get_system_info"))

    assert api.transport_errors == {}
