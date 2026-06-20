from navigation_ai.actions import Action, ReasonCode
from navigation_ai.expert_controller import ExpertController
from sensor_layer.types import SensorFrame


def frame(**updates):
    data = SensorFrame.empty().__dict__ | updates
    return SensorFrame(**data)


def test_emergency_stop_overrides_everything():
    decision = ExpertController().decide(frame(ir_center=1, ultrasonic_distance=5.0))
    assert decision.action == Action.STOP
    assert decision.reason_code == ReasonCode.EMERGENCY_STOP


def test_left_obstacle_prefers_straight_and_avoids_left():
    decision = ExpertController().decide(frame(ir_left=1))
    assert decision.action == Action.STRAIGHT
    assert decision.reason_code == ReasonCode.LEFT_OBSTACLE
    assert decision.probabilities["straight"] > decision.probabilities["left"]


def test_center_obstacle_selects_safest_gap():
    decision = ExpertController().decide(frame(ir_center=1, left_gap_score=0.2, right_gap_score=0.8))
    assert decision.action == Action.RIGHT
    assert decision.reason_code == ReasonCode.FRONT_OBSTACLE_RIGHT_GAP


def test_center_obstacle_stops_when_no_safe_path_exists():
    decision = ExpertController().decide(frame(ir_center=1, left_gap_score=0.1, right_gap_score=0.2))
    assert decision.action == Action.STOP
    assert decision.reason_code == ReasonCode.NO_SAFE_PATH
