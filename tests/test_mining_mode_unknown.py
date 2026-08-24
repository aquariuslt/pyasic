from pyasic.config import MinerConfig, MiningModeConfig, PoolConfig
from pyasic.config.mining import MiningModeUnknown


def test_hashmaster_missing_work_mode_parses_as_unknown():
    conf = MiningModeConfig.from_hashmaster_am({}, None)
    assert isinstance(conf, MiningModeUnknown)


def test_hashmaster_empty_work_mode_parses_as_unknown():
    conf = MiningModeConfig.from_hashmaster_am({"bitmain-work-mode": ""}, None)
    assert isinstance(conf, MiningModeUnknown)


def test_hashmaster_sleep_still_parses_as_sleep():
    conf = MiningModeConfig.from_hashmaster_am(
        {"bitmain-work-mode": "1", "bitmain-ex-hashrate": "5400"}, None
    )
    assert conf.mode == "sleep"


def test_am_modern_missing_work_mode_parses_as_unknown():
    conf = MiningModeConfig.from_am_modern({})
    assert isinstance(conf, MiningModeUnknown)


def test_bitfufu_missing_work_mode_parses_as_unknown():
    conf = MiningModeConfig.from_bitfufuos_am({}, None)
    assert isinstance(conf, MiningModeUnknown)


def test_epic_missing_tuner_section_parses_as_unknown():
    conf = MiningModeConfig.from_epic({})
    assert isinstance(conf, MiningModeUnknown)


def test_vnish_missing_overclock_section_parses_as_unknown():
    conf = MiningModeConfig.from_vnish({}, [], {})
    assert isinstance(conf, MiningModeUnknown)


def test_mara_missing_mode_section_parses_as_unknown():
    conf = MiningModeConfig.from_mara({})
    assert isinstance(conf, MiningModeUnknown)


def test_auradine_missing_mode_parses_as_unknown():
    conf = MiningModeConfig.from_auradine({})
    assert isinstance(conf, MiningModeUnknown)


def test_auradine_unrecognized_mode_parses_as_unknown():
    conf = MiningModeConfig.from_auradine({"Mode": [{"Mode": "future-mode"}]})
    assert isinstance(conf, MiningModeUnknown)


def test_bosminer_tuner_disabled_still_parses_as_normal():
    conf = MiningModeConfig.from_bosminer({"autotuning": {"enabled": False}})
    assert conf.mode == "normal"


def test_unknown_round_trips_through_dict():
    conf = MiningModeConfig.from_dict({"mode": "unknown"})
    assert isinstance(conf, MiningModeUnknown)
    assert conf.as_dict()["mode"] == "unknown"


def test_unknown_serializes_to_empty_for_every_firmware():
    unknown = MiningModeConfig.unknown()
    assert unknown.as_hashmaster_am() == {}
    assert unknown.as_bitfufuos_am() == {}
    assert unknown.as_am_modern() == {}
    assert unknown.as_hiveon_modern() == {}
    assert unknown.as_elphapex() == {}
    assert unknown.as_wm() == {}
    assert unknown.as_epic() == {}
    assert unknown.as_auradine() == {}
    assert unknown.as_mara() == {}
    assert unknown.as_bosminer() == {}
    assert unknown.as_goldshell() == {}


def test_config_write_back_with_unknown_mode_keeps_mode_fields_absent():
    config = MinerConfig(
        pools=PoolConfig.simple(
            [
                {
                    "url": "stratum+tcp://stratum.test.io:3333",
                    "user": "test.worker",
                    "password": "x",
                }
            ]
        ),
        mining_mode=MiningModeConfig.unknown(),
    )
    payload = config.as_hashmaster_am()
    assert "miner-mode" not in payload
    assert "ex-hashrate" not in payload
    assert payload["pools"][0]["url"] == "stratum+tcp://stratum.test.io:3333"
