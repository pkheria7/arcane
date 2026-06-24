from rpi_edge.client import LocalAutonomy, steering_to_motor_mix
from sensor_layer.types import SensorFrame


def frame(**updates):
    data = SensorFrame.empty().__dict__ | updates
    # Neutral gap scores so default frames do not trigger false front-blocked checks.
    data["left_gap_score"] = data.get("left_gap_score", 0.0) or 0.5
    data["center_gap_score"] = data.get("center_gap_score", 0.0) or 0.5
    data["right_gap_score"] = data.get("right_gap_score", 0.0) or 0.5
    return SensorFrame(**data)


def test_local_autonomy_stops_on_center_ir():
    auto = LocalAutonomy()
    cmd = auto.decide(frame(ir_center=1, ultrasonic_distance=80.0))
    assert cmd["stop"] is True


def test_local_autonomy_turns_away_from_left_ir():
    auto = LocalAutonomy()
    cmd = auto.decide(frame(ir_left=1, ultrasonic_distance=80.0))
    assert cmd["steering"] > 0
    assert cmd["action"] == "right"


def test_local_autonomy_turns_away_from_right_ir():
    auto = LocalAutonomy()
    cmd = auto.decide(frame(ir_right=1, ultrasonic_distance=80.0))
    assert cmd["steering"] < 0
    assert cmd["action"] == "left"


def test_local_autonomy_drives_straight_when_clear():
    auto = LocalAutonomy()
    cmd = auto.decide(frame(ultrasonic_distance=80.0))
    assert cmd["action"] == "straight"
    assert cmd["steering"] == 0.0
    assert cmd["speed_cm_s"] > 0


def test_local_autonomy_chooses_gap_direction_for_front_obstacle():
    auto = LocalAutonomy()
    # Front blocked (ultrasonic in 15-40 cm range) but not an emergency.
    # Right side has more space -> turn right.
    cmd = auto.decide(
        frame(ultrasonic_distance=30.0, left_gap_score=0.1, right_gap_score=0.8)
    )
    assert cmd["stop"] is True
    # Simulate next cycle in stop_scan -> should transition to turn.
    cmd = auto.decide(
        frame(ultrasonic_distance=30.0, left_gap_score=0.1, right_gap_score=0.8)
    )
    assert cmd["action"] == "right"
    assert cmd["steering"] > 0


def test_steering_pivot_is_softened():
    left, right = steering_to_motor_mix(1.0, -1.0, "forward")
    assert left == -0.40
    assert right == 1.0
