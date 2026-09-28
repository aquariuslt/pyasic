import pytest

from pyasic.data.pools import PoolMetrics


@pytest.mark.parametrize(
    "accepted, rejected, failures, rejected_percent, stale_percent",
    [
        (None, None, None, 0, 0),
        (None, 2, 1, 0, 0),
        (8, None, 1, 0, 0),
        (0, 0, 0, 0, 0),
        (8, 2, None, 20, 0),
        (8, 2, 1, 20, 10),
    ],
)
def test_nullable_pool_counters_serialize(
    accepted, rejected, failures, rejected_percent, stale_percent
):
    pool = PoolMetrics(
        url=None,
        accepted=accepted,
        rejected=rejected,
        get_failures=failures,
        alive=True,
        active=True,
    )
    data = pool.model_dump(mode="json")
    assert data["accepted"] == accepted and data["rejected"] == rejected
    assert data["alive"] is True and data["active"] is True
    assert data["pool_rejected_percent"] == rejected_percent
    assert data["pool_stale_percent"] == stale_percent
    assert pool.model_dump_json()
