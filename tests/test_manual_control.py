from dataset.manual_recorder import ManualCommandState, derived_action
from rpi_edge.client import steering_to_motor_mix


def test_derived_action_from_continuous_steering():
    assert derived_action(-1.0, False) == "full_left"
    assert derived_action(-0.4, False) == "slight_left"
    assert derived_action(0.0, False) == "straight"
    assert derived_action(0.4, False) == "slight_right"
    assert derived_action(1.0, False) == "full_right"
    assert derived_action(0.0, True) == "stop"
    assert derived_action(0.0, False, "reverse") == "reverse_straight"
    assert derived_action(-0.8, False, "reverse") == "reverse_full_left"


def test_manual_command_normalizes_to_supported_modes():
    command = ManualCommandState(speed_cm_s=3.3, steering=2.0, direction="backward", servo_angle=120, stop=False).normalized()
    assert command.speed_cm_s == 3.0
    assert command.steering == 1.0
    assert command.direction == "forward"
    assert command.servo_angle == 120


def test_steering_to_motor_mix():
    assert steering_to_motor_mix(0.6, 0.0, "forward") == (0.6, 0.6)
    assert steering_to_motor_mix(0.6, 0.0, "reverse") == (-0.6, -0.6)
    assert steering_to_motor_mix(0.6, -1.0, "forward") == (-0.24, 0.6)
    assert steering_to_motor_mix(0.6, 1.0, "forward") == (0.6, -0.24)
    assert steering_to_motor_mix(0.6, -1.0, "reverse") == (0.24, -0.6)


def test_slight_turn_reduces_inner_tire_aggressively():
    left, right = steering_to_motor_mix(0.8, -0.45, "forward")
    assert left <= 0.45
    assert right == 0.8


def test_full_turn_threshold_pivots_from_button_value():
    left, right = steering_to_motor_mix(1.0, -1.0, "forward")
    assert left < 0
    assert right == 1.0

    left, right = steering_to_motor_mix(1.0, 1.0, "forward")
    assert left == 1.0
    assert right < 0
