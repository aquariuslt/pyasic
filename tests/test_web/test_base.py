from pyasic.web.base import normalize_wattage_value


def test_normalize_wattage_value_handles_supported_formats():
    assert normalize_wattage_value("miner power:1234") == 1234
    assert normalize_wattage_value("1234") == 1234
    assert normalize_wattage_value(1234) == 1234


def test_normalize_wattage_value_rejects_invalid_values():
    assert normalize_wattage_value(None) is None
    assert normalize_wattage_value("miner power:abc") is None
    assert normalize_wattage_value("abc") is None
