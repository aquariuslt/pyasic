import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx

from pyasic import settings
from pyasic.web.antminer import AntminerModernWebAPI
from pyasic.web.spideros import SpiderOSWebAPI


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


def test_spideros_webapi_is_independent_class():
    assert SpiderOSWebAPI is not AntminerModernWebAPI
    assert AntminerModernWebAPI not in SpiderOSWebAPI.__mro__[1:]


def test_spideros_http_get_returns_failure_on_connection_error(monkeypatch):
    api = SpiderOSWebAPI("10.10.101.10")

    monkeypatch.setattr(httpx, "AsyncClient", _RaisingAsyncClient)

    response = asyncio.run(api._invoke_http_get("get_sn", 6060))

    assert response["success"] is False
    assert "Connection error occurred" in response["message"]


def test_spideros_serial_number_returns_empty_data_on_connection_error(monkeypatch):
    api = SpiderOSWebAPI("10.10.101.10")

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


def test_spideros_multicommand_uses_configured_port():
    api = SpiderOSWebAPI("10.10.101.10")
    api.port = 8080

    class _CapturingClient:
        async def get(self, url, auth=None, timeout=None):
            return SimpleNamespace(
                status_code=200,
                json=lambda: {"ok": True, "url": url, "timeout": timeout},
            )

    result = asyncio.run(api._handle_multicommand(_CapturingClient(), "summary"))

    assert result == {
        "summary": {
            "ok": True,
            "url": "http://10.10.101.10:8080/cgi-bin/summary.cgi",
            "timeout": settings.get("api_function_timeout", 3),
        }
    }
