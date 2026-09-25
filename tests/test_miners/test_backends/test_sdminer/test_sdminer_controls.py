"""The two controls the GridFW backend implements: the locator light and the
log download. Both artifacts are passed on as the firmware serves them."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from pyasic.miners.antminer.sdminer import SDMinerS21XP

LOGS_BODY = b'{"miner": [], "events": [], "audit": []}'
BUNDLE_BODY = b"\x1f\x8b\x08\x00support-bundle"


def create_miner_with_web_methods(monkeypatch, **web_methods):
    miner = SDMinerS21XP("10.10.101.10")
    for name, mock in web_methods.items():
        monkeypatch.setattr(miner.web, name, mock)
    return miner


def test_current_logs_are_the_raw_json_document(monkeypatch):
    miner = create_miner_with_web_methods(
        monkeypatch, logs=AsyncMock(return_value=LOGS_BODY)
    )

    result = asyncio.run(miner.download_logs("current"))

    assert result["data"] == {"content": LOGS_BODY, "ext": "json", "log_type": "flat"}


def test_history_logs_are_the_raw_support_bundle(monkeypatch):
    miner = create_miner_with_web_methods(
        monkeypatch, support_bundle=AsyncMock(return_value=BUNDLE_BODY)
    )

    result = asyncio.run(miner.download_logs("history"))

    assert result["data"] == {
        "content": BUNDLE_BODY,
        "ext": "tar.gz",
        "log_type": "compressed",
    }


def test_download_reports_success(monkeypatch):
    miner = create_miner_with_web_methods(
        monkeypatch, logs=AsyncMock(return_value=LOGS_BODY)
    )

    assert asyncio.run(miner.download_logs("current"))["success"] is True


def test_failed_download_names_the_transport_error(monkeypatch):
    miner = SDMinerS21XP("10.10.101.10")

    async def refused():
        miner.web._start_command("support_bundle")
        miner.web._record_transport_error("support_bundle", RuntimeError("HTTP 403"))
        return None

    monkeypatch.setattr(miner.web, "support_bundle", refused)

    result = asyncio.run(miner.download_logs("history"))

    assert (result["success"], result["message"]) == (
        False,
        "failed to download history logs: HTTP 403",
    )


def test_unknown_log_category_is_refused():
    with pytest.raises(ValueError):
        asyncio.run(SDMinerS21XP("10.10.101.10").download_logs("recent"))


def test_light_on_answers_the_confirmed_state(monkeypatch):
    miner = create_miner_with_web_methods(
        monkeypatch,
        set_find_miner=AsyncMock(return_value={"stats": "success", "enabled": True}),
    )

    assert asyncio.run(miner.fault_light_on()) is True


def test_light_off_answers_the_confirmed_state(monkeypatch):
    miner = create_miner_with_web_methods(
        monkeypatch,
        set_find_miner=AsyncMock(return_value={"stats": "success", "enabled": False}),
    )

    assert asyncio.run(miner.fault_light_off()) is False


def test_light_write_sends_the_target_state(monkeypatch):
    write = AsyncMock(return_value={"stats": "success", "enabled": True})
    miner = create_miner_with_web_methods(monkeypatch, set_find_miner=write)

    asyncio.run(miner.fault_light_on())

    assert write.await_args.args == (True,)


def test_light_write_the_firmware_did_not_accept_answers_none(monkeypatch):
    # /system/v1 answers HTTP 200 on a failed write; stats carries the verdict
    miner = create_miner_with_web_methods(
        monkeypatch,
        set_find_miner=AsyncMock(return_value={"stats": "error", "enabled": False}),
    )

    assert asyncio.run(miner.fault_light_on()) is None


def test_light_write_left_in_the_other_state_answers_none(monkeypatch):
    miner = create_miner_with_web_methods(
        monkeypatch,
        set_find_miner=AsyncMock(return_value={"stats": "success", "enabled": True}),
    )

    assert asyncio.run(miner.fault_light_off()) is None


def test_refused_light_write_answers_none(monkeypatch):
    miner = create_miner_with_web_methods(
        monkeypatch, set_find_miner=AsyncMock(return_value={})
    )

    assert asyncio.run(miner.fault_light_on()) is None


def test_confirmed_light_state_is_remembered(monkeypatch):
    miner = create_miner_with_web_methods(
        monkeypatch,
        set_find_miner=AsyncMock(return_value={"stats": "success", "enabled": True}),
    )

    asyncio.run(miner.fault_light_on())

    assert miner.light is True
