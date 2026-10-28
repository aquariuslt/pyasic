import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from pyasic.miners.antminer.nonce import NonceS21Plus, NonceS21XP
from pyasic.miners.factory import MinerFactory, MinerIdentifyStatus, MinerTypes


@pytest.mark.parametrize("terminator", ["", "\x00"])
@pytest.mark.parametrize("api_fields", [{}, {"Nonce API": 1}, {"Nonce API": 2}])
def test_version_marker_precedes_stock_antminer_detection(terminator, api_fields):
    data = {"VERSION": [{"Firmware": "Nonce", "Model": "Antminer S21+", **api_fields}]}
    assert (
        MinerFactory._parse_socket_type(json.dumps(data) + terminator)
        is MinerTypes.NONCE
    )
    assert (
        MinerFactory._parse_socket_type('{"VERSION":[{"Type":"Antminer S21+"}]}')
        is MinerTypes.ANTMINER
    )
    assert (
        MinerFactory._parse_socket_type(
            '{"VERSION":[{"Firmware":"Nonce","Nonce API":1}]}'
        )
        is None
    )


@pytest.mark.parametrize("api_fields", [{}, {"Nonce API": 1}, {"Nonce API": 2}])
@pytest.mark.parametrize(
    ("model", "miner_class", "chips"),
    [("Antminer S21+", NonceS21Plus, 55), ("Antminer S21 XP", NonceS21XP, 91)],
)
def test_identification_selects_nonce_backend_over_tcp(
    monkeypatch, api_fields, model, miner_class, chips
):
    factory = MinerFactory()
    response = {"VERSION": [{"Firmware": "Nonce", "Model": model, **api_fields}]}
    monkeypatch.setattr(
        factory, "_get_miner_type", AsyncMock(return_value=MinerTypes.NONCE)
    )
    monkeypatch.setattr(factory, "send_api_command", AsyncMock(return_value=response))
    result = asyncio.run(factory.identify_miner("192.0.2.1"))
    assert result.status is MinerIdentifyStatus.IDENTIFIED
    assert isinstance(result.miner, miner_class)
    assert result.miner.expected_chips == chips
    assert result.miner.expected_hashboards == 3
    factory.send_api_command.assert_awaited_once_with("192.0.2.1", "version")
