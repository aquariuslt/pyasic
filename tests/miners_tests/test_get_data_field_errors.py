import asyncio
from unittest.mock import AsyncMock

import pytest

from pyasic.errors import APIError
from pyasic.miners.backends.antminer import AntminerModern
from pyasic.miners.data import DataOptions


def _miner_with_one_failing_parser(monkeypatch):
    miner = AntminerModern("10.0.0.1")
    monkeypatch.setattr(miner.rpc, "multicommand", AsyncMock(return_value={}))
    monkeypatch.setattr(miner.web, "multicommand", AsyncMock(return_value={}))
    monkeypatch.setattr(miner, "_get_uptime", AsyncMock(return_value=123))
    monkeypatch.setattr(miner, "_get_hostname", AsyncMock(return_value="miner-1"))
    monkeypatch.setattr(miner, "_get_wattage", AsyncMock(side_effect=KeyError("power")))
    return miner


INCLUDE = [DataOptions.UPTIME, DataOptions.WATTAGE, DataOptions.HOSTNAME]


def test_get_data_still_raises_api_error_naming_the_failed_field(monkeypatch):
    miner = _miner_with_one_failing_parser(monkeypatch)

    with pytest.raises(
        APIError, match=r"Failed to call wattage on .* while getting data\."
    ) as raised:
        asyncio.run(miner.get_data(include=INCLUDE))

    assert isinstance(raised.value.__cause__, KeyError)


def test_get_data_with_field_errors_keeps_the_fields_that_parsed(monkeypatch):
    miner = _miner_with_one_failing_parser(monkeypatch)

    result = asyncio.run(miner.get_data_with_field_errors(include=INCLUDE))

    assert result.data.uptime == 123
    assert result.data.hostname == "miner-1"
    assert result.data.wattage is None
    assert list(result.field_errors) == ["wattage"]
    assert isinstance(result.field_errors["wattage"], KeyError)


def test_get_data_with_field_errors_is_empty_when_every_field_parses(monkeypatch):
    miner = _miner_with_one_failing_parser(monkeypatch)
    monkeypatch.setattr(miner, "_get_wattage", AsyncMock(return_value=3000))

    result = asyncio.run(miner.get_data_with_field_errors(include=INCLUDE))

    assert result.data.wattage == 3000
    assert result.field_errors == {}
