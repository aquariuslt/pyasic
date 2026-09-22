"""Every web backend that takes part in get_data records the commands whose
request never got a usable answer, so the miner can tell a field the device
never answered from one it answered empty. Backends that raise on a failed
request record first and raise after."""

import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest
import requests

from pyasic.errors import APIError, APITransportError
from pyasic.web.auradine import AuradineWebAPI
from pyasic.web.avalonminer import AvalonMinerWebAPI
from pyasic.web.bitfufu import BitfufuAntminerWebAPI, HttpClient
from pyasic.web.braiins_os.bosminer import BOSMinerWebAPI
from pyasic.web.elphapex import ElphapexWebAPI
from pyasic.web.epic import ePICWebAPI
from pyasic.web.espminer import ESPMinerWebAPI
from pyasic.web.goldshell import GoldshellWebAPI
from pyasic.web.hammer import HammerWebAPI
from pyasic.web.hiveon import HiveonWebAPI
from pyasic.web.iceriver import IceRiverWebAPI
from pyasic.web.innosilicon import InnosiliconWebAPI
from pyasic.web.marathon import MaraWebAPI
from pyasic.web.mskminer import MSKMinerWebAPI
from pyasic.web.spideros import SpiderOSWebAPI
from pyasic.web.vnish import VNishWebAPI

IP = "10.10.101.10"
COMMAND = "summary"

# every backend's send_command takes part; the raising ones surface the
# failure as APIError after recording it
ALL_BACKENDS = [
    HiveonWebAPI,
    ElphapexWebAPI,
    HammerWebAPI,
    MaraWebAPI,
    SpiderOSWebAPI,
    VNishWebAPI,
    GoldshellWebAPI,
    InnosiliconWebAPI,
    AuradineWebAPI,
    ePICWebAPI,
    ESPMinerWebAPI,
    AvalonMinerWebAPI,
    IceRiverWebAPI,
    MSKMinerWebAPI,
    BOSMinerWebAPI,
]
# backends that fan a multicommand out over the wire themselves, one request
# per command, instead of going through their own send_command
MULTICOMMAND_BACKENDS = [
    HiveonWebAPI,
    ElphapexWebAPI,
    HammerWebAPI,
    MaraWebAPI,
    SpiderOSWebAPI,
    GoldshellWebAPI,
    InnosiliconWebAPI,
]


def _connect_error() -> httpx.ConnectError:
    return httpx.ConnectError(
        "connection refused", request=httpx.Request("GET", f"http://{IP}/")
    )


class _RaisingAsyncClient:
    """Every request fails to connect."""

    def __init__(self, *args, **kwargs):
        self.cookies = httpx.Cookies()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def _fail(self, *args, **kwargs):
        raise _connect_error()

    get = post = put = patch = _fail


class _StatusAsyncClient(_RaisingAsyncClient):
    """Every request answers with a fixed status and body."""

    status_code = 200
    text = "not json"

    async def _answer(self, *args, **kwargs):
        return self

    get = post = put = patch = _answer

    def json(self):
        return json.loads(self.text)


class _ServerErrorAsyncClient(_StatusAsyncClient):
    status_code = 500
    text = "{}"


class _AnsweringAsyncClient(_StatusAsyncClient):
    text = '{"STATUS": "S"}'


def _api(api_class):
    api = api_class(IP)
    # token backends would otherwise try to authenticate first
    api.token = "token"
    return api


def _send(api):
    """Run send_command, letting a raising backend raise after recording."""
    try:
        asyncio.run(api.send_command(COMMAND))
    except APIError:
        pass


@pytest.mark.parametrize("api_class", ALL_BACKENDS)
def test_send_command_records_a_connection_error_under_the_command(
    monkeypatch, api_class
):
    api = _api(api_class)
    monkeypatch.setattr(httpx, "AsyncClient", _RaisingAsyncClient)

    _send(api)

    assert isinstance(api.transport_errors[COMMAND], httpx.ConnectError)


@pytest.mark.parametrize("api_class", ALL_BACKENDS)
def test_send_command_records_an_error_status(monkeypatch, api_class):
    api = _api(api_class)
    monkeypatch.setattr(httpx, "AsyncClient", _ServerErrorAsyncClient)

    _send(api)

    assert isinstance(api.transport_errors[COMMAND], APITransportError)


@pytest.mark.parametrize("api_class", ALL_BACKENDS)
def test_send_command_records_an_answer_it_cannot_parse(monkeypatch, api_class):
    api = _api(api_class)
    monkeypatch.setattr(httpx, "AsyncClient", _StatusAsyncClient)

    _send(api)

    assert isinstance(api.transport_errors[COMMAND], APITransportError)


@pytest.mark.parametrize("api_class", ALL_BACKENDS)
def test_a_command_that_answers_forgets_its_earlier_failure(monkeypatch, api_class):
    api = _api(api_class)
    monkeypatch.setattr(httpx, "AsyncClient", _RaisingAsyncClient)
    _send(api)

    monkeypatch.setattr(httpx, "AsyncClient", _AnsweringAsyncClient)
    _send(api)

    assert api.transport_errors == {}


@pytest.mark.parametrize("api_class", [IceRiverWebAPI, MSKMinerWebAPI, BOSMinerWebAPI])
def test_a_raising_backend_still_raises_after_recording(monkeypatch, api_class):
    api = _api(api_class)
    monkeypatch.setattr(httpx, "AsyncClient", _RaisingAsyncClient)

    with pytest.raises(APIError):
        asyncio.run(api.send_command(COMMAND))


@pytest.mark.parametrize("api_class", MULTICOMMAND_BACKENDS)
def test_multicommand_records_every_command_that_never_answered(monkeypatch, api_class):
    api = _api(api_class)
    monkeypatch.setattr(httpx, "AsyncClient", _RaisingAsyncClient)

    asyncio.run(api.multicommand("summary", "stats"))

    assert set(api.transport_errors) == {"summary", "stats"}


@pytest.mark.parametrize(
    "api_class", [GoldshellWebAPI, InnosiliconWebAPI, VNishWebAPI, AuradineWebAPI]
)
def test_a_failed_login_is_recorded_under_every_command_it_kept_from_sending(
    monkeypatch, api_class
):
    # the token is missing and the login request itself fails to connect
    api = api_class(IP)
    monkeypatch.setattr(httpx, "AsyncClient", _RaisingAsyncClient)

    asyncio.run(api.multicommand("summary", "stats"))

    assert set(api.transport_errors) == {"summary", "stats"}
    assert all(
        isinstance(error, APITransportError) for error in api.transport_errors.values()
    )


class _OneCommandFailingAsyncClient(_AnsweringAsyncClient):
    """Answers every request except the one whose url names `failed`."""

    async def _answer(self, url="", *args, **kwargs):
        if "failed" in str(url):
            raise _connect_error()
        return self

    get = post = put = patch = _answer


def test_bosminer_batch_keeps_the_commands_that_answered(monkeypatch):
    api = _api(BOSMinerWebAPI)
    monkeypatch.setattr(httpx, "AsyncClient", _OneCommandFailingAsyncClient)

    result = asyncio.run(api.multicommand("healthy", "failed"))

    assert result == {"healthy": {"STATUS": "S"}, "failed": {}}
    assert set(api.transport_errors) == {"failed"}


@pytest.mark.parametrize("api_class", [IceRiverWebAPI, MSKMinerWebAPI])
def test_a_gathered_batch_keeps_the_commands_that_answered(monkeypatch, api_class):
    api = _api(api_class)
    # these backends fan a batch out over their own named methods
    monkeypatch.setattr(
        api, "healthy", AsyncMock(return_value={"ok": 1}), raising=False
    )
    monkeypatch.setattr(
        api, "failed", AsyncMock(side_effect=APIError("refused")), raising=False
    )

    result = asyncio.run(api.multicommand("healthy", "failed"))

    assert result == {"healthy": {"ok": 1}, "failed": {}}


def test_bitfufu_refused_6060_connection_is_recorded_for_serial_number(monkeypatch):
    api = BitfufuAntminerWebAPI(IP)

    async def refuse(self, *args, **kwargs):
        raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(HttpClient, "get", refuse)

    assert asyncio.run(api.get_serial_number()) == {}
    assert isinstance(api.transport_errors["serial_number"], APITransportError)


class _EpicOneCommandRefusedByDeviceAsyncClient(_AnsweringAsyncClient):
    """The device answers `summary` with a failed result and the rest normally."""

    async def _answer(self, url="", *args, **kwargs):
        client = _AnsweringAsyncClient()
        client.text = (
            '{"result": false, "error": "not now"}'
            if "summary" in str(url)
            else '{"result": true, "value": 1}'
        )
        return client

    get = post = put = patch = _answer


def test_epic_batch_keeps_the_commands_the_device_answered(monkeypatch):
    api = _api(ePICWebAPI)
    monkeypatch.setattr(httpx, "AsyncClient", _EpicOneCommandRefusedByDeviceAsyncClient)

    result = asyncio.run(api.multicommand("summary", "network"))

    assert result["network"] == {"result": True, "value": 1}
    assert result["summary"] == {}
    # an answer the device marked as failed is not a transport failure
    assert api.transport_errors == {}
    assert api.request_count == 2
