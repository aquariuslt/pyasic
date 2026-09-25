import asyncio
import json

import httpx

from pyasic import settings
from pyasic.web.sdminer import SDMinerWebAPI


def _configure_mock_transport(monkeypatch, handle_request):
    monkeypatch.setattr(
        settings,
        "transport",
        lambda *args, **kwargs: httpx.MockTransport(handle_request),
    )


def test_multicommand_reads_each_command_from_its_own_base(monkeypatch):
    seen = []

    def handle_request(request):
        seen.append(request.url.path)
        return httpx.Response(200, json={"path": request.url.path})

    _configure_mock_transport(monkeypatch, handle_request)
    api = SDMinerWebAPI("10.10.101.10")

    asyncio.run(api.multicommand("overview", "system_info"))

    assert sorted(seen) == ["/api/v1/overview", "/system/v1/info"]


def test_multicommand_keys_each_answer_by_command(monkeypatch):
    _configure_mock_transport(
        monkeypatch,
        lambda request: httpx.Response(200, json={"path": request.url.path}),
    )
    api = SDMinerWebAPI("10.10.101.10")

    result = asyncio.run(api.multicommand("find_miner"))

    assert result == {
        "find_miner": {"path": "/system/v1/find-miner"},
        "multicommand": True,
    }


def test_json_without_json_content_type_is_decoded(monkeypatch):
    # some /system/v1 scripts omit the content type
    _configure_mock_transport(
        monkeypatch,
        lambda request: httpx.Response(
            200, text='{"enabled": false}', headers={"Content-Type": "text/html"}
        ),
    )
    api = SDMinerWebAPI("10.10.101.10")

    assert asyncio.run(api.find_miner()) == {"enabled": False}


def test_refused_request_answers_empty(monkeypatch):
    _configure_mock_transport(
        monkeypatch, lambda request: httpx.Response(403, text="forbidden")
    )
    api = SDMinerWebAPI("10.10.101.10")

    assert asyncio.run(api.overview()) == {}


def test_refused_request_is_recorded_under_its_command(monkeypatch):
    _configure_mock_transport(
        monkeypatch, lambda request: httpx.Response(403, text="forbidden")
    )
    api = SDMinerWebAPI("10.10.101.10")

    asyncio.run(api.overview())

    assert str(api.transport_errors["overview"]) == "HTTP 403"


def test_body_that_is_not_json_is_recorded_as_a_decode_failure(monkeypatch):
    _configure_mock_transport(
        monkeypatch, lambda request: httpx.Response(200, text="not found\n")
    )
    api = SDMinerWebAPI("10.10.101.10")

    asyncio.run(api.system())

    assert "system" in api.transport_errors


def test_connection_error_is_recorded_under_its_command(monkeypatch):
    def handle_request(request):
        raise httpx.ConnectError("connection refused", request=request)

    _configure_mock_transport(monkeypatch, handle_request)
    api = SDMinerWebAPI("10.10.101.10")

    asyncio.run(api.multicommand("pools"))

    assert isinstance(api.transport_errors["pools"], httpx.ConnectError)


def test_logs_are_returned_as_the_raw_body(monkeypatch):
    body = b'{"miner": [], "events": [], "audit": []}'
    _configure_mock_transport(
        monkeypatch, lambda request: httpx.Response(200, content=body)
    )
    api = SDMinerWebAPI("10.10.101.10")

    assert asyncio.run(api.logs()) == body


def test_logs_are_read_from_the_native_base(monkeypatch):
    seen = []

    def handle_request(request):
        seen.append(request.url.path)
        return httpx.Response(200, content=b"{}")

    _configure_mock_transport(monkeypatch, handle_request)

    asyncio.run(SDMinerWebAPI("10.10.101.10").logs())

    assert seen == ["/api/v1/logs"]


def test_support_bundle_is_returned_as_the_raw_body(monkeypatch):
    bundle = b"\x1f\x8b\x08\x00tar-gz-bytes"
    _configure_mock_transport(
        monkeypatch,
        lambda request: httpx.Response(
            200, content=bundle, headers={"Content-Type": "application/gzip"}
        ),
    )
    api = SDMinerWebAPI("10.10.101.10")

    assert asyncio.run(api.support_bundle()) == bundle


def test_support_bundle_is_read_from_the_system_base(monkeypatch):
    seen = []

    def handle_request(request):
        seen.append(request.url.path)
        return httpx.Response(200, content=b"\x1f\x8b")

    _configure_mock_transport(monkeypatch, handle_request)

    asyncio.run(SDMinerWebAPI("10.10.101.10").support_bundle())

    assert seen == ["/system/v1/support-bundle"]


def test_refused_support_bundle_answers_none(monkeypatch):
    _configure_mock_transport(
        monkeypatch, lambda request: httpx.Response(403, text="forbidden")
    )

    assert asyncio.run(SDMinerWebAPI("10.10.101.10").support_bundle()) is None


def test_set_find_miner_posts_the_target_state(monkeypatch):
    seen = []

    def handle_request(request):
        seen.append((request.method, request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"stats": "success", "enabled": True})

    _configure_mock_transport(monkeypatch, handle_request)

    asyncio.run(SDMinerWebAPI("10.10.101.10").set_find_miner(True))

    assert seen == [("POST", "/system/v1/find-miner", {"enabled": True})]
