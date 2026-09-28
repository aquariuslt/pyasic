import asyncio
import json
from unittest.mock import AsyncMock

from pyasic.errors import APIError
from pyasic.rpc.nonce import NonceRPCAPI


def test_single_and_batched_stats_use_new_api_without_legacy_fallback():
    rpc = NonceRPCAPI("192.0.2.1")
    requests = []

    async def respond(raw, **kwargs):
        request = json.loads(raw)
        requests.append(request)
        if request["command"] == "stats":
            assert request["new_api"] is True
            raise APIError("unsupported")
        return json.dumps(
            {"STATUS": [{"STATUS": "S"}], "VERSION": [{"API": "3.7"}]}
        ).encode()

    rpc._send_bytes = AsyncMock(side_effect=respond)
    data = asyncio.run(rpc.multicommand("version", "stats"))
    assert data["version"][0]["VERSION"][0]["API"] == "3.7"
    assert data["stats"] == [{}]
    assert len(requests) == 2
    assert {r["command"] for r in requests} == {"version", "stats"}
    assert set(rpc.transport_errors) == {"stats"}
    assert rpc.request_count == 2 and rpc.failure_count == 1


def test_regular_request_failure_preserves_new_stats():
    rpc = NonceRPCAPI("192.0.2.1")
    requests = []

    async def respond(raw, **kwargs):
        request = json.loads(raw)
        requests.append(request)
        if request["command"] != "stats":
            raise APIError("summary unavailable")
        assert request == {"command": "stats", "new_api": True}
        return b'{"STATUS":{"STATUS":"S"},"INFO":{},"STATS":[{"fan":[0,null]}]}'

    rpc._send_bytes = AsyncMock(side_effect=respond)
    data = asyncio.run(rpc.multicommand("summary", "stats"))
    assert data["stats"][0]["STATS"][0]["fan"] == [0, None]
    assert data["summary"] == [{}]
    assert len(requests) == 2
    assert set(rpc.transport_errors) == {"summary"}
    assert rpc.request_count == 2 and rpc.failure_count == 1
    assert asyncio.run(rpc.stats())["STATS"][0]["fan"][0] == 0


def test_special_api_errors_return_placeholders_without_retrying():
    rpc = NonceRPCAPI("192.0.2.1")
    rpc._send_bytes = AsyncMock(side_effect=APIError("unreachable"))
    assert asyncio.run(rpc.multicommand("summary", "stats", "legacy_stats")) == {
        "multicommand": True,
        "stats": [{}],
        "summary": [{}],
        "legacy_stats": [{}],
    }
    assert rpc._send_bytes.await_count == 3
    assert set(rpc.transport_errors) == {"stats", "summary", "legacy_stats"}
    assert rpc.request_count == rpc.failure_count == 3


def test_new_summary_and_legacy_psu_requests_are_distinct_and_read_only():
    rpc = NonceRPCAPI("192.0.2.1")
    rpc.send_command = AsyncMock(return_value={"STATUS": {"STATUS": "S"}})
    result = asyncio.run(rpc.multicommand("stats", "summary", "legacy_stats"))
    assert set(result) == {"multicommand", "stats", "summary", "legacy_stats"}
    calls = rpc.send_command.call_args_list
    assert [(call.args, call.kwargs) for call in calls] == [
        (("stats",), {"allow_warning": True, "new_api": True}),
        (("summary",), {"allow_warning": True, "new_api": True}),
        (("legacy_stats",), {"allow_warning": True}),
    ]
    asyncio.run(rpc.summary())
    rpc.send_command.assert_awaited_with("summary", new_api=True)
    asyncio.run(rpc.legacy_stats())
    rpc.send_command.assert_awaited_with("legacy_stats")


def test_legacy_psu_transport_failure_is_isolated():
    rpc = NonceRPCAPI("192.0.2.1")

    async def send(command, **kwargs):
        if not kwargs.get("new_api"):
            raise TimeoutError("PSU unavailable")
        return {"STATUS": {"STATUS": "S"}}

    rpc.send_command = AsyncMock(side_effect=send)
    result = asyncio.run(rpc.multicommand("stats", "summary", "legacy_stats"))
    assert set(result) == {"multicommand", "stats", "summary", "legacy_stats"}
    assert result["legacy_stats"] == [{}]
    assert isinstance(rpc.transport_errors["legacy_stats"], TimeoutError)


def test_nonce_does_not_repair_invalid_numeric_strings_to_zero():
    result = NonceRPCAPI._load_api_data(
        b'{"PSU Power W":"nan","PSU Voltage V":"inf"}\x00'
    )
    assert result == {"PSU Power W": "nan", "PSU Voltage V": "inf"}
