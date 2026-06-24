from __future__ import annotations

from dataclasses import dataclass

from sensor_layer.types import SensorFrame

from .actions import Action, ReasonCode


@dataclass(frozen=True)
class NavigationConfig:
    constant_speed: float = 0.42
    turn_speed: float = 0.36
    emergency_distance_cm: float = 40.0
    safe_gap_threshold: float = 0.35
    center_scan_angles: tuple[int, ...] = (-60, -30, 0, 30, 60)


@dataclass(frozen=True)
class Decision:
    action: Action
    reason_code: ReasonCode
    speed: float
    probabilities: dict[str, float]
    second_best_action: Action
    explanation: str


class ExpertController:
    def __init__(self, config: NavigationConfig | None = None) -> None:
        self.config = config or NavigationConfig()

    def decide(self, frame: SensorFrame) -> Decision:
        if frame.ultrasonic_distance < self.config.emergency_distance_cm:
            return self._decision(Action.STOP, ReasonCode.EMERGENCY_STOP, 1.0, "Ultrasonic distance is below the emergency threshold.")

        if frame.ir_center:
            left_score = max(frame.left_gap_score, 0.0)
            right_score = max(frame.right_gap_score, 0.0)
            if left_score < self.config.safe_gap_threshold and right_score < self.config.safe_gap_threshold:
                return self._decision(Action.STOP, ReasonCode.NO_SAFE_PATH, 0.9, "Front obstacle detected and neither side has sufficient free space.")
            if left_score >= right_score:
                confidence = min(0.95, 0.55 + left_score * 0.4)
                return self._decision(Action.LEFT, ReasonCode.FRONT_OBSTACLE_LEFT_GAP, confidence, "Front obstacle detected; left scan has the safest bypass gap.")
            confidence = min(0.95, 0.55 + right_score * 0.4)
            return self._decision(Action.RIGHT, ReasonCode.FRONT_OBSTACLE_RIGHT_GAP, confidence, "Front obstacle detected; right scan has the safest bypass gap.")

        if frame.ir_left:
            return self._decision(Action.STRAIGHT, ReasonCode.LEFT_OBSTACLE, 0.72, "Left obstacle detected; avoiding left turn and preferring straight.")

        if frame.ir_right:
            return self._decision(Action.STRAIGHT, ReasonCode.RIGHT_OBSTACLE, 0.72, "Right obstacle detected; avoiding right turn and preferring straight.")

        return self._decision(Action.STRAIGHT, ReasonCode.CLEAR_PATH, 0.82, "No immediate obstacle detected; continuing at constant speed.")

    def _decision(self, action: Action, reason: ReasonCode, confidence: float, explanation: str) -> Decision:
        base = {Action.LEFT.value: 0.08, Action.STRAIGHT.value: 0.08, Action.RIGHT.value: 0.08, Action.STOP.value: 0.08}
        base[action.value] = confidence
        remainder = max(0.0, 1.0 - confidence)
        others = [name for name in base if name != action.value]
        for name in others:
            base[name] = remainder / len(others)
        ranked = sorted(base.items(), key=lambda item: item[1], reverse=True)
        speed = 0.0 if action == Action.STOP else (self.config.constant_speed if action == Action.STRAIGHT else self.config.turn_speed)
        return Decision(action=action, reason_code=reason, speed=speed, probabilities=base, second_best_action=Action(ranked[1][0]), explanation=explanation)
