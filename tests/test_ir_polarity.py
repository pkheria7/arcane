from sensor_layer.sensors import IR_ACTIVE_LOW


def test_ir_polarity_matches_vehicle_modules():
    assert IR_ACTIVE_LOW["left"] is False
    assert IR_ACTIVE_LOW["center"] is False
    assert IR_ACTIVE_LOW["right"] is True
