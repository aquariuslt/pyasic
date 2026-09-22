import asyncio
from unittest.mock import AsyncMock

import pytest

from pyasic.errors import APIError, APITransportError
from pyasic.rpc.bmminer import BMMinerRPCAPI


class _FakeWriter:
    """Stands in for a StreamWriter: the send path only writes and closes."""

    def write(self, data: bytes) -> None:
        return None

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None


def _api_with_dead_socket(monkeypatch) -> BMMinerRPCAPI:
    api = BMMinerRPCAPI("10.0.0.1")
    monkeypatch.setattr(
        api,
        "_send_bytes",
        AsyncMock(side_effect=APITransportError("Read timeout after 10s")),
    )
    return api


def test_send_command_returns_empty_when_the_socket_never_answers(monkeypatch):
    api = _api_with_dead_socket(monkeypatch)

    assert asyncio.run(api.send_command("summary")) == {}


def test_send_command_records_the_failure_under_the_command(monkeypatch):
    api = _api_with_dead_socket(monkeypatch)

    asyncio.run(api.send_command("summary"))

    assert isinstance(api.transport_errors["summary"], APITransportError)


def test_multicommand_records_the_failure_under_every_joined_command(monkeypatch):
    api = _api_with_dead_socket(monkeypatch)

    asyncio.run(api.multicommand("summary", "stats"))

    assert set(api.transport_errors) == {"summary", "stats"}


def test_connection_refused_reply_is_recorded_as_a_transport_error(monkeypatch):
    api = BMMinerRPCAPI("10.0.0.1")
    monkeypatch.setattr(
        api,
        "_send_bytes",
        AsyncMock(return_value=b"Socket connect failed: Connection refused\n"),
    )

    asyncio.run(api.send_command("summary", ignore_errors=True))

    assert isinstance(api.transport_errors["summary"], APITransportError)


def test_send_bytes_raises_transport_error_when_the_connection_is_refused(
    monkeypatch,
):
    api = BMMinerRPCAPI("10.0.0.1")

    async def refuse(*args, **kwargs):
        raise ConnectionRefusedError(111, "Connection refused")

    monkeypatch.setattr(asyncio, "open_connection", refuse)

    with pytest.raises(APITransportError):
        asyncio.run(api._send_bytes(b"{}"))


def test_send_bytes_raises_transport_error_when_the_read_times_out(monkeypatch):
    api = BMMinerRPCAPI("10.0.0.1")

    async def connect(*args, **kwargs):
        return object(), _FakeWriter()

    async def time_out(*args, **kwargs):
        raise TimeoutError

    monkeypatch.setattr(asyncio, "open_connection", connect)
    monkeypatch.setattr(api, "_read_bytes", time_out)

    with pytest.raises(APITransportError):
        asyncio.run(api._send_bytes(b"{}"))


def test_an_answer_that_will_not_parse_is_recorded_as_a_transport_error(monkeypatch):
    api = BMMinerRPCAPI("10.0.0.1")
    monkeypatch.setattr(api, "_send_bytes", AsyncMock(return_value=b"<html>"))

    with pytest.raises(APIError):
        asyncio.run(api.send_command("summary"))

    assert isinstance(api.transport_errors["summary"], APITransportError)


def test_a_command_that_answers_forgets_its_earlier_failure(monkeypatch):
    api = _api_with_dead_socket(monkeypatch)
    asyncio.run(api.send_command("summary"))

    monkeypatch.setattr(api, "_send_bytes", AsyncMock(return_value=b'{"STATUS": "S"}'))
    asyncio.run(api.send_command("summary"))

    assert api.transport_errors == {}


def test_a_command_resent_alone_clears_only_its_own_failure(monkeypatch):
    # a field whose command came back empty from the multicommand sends it
    # again on its own; the answer must not clear the commands still missing
    api = _api_with_dead_socket(monkeypatch)
    asyncio.run(api.multicommand("summary", "stats"))

    monkeypatch.setattr(api, "_send_bytes", AsyncMock(return_value=b'{"STATUS": "S"}'))
    asyncio.run(api.send_command("summary"))

    assert set(api.transport_errors) == {"stats"}


def test_a_connection_reset_while_closing_keeps_the_answer(monkeypatch):
    api = BMMinerRPCAPI("10.0.0.1")

    class _ResettingWriter(_FakeWriter):
        async def wait_closed(self) -> None:
            raise ConnectionResetError(104, "Connection reset by peer")

    async def connect(*args, **kwargs):
        return object(), _ResettingWriter()

    async def read(*args, **kwargs):
        return b'{"STATUS": "S"}'

    monkeypatch.setattr(asyncio, "open_connection", connect)
    monkeypatch.setattr(api, "_read_bytes", read)

    assert asyncio.run(api._send_bytes(b"{}")) == b'{"STATUS": "S"}'
