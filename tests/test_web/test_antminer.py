import asyncio
from unittest.mock import AsyncMock

import httpx

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
