from pyasic.config import MinerConfig
from pyasic.config.mining import MiningModeHashrateTune, MiningModeSleep

SAVED_CONFIG = {
    "general": {"cooling_mode": "air"},
    "mode": {
        "work_mode": "tuning",
        "fixed": {"frequency_mhz": 490, "voltage_v": 14.3},
        "tuning": {"target_hashrate_ths": 270},
    },
    "pools": [
        {"url": "stratum+tcp://a.example:3333", "user": "acct.w1", "pass": "root"},
        {"url": "stratum+tcp://b.example:3333", "worker": "acct.w2", "password": ""},
        {"enabled": False},
    ],
}


def _pools(config):
    return [
        (pool.url, pool.user, pool.password)
        for pool in MinerConfig.from_sdminer(config, None).pools.groups[0].pools
    ]


def test_pools_accept_worker_and_password_aliases():
    assert _pools(SAVED_CONFIG)[1] == ("stratum+tcp://b.example:3333", "acct.w2", "x")


def test_disabled_pool_slot_is_left_out():
    assert len(_pools(SAVED_CONFIG)) == 2


def test_saved_mode_is_used_when_the_mode_in_effect_is_unknown():
    mode = MinerConfig.from_sdminer(SAVED_CONFIG, None).mining_mode

    assert (type(mode), mode.hashrate) == (MiningModeHashrateTune, 270)


def test_mode_in_effect_wins_over_the_saved_mode():
    mode = MinerConfig.from_sdminer(SAVED_CONFIG, "sleep").mining_mode

    assert type(mode) is MiningModeSleep


def test_config_without_pools_has_no_pool_groups():
    assert MinerConfig.from_sdminer({}, "stock").pools.groups == []
