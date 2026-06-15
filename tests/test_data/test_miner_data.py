from pyasic.data import HashBoard, MinerData
from pyasic.data.device import DeviceInfo


def test_miner_data_influxdb_includes_temperature_inlet_outlet_averages():
    miner_data = MinerData(
        ip="10.0.0.1",
        device_info=DeviceInfo(),
        hashboards=[
            HashBoard(temp=50, inlet_temp=30, outlet_temp=60),
            HashBoard(temp=60, inlet_temp=40, outlet_temp=70),
        ],
    )

    line_protocol = miner_data.as_influxdb()

    assert "temperature_avg=55" in line_protocol
    assert "temperature_inlet_avg=35.0" in line_protocol
    assert "temperature_outlet_avg=65.0" in line_protocol
