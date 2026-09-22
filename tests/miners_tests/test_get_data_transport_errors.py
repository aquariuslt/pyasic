import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from pyasic.data import HashBoard
from pyasic.errors import APIError, APITransportError
from pyasic.miners.backends.antminer import AntminerModern
from pyasic.miners.data import DataOptions

INCLUDE = [DataOptions.MAC, DataOptions.HOSTNAME, DataOptions.UPTIME]

# every web command answers, so the parsers see an empty dict instead of
# falling back to a live request
_WEB_ANSWERED = {
    "multicommand": True,
    "get_system_info": {},
    "get_network_info": {},
}


def _connect_error() -> httpx.ConnectError:
    return httpx.ConnectError(
        "connection refused",
        request=httpx.Request("GET", "http://10.0.0.1/cgi-bin/get_system_info.cgi"),
    )


def _miner(
    monkeypatch,
    *,
    failing_web_command: str | None = None,
    failing_rpc_command: str | None = None,
):
    miner = AntminerModern("10.0.0.1")

    async def rpc_multicommand(*commands, **kwargs):
        for command in commands:
            miner.rpc._start_command(command)
        if failing_rpc_command is not None:
            miner.rpc._record_transport_error(failing_rpc_command, _connect_error())
        return {}

    async def web_multicommand(*commands, **kwargs):
        for command in commands:
            miner.web._start_command(command)
        if failing_web_command is not None:
            miner.web._record_transport_error(failing_web_command, _connect_error())
        return dict(_WEB_ANSWERED)

    monkeypatch.setattr(miner.rpc, "multicommand", rpc_multicommand)
    monkeypatch.setattr(miner.web, "multicommand", web_multicommand)
    monkeypatch.setattr(miner, "_get_uptime", AsyncMock(return_value=123))
    return miner


def test_fields_fed_by_a_command_that_never_answered_are_listed(monkeypatch):
    miner = _miner(monkeypatch, failing_web_command="get_system_info")

    result = asyncio.run(miner.get_data_with_errors(include=INCLUDE))

    assert set(result.field_transport_errors) == {"mac", "hostname"}
    assert isinstance(result.field_transport_errors["mac"], httpx.ConnectError)


def test_a_field_that_never_answered_keeps_its_default_without_a_parser_error(
    monkeypatch,
):
    miner = _miner(monkeypatch, failing_web_command="get_system_info")

    result = asyncio.run(miner.get_data_with_errors(include=INCLUDE))

    assert result.data.mac is None
    assert result.field_parse_errors == {}


def test_a_field_fed_by_an_rpc_command_that_never_answered_is_listed(monkeypatch):
    miner = _miner(monkeypatch, failing_rpc_command="summary")

    result = asyncio.run(
        miner.get_data_with_errors(include=[DataOptions.HASHRATE, DataOptions.MAC])
    )

    assert set(result.field_transport_errors) == {"hashrate"}


def test_transport_failures_do_not_carry_over_to_the_next_read(monkeypatch):
    miner = _miner(monkeypatch, failing_web_command="get_system_info")
    asyncio.run(miner.get_data_with_errors(include=INCLUDE))
    miner.web.multicommand = AsyncMock(return_value=dict(_WEB_ANSWERED))

    result = asyncio.run(miner.get_data_with_errors(include=INCLUDE))

    assert result.field_transport_errors == {}


def test_an_endpoint_read_outside_the_multicommand_is_listed_for_its_field(
    monkeypatch,
):
    # the serial number falls back to the backend's own 6060 endpoint when the
    # multicommand answer does not carry it
    miner = _miner(monkeypatch, failing_web_command=None)
    monkeypatch.setattr(
        miner.web,
        "_invoke_http_get",
        AsyncMock(return_value={"success": False, "message": "Timeout error occurred"}),
    )

    result = asyncio.run(
        miner.get_data_with_errors(include=[*INCLUDE, DataOptions.SERIAL_NUMBER])
    )

    assert isinstance(result.field_transport_errors["serial_number"], APITransportError)
    assert "mac" not in result.field_transport_errors


def test_get_data_does_not_raise_on_a_transport_error(monkeypatch):
    miner = _miner(monkeypatch, failing_web_command="get_system_info")

    data = asyncio.run(miner.get_data(include=INCLUDE))

    assert data.mac is None
    assert data.uptime == 123


def _miner_with_every_command_failing(monkeypatch):
    miner = AntminerModern("10.0.0.1")

    async def rpc_multicommand(*commands, **kwargs):
        for command in commands:
            miner.rpc._start_command(command)
            miner.rpc._record_transport_error(command, _connect_error())
        return {}

    async def web_multicommand(*commands, **kwargs):
        for command in commands:
            miner.web._start_command(command)
            miner.web._record_transport_error(command, _connect_error())
        return {}

    monkeypatch.setattr(miner.rpc, "multicommand", rpc_multicommand)
    monkeypatch.setattr(miner.web, "multicommand", web_multicommand)
    _keep_parsers_off_the_wire(miner, monkeypatch)
    return miner


def _keep_parsers_off_the_wire(miner, monkeypatch):
    # these parsers ask the device themselves when the multicommand gave them
    # nothing; the test is about the read, not about them
    monkeypatch.setattr(miner, "_get_uptime", AsyncMock(return_value=None))
    monkeypatch.setattr(miner, "_get_temperature_raw", AsyncMock(return_value=[]))


def test_a_read_whose_every_command_failed_all_requests_failed(monkeypatch):
    miner = _miner_with_every_command_failing(monkeypatch)

    result = asyncio.run(miner.get_data_with_errors(include=INCLUDE))

    assert result.all_requests_failed


def test_a_read_all_requests_failed_even_with_fields_that_send_no_command(monkeypatch):
    # temperature_raw and the like have no command behind them, so a field
    # based rule would never see the device as unreached
    miner = _miner_with_every_command_failing(monkeypatch)

    result = asyncio.run(
        miner.get_data_with_errors(include=[*INCLUDE, DataOptions.TEMPERATURE_RAW])
    )

    assert result.all_requests_failed
    assert "temperature_raw" not in result.field_transport_errors


def test_a_read_with_one_command_answering_is_not_unanswered(monkeypatch):
    miner = _miner(monkeypatch, failing_web_command="get_system_info")

    result = asyncio.run(miner.get_data_with_errors(include=INCLUDE))

    assert not result.all_requests_failed


def test_a_read_that_sent_no_command_is_not_unanswered(monkeypatch):
    miner = _miner(monkeypatch)
    _keep_parsers_off_the_wire(miner, monkeypatch)

    result = asyncio.run(
        miner.get_data_with_errors(include=[DataOptions.TEMPERATURE_RAW])
    )

    assert not result.all_requests_failed


def test_a_multicommand_that_raises_does_not_interrupt_the_read(monkeypatch):
    miner = AntminerModern("10.0.0.1")

    async def rpc_multicommand(*commands, **kwargs):
        return {}

    async def web_multicommand(*commands, **kwargs):
        raise APIError("Command failed: get_system_info")

    monkeypatch.setattr(miner.rpc, "multicommand", rpc_multicommand)
    monkeypatch.setattr(miner.web, "multicommand", web_multicommand)
    monkeypatch.setattr(miner, "_get_uptime", AsyncMock(return_value=123))

    result = asyncio.run(miner.get_data_with_errors(include=INCLUDE))

    assert result.data.uptime == 123
    assert set(result.field_transport_errors) == {"mac", "hostname"}
    assert isinstance(result.field_transport_errors["mac"], APIError)


def test_get_data_names_the_transport_failure_as_the_cause_of_a_parser_error(
    monkeypatch,
):
    miner = _miner(monkeypatch, failing_web_command="get_system_info")
    monkeypatch.setattr(miner, "_get_mac", AsyncMock(side_effect=KeyError("macaddr")))

    with pytest.raises(APIError) as raised:
        asyncio.run(miner.get_data(include=INCLUDE))

    assert isinstance(raised.value.__cause__, httpx.ConnectError)


def test_a_parser_asking_the_device_itself_charges_its_own_field(monkeypatch):
    # hostname re-reads get_system_info inside the parser when the batch gave
    # it nothing; that request failing must land on hostname, not on the
    # fields the multicommand already answered
    miner = _miner(monkeypatch)

    async def hostname_reading_system_info_again(web_get_system_info=None):
        miner.web._start_command("get_system_info")
        miner.web._record_transport_error("get_system_info", _connect_error())
        return None

    monkeypatch.setattr(miner, "_get_hostname", hostname_reading_system_info_again)

    result = asyncio.run(miner.get_data_with_errors(include=INCLUDE))

    assert set(result.field_transport_errors) == {"hostname"}
    assert result.data.uptime == 123


def test_a_parser_request_does_not_make_the_read_unanswered(monkeypatch):
    miner = _miner(monkeypatch)

    async def hashboards_reading_stats_again():
        miner.rpc._start_command("stats")
        miner.rpc._record_transport_error("stats", _connect_error())
        return []

    monkeypatch.setattr(miner, "_get_hashboards", hashboards_reading_stats_again)

    result = asyncio.run(
        miner.get_data_with_errors(include=[*INCLUDE, DataOptions.HASHBOARDS])
    )

    assert not result.all_requests_failed


def test_a_multicommand_raising_something_other_than_an_api_error_propagates(
    monkeypatch,
):
    miner = AntminerModern("10.0.0.1")

    async def rpc_multicommand(*commands, **kwargs):
        return {}

    async def web_multicommand(*commands, **kwargs):
        raise RuntimeError("programming error")

    monkeypatch.setattr(miner.rpc, "multicommand", rpc_multicommand)
    monkeypatch.setattr(miner.web, "multicommand", web_multicommand)

    with pytest.raises(RuntimeError):
        asyncio.run(miner.get_data_with_errors(include=INCLUDE))


def test_a_field_filled_in_by_a_fallback_source_is_not_unread(monkeypatch):
    # get_system_info never answered, but the serial number parser fell back
    # to the 6060 endpoint and read one: the field was read, and the read as
    # a whole got an answer
    miner = _miner(monkeypatch, failing_web_command="get_system_info")

    async def serial_number_from_6060(web_get_system_info=None):
        miner.web._start_command("serial_number")
        return "SN-123"

    monkeypatch.setattr(miner, "_get_serial_number", serial_number_from_6060)

    result = asyncio.run(
        miner.get_data_with_errors(include=[DataOptions.MAC, DataOptions.SERIAL_NUMBER])
    )

    assert result.data.serial_number == "SN-123"
    assert set(result.field_transport_errors) == {"mac"}


def test_a_fallback_that_got_through_means_the_read_was_answered(monkeypatch):
    miner = _miner_with_every_command_failing(monkeypatch)

    async def serial_number_from_6060(web_get_system_info=None):
        miner.web._start_command("serial_number")
        return "SN-123"

    monkeypatch.setattr(miner, "_get_serial_number", serial_number_from_6060)

    result = asyncio.run(
        miner.get_data_with_errors(include=[DataOptions.MAC, DataOptions.SERIAL_NUMBER])
    )

    assert not result.all_requests_failed


def test_a_read_whose_only_request_came_from_a_parser_and_failed_all_requests_failed(
    monkeypatch,
):
    miner = _miner(monkeypatch)

    async def hashboards_reading_stats_again():
        miner.rpc._start_command("stats")
        miner.rpc._record_transport_error("stats", _connect_error())
        return []

    monkeypatch.setattr(miner, "_get_hashboards", hashboards_reading_stats_again)

    result = asyncio.run(miner.get_data_with_errors(include=[DataOptions.HASHBOARDS]))

    assert result.all_requests_failed


def test_a_parser_rereading_the_failed_command_successfully_settles_its_field(
    monkeypatch,
):
    # stats failed in the multicommand phase; the fans parser asks for stats
    # again on its own and gets it, so fans was read after all while uptime,
    # which parsed the empty batch answer, was not
    miner = _miner(monkeypatch, failing_rpc_command="stats")

    async def fans_reading_stats_again(rpc_stats=None):
        miner.rpc._start_command("stats")
        return []

    monkeypatch.setattr(miner, "_get_fans", fans_reading_stats_again)
    monkeypatch.setattr(miner, "_get_uptime", AsyncMock(return_value=None))

    result = asyncio.run(
        miner.get_data_with_errors(include=[DataOptions.UPTIME, DataOptions.FANS])
    )

    assert set(result.field_transport_errors) == {"uptime"}


def test_a_command_answered_once_and_failed_once_is_not_unanswered(monkeypatch):
    # stats answered in the multicommand phase (uptime parsed); the hashboards
    # parser asked for stats again and that request failed
    miner = _miner(monkeypatch)

    async def hashboards_reading_stats_again():
        miner.rpc._start_command("stats")
        miner.rpc._record_transport_error("stats", _connect_error())
        return []

    monkeypatch.setattr(miner, "_get_hashboards", hashboards_reading_stats_again)

    result = asyncio.run(
        miner.get_data_with_errors(include=[DataOptions.UPTIME, DataOptions.HASHBOARDS])
    )

    assert result.data.uptime == 123
    assert not result.all_requests_failed


def test_a_field_read_from_its_second_source_is_not_unread(monkeypatch):
    # get_system_info failed in the batch and again inside the mac parser,
    # which then read the mac from get_network_info
    miner = _miner(monkeypatch, failing_web_command="get_system_info")

    async def mac_from_network_info(
        web_get_system_info=None, web_get_network_info=None
    ):
        miner.web._start_command("get_system_info")
        miner.web._record_transport_error("get_system_info", _connect_error())
        miner.web._start_command("get_network_info")
        return "AA:BB:CC:DD:EE:FF"

    monkeypatch.setattr(miner, "_get_mac", mac_from_network_info)

    result = asyncio.run(
        miner.get_data_with_errors(include=[DataOptions.MAC, DataOptions.HOSTNAME])
    )

    assert result.data.mac == "AA:BB:CC:DD:EE:FF"
    assert set(result.field_transport_errors) == {"hostname"}


def _web_reads(miner, monkeypatch, *, failing, answers):
    """Fake the web reads a parser makes on its own: `failing` commands are
    recorded as transport failures and return None, `answers` return their
    dict."""

    def make(command):
        async def read(*args, **kwargs):
            miner.web._start_command(command)
            if command in failing:
                miner.web._record_transport_error(command, _connect_error())
                return None
            return answers[command]

        return read

    for command in {*failing, *answers}:
        monkeypatch.setattr(miner.web, command, make(command))


def test_real_mac_parser_reading_the_mac_from_the_batch_network_info_is_read(
    monkeypatch,
):
    # get_system_info failed in the batch and again inside _get_mac, but the
    # batch had answered get_network_info with the mac
    miner = AntminerModern("10.0.0.1")

    async def rpc_multicommand(*commands, **kwargs):
        return {}

    async def web_multicommand(*commands, **kwargs):
        for command in commands:
            miner.web._start_command(command)
        miner.web._record_transport_error("get_system_info", _connect_error())
        return {
            "multicommand": True,
            "get_network_info": {"macaddr": "AA:BB:CC:DD:EE:FF"},
        }

    monkeypatch.setattr(miner.rpc, "multicommand", rpc_multicommand)
    monkeypatch.setattr(miner.web, "multicommand", web_multicommand)
    _web_reads(miner, monkeypatch, failing={"get_system_info"}, answers={})

    result = asyncio.run(miner.get_data_with_errors(include=[DataOptions.MAC]))

    assert result.data.mac == "AA:BB:CC:DD:EE:FF"
    assert result.field_transport_errors == {}


def test_real_serial_parser_left_empty_by_a_failed_fallback_is_unread(monkeypatch):
    # the batch answered get_system_info without a serial number, so the
    # parser fell back to the 6060 endpoint, which never answered
    miner = _miner(monkeypatch)

    async def serial_number_endpoint():
        miner.web._start_command("serial_number")
        miner.web._record_endpoint_failure(
            "serial_number", {"success": False, "message": "refused"}
        )
        return {}

    monkeypatch.setattr(miner.web, "get_serial_number", serial_number_endpoint)

    result = asyncio.run(
        miner.get_data_with_errors(include=[DataOptions.SERIAL_NUMBER])
    )

    assert result.data.serial_number is None
    assert set(result.field_transport_errors) == {"serial_number"}


def test_real_serial_parser_answered_without_a_serial_is_empty_not_unread(
    monkeypatch,
):
    # every request got through; the device just reports no serial number
    miner = _miner(monkeypatch)

    async def serial_number_endpoint():
        miner.web._start_command("serial_number")
        return {"serinum": None}

    monkeypatch.setattr(miner.web, "get_serial_number", serial_number_endpoint)

    result = asyncio.run(
        miner.get_data_with_errors(include=[DataOptions.SERIAL_NUMBER])
    )

    assert result.data.serial_number is None
    assert result.field_transport_errors == {}


def _stats_refusing(miner):
    async def stats(*args, **kwargs):
        miner.rpc._start_command("stats")
        miner.rpc._record_transport_error("stats", _connect_error())
        raise APIError("stats failed")

    return stats


def test_a_container_the_parser_rebuilds_from_the_model_is_not_reported_unread(
    monkeypatch,
):
    # _get_hashboards answers a failed stats request with one board per
    # expected slot, carrying the layout. Telling that apart from a board the
    # device described takes per-backend knowledge this result does not have,
    # so the field is not reported as unread and the caller weighs the data
    miner = _miner(monkeypatch)
    miner.expected_hashboards = 3
    miner.expected_chips = 216
    monkeypatch.setattr(miner.rpc, "stats", _stats_refusing(miner))

    result = asyncio.run(miner.get_data_with_errors(include=[DataOptions.HASHBOARDS]))

    assert len(result.data.hashboards) == 3
    assert result.field_transport_errors == {}
    # the read itself is still known to have reached nothing
    assert result.all_requests_failed


def test_real_fans_parser_left_with_the_expected_count_is_unread(monkeypatch):
    # _get_fans answers a failed stats request with one speedless Fan per
    # expected fan; stats is its declared command, so the batch sends it
    miner = _miner(monkeypatch, failing_rpc_command="stats")
    miner.expected_fans = 4

    result = asyncio.run(miner.get_data_with_errors(include=[DataOptions.FANS]))

    assert [fan.speed for fan in result.data.fans] == [None] * 4
    assert set(result.field_transport_errors) == {"fans"}


def test_a_hashboard_that_answered_is_read_even_when_another_request_failed(
    monkeypatch,
):
    miner = _miner(monkeypatch, failing_web_command="get_system_info")
    miner.expected_hashboards = 1
    miner.expected_chips = 216

    async def hashboards_with_a_live_board():
        board = HashBoard(slot=0, expected_chips=216)
        board.chips = 216
        board.missing = False
        return [board]

    monkeypatch.setattr(miner, "_get_hashboards", hashboards_with_a_live_board)

    result = asyncio.run(
        miner.get_data_with_errors(include=[DataOptions.HASHBOARDS, DataOptions.MAC])
    )

    assert set(result.field_transport_errors) == {"mac"}
