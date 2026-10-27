import asyncio
import json
from unittest.mock import AsyncMock

import httpx

from pyasic import settings
from pyasic.errors import APITransportError
from pyasic.web import antminer
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


class _RecordingAsyncClient(_StatusAsyncClient):
    """Answers a log backup request and keeps the timeout it was given."""

    text = '{"stats": "success", "msg": "log_backup.tar"}'
    timeouts = []

    async def post(self, *args, **kwargs):
        self.timeouts.append(kwargs.get("timeout"))
        return self


def test_antminer_log_backup_waits_for_the_miner_to_pack_its_logs(monkeypatch):
    api = AntminerModernWebAPI("10.10.101.10")
    monkeypatch.setattr(httpx, "AsyncClient", _RecordingAsyncClient)
    monkeypatch.setattr(_RecordingAsyncClient, "timeouts", [])

    result = asyncio.run(api._create_log_backup(["log.1", "log.2"]))

    assert result["success"] is True and result["msg"] == "log_backup.tar"
    assert _RecordingAsyncClient.timeouts == [antminer.LOG_BACKUP_TIMEOUT_SECONDS]
    assert antminer.LOG_BACKUP_TIMEOUT_SECONDS > settings.get("api_function_timeout")


class _SlowBackupAsyncClient(_RaisingAsyncClient):
    async def post(self, *args, **kwargs):
        raise httpx.ReadTimeout(
            "",
            request=httpx.Request(
                "POST", "http://10.10.101.10/cgi-bin/create_log_backup.cgi"
            ),
        )


def test_antminer_log_backup_timeout_is_reported_not_raised(monkeypatch):
    api = AntminerModernWebAPI("10.10.101.10")
    monkeypatch.setattr(httpx, "AsyncClient", _SlowBackupAsyncClient)

    result = asyncio.run(api._create_log_backup(["log.1"]))

    assert result["success"] is False and "ReadTimeout" in result["message"]


class _RecordingCurrentLogClient(_RecordingAsyncClient):
    text = "2026-10-22 01:25:42 set_voltage_by_steps to 1452."


def test_antminer_current_log_waits_beyond_the_per_command_timeout(monkeypatch):
    api = AntminerModernWebAPI("10.10.101.10")
    monkeypatch.setattr(httpx, "AsyncClient", _RecordingCurrentLogClient)
    monkeypatch.setattr(_RecordingCurrentLogClient, "timeouts", [])

    result = asyncio.run(api._download_current_logs())

    assert result["success"] is True
    assert _RecordingCurrentLogClient.timeouts == [antminer.CURRENT_LOG_TIMEOUT_SECONDS]
    assert antminer.CURRENT_LOG_TIMEOUT_SECONDS > settings.get("api_function_timeout")


def test_antminer_firmware_upload_waits_for_the_flash_to_finish(monkeypatch, tmp_path):
    firmware = tmp_path / "firmware.bmu"
    firmware.write_bytes(b"image")
    api = AntminerModernWebAPI("10.10.101.10")
    monkeypatch.setattr(httpx, "AsyncClient", _RecordingAsyncClient)
    monkeypatch.setattr(_RecordingAsyncClient, "timeouts", [])

    asyncio.run(api.update_firmware(firmware))

    assert _RecordingAsyncClient.timeouts == [antminer.FIRMWARE_UPLOAD_TIMEOUT_SECONDS]
    assert antminer.FIRMWARE_UPLOAD_TIMEOUT_SECONDS > settings.get(
        "api_function_timeout"
    )
