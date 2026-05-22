import asyncio
from unittest.mock import AsyncMock, patch

from pyasic.rpc.antminer import AntminerRPCAPI
from pyasic.rpc.base import BaseMinerRPCAPI
from pyasic.rpc.spideros import SpiderOSRPCAPI


def test_spideros_rpcapi_is_independent_class():
    assert SpiderOSRPCAPI is not AntminerRPCAPI
    assert AntminerRPCAPI not in SpiderOSRPCAPI.__mro__[1:]


@patch.object(BaseMinerRPCAPI, "send_command", new_callable=AsyncMock)
def test_spideros_rpcapi_new_api_methods_match_antminer_behavior(mock_send_command):
    mock_send_command.return_value = {"ok": True}
    api = SpiderOSRPCAPI("10.10.101.10")

    assert asyncio.run(api.stats(new_api=True)) == {"ok": True}
    assert asyncio.run(api.summary(new_api=True)) == {"ok": True}
    assert asyncio.run(api.pools(new_api=True)) == {"ok": True}

    assert mock_send_command.await_args_list[0].args == ("stats",)
    assert mock_send_command.await_args_list[0].kwargs == {"new_api": True}
    assert mock_send_command.await_args_list[1].args == ("summary",)
    assert mock_send_command.await_args_list[1].kwargs == {"new_api": True}
    assert mock_send_command.await_args_list[2].args == ("pools",)
    assert mock_send_command.await_args_list[2].kwargs == {"new_api": True}
