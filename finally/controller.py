from __future__ import annotations

from dataclasses import dataclass
from time import time

from .config import AutonomyConfig
from .models import Decision, SensorSnapshot
from .motors import command_all, differential_mix, pivot


@dataclass
class RuleController:
    config: AutonomyConfig
    state: str = "drive"
    state_start: float = 0.0
    turn_direction: int = 1
    close_count: int = 0
    clear_count: int = 0
    last_reason: str = "Starting."

    def update(self, sensors: SensorSnapshot, emergency_stop: bool = False, now: float | None = None) -> Decision:
        now = time() if now is None else now
        if self.state_start == 0.0:
            self.state_start = now

        self._update_filters(sensors)
        front_blocked = self._front_blocked(sensors)
        true_emergency = bool(sensors.ir_center) or sensors.ultrasonic_cm <= self.config.emergency_distance_cm

        if emergency_stop:
            self.state = "hard_stop"
            self.state_start = now
            return self._decision("hard_stop", "Emergency stop requested from UI.", stop=True)

        if self.state == "drive":
            if true_emergency:
                self._enter("hard_stop", now, "Immediate front danger.")
            elif front_blocked:
                self._enter("blocked_stop", now, "Front blocked; pausing before scan.")
            elif sensors.ir_left:
                self.turn_direction = 1
                self._enter("avoid_side", now, "Left IR obstacle; steering right.")
            elif sensors.ir_right:
                self.turn_direction = -1
                self._enter("avoid_side", now, "Right IR obstacle; steering left.")

        elif self.state == "hard_stop":
            if self._elapsed(now) >= self.config.hard_stop_s:
                self._enter("scan", now, "Hard stop complete; scanning for escape.")

        elif self.state == "blocked_stop":
            if self._elapsed(now) >= self.config.blocked_stop_s:
                self._enter("scan", now, "Stop complete; scanning for best gap.")

        elif self.state == "scan":
            self.turn_direction = self._choose_turn_direction(sensors)
            if front_blocked:
                self._enter("reverse", now, "Front still blocked; reversing before pivot.")
            else:
                self._enter("pivot", now, "Path partly clear; pivoting toward safer side.")

        elif self.state == "reverse":
            if self._elapsed(now) >= self.config.reverse_s:
                self._enter("pivot", now, "Reverse complete; pivoting away.")

        elif self.state == "pivot":
            if self._elapsed(now) >= self.config.pivot_s:
                self._enter("recover", now, "Pivot complete; recovering forward.")

        elif self.state == "avoid_side":
            if true_emergency or front_blocked:
                self._enter("blocked_stop", now, "Side avoid interrupted by front block.")
            elif self._elapsed(now) >= self.config.side_avoid_s:
                self._enter("recover", now, "Side obstacle avoided.")

        elif self.state == "recover":
            if true_emergency:
                self._enter("hard_stop", now, "Danger during recovery.")
            elif front_blocked:
                self._enter("blocked_stop", now, "Recovery still blocked; retrying.")
            elif self._elapsed(now) >= self.config.recover_s:
                self._enter("drive", now, "Clear enough; cruising.")

        return self._command_for_state(sensors)

    def _update_filters(self, sensors: SensorSnapshot) -> None:
        if sensors.ultrasonic_cm <= self.config.close_distance_cm:
            self.close_count += 1
            self.clear_count = 0
        elif sensors.ultrasonic_cm >= self.config.clear_distance_cm:
            self.clear_count += 1
            if self.clear_count >= self.config.ultrasonic_clear_samples:
                self.close_count = 0

    def _front_blocked(self, sensors: SensorSnapshot) -> bool:
        camera_blocked = sensors.camera_ok and sensors.center_gap < self.config.safe_gap_score
        ultrasonic_blocked = self.close_count >= self.config.ultrasonic_close_samples
        return bool(sensors.ir_center) or ultrasonic_blocked or camera_blocked

    def _choose_turn_direction(self, sensors: SensorSnapshot) -> int:
        if sensors.ir_left and not sensors.ir_right:
            return 1
        if sensors.ir_right and not sensors.ir_left:
            return -1
        return -1 if sensors.left_gap >= sensors.right_gap else 1

    def _elapsed(self, now: float) -> float:
        return now - self.state_start

    def _enter(self, state: str, now: float, reason: str) -> None:
        if self.state != state:
            self.state = state
            self.state_start = now
        self.last_reason = reason

    def _decision(self, state: str, reason: str, stop: bool = False) -> Decision:
        command = command_all(0.0, "stop") if stop else command_all(self.config.cruise_pwm, "drive")
        return Decision(state=state, reason=reason, command=command)

    def _command_for_state(self, sensors: SensorSnapshot) -> Decision:
        cfg = self.config
        if self.state == "hard_stop":
            return Decision("hard_stop", self.last_reason, command_all(0.0, "stop"), scan_active=False)
        if self.state == "blocked_stop":
            return Decision("blocked_stop", self.last_reason, command_all(0.0, "stop"), scan_active=True)
        if self.state == "scan":
            return Decision("scan", self.last_reason, command_all(0.0, "scan_stop"), scan_active=True)
        if self.state == "reverse":
            return Decision("reverse", self.last_reason, command_all(-cfg.reverse_pwm, "reverse"), turn_direction=self.turn_direction)
        if self.state == "pivot":
            return Decision("pivot", self.last_reason, pivot(self.turn_direction, cfg.pivot_pwm), turn_direction=self.turn_direction)
        if self.state == "avoid_side":
            steering = 0.65 if self.turn_direction > 0 else -0.65
            return Decision(
                "avoid_side",
                self.last_reason,
                differential_mix(cfg.avoid_pwm, steering, label="avoid_side"),
                turn_direction=self.turn_direction,
            )
        if self.state == "recover":
            return Decision("recover", self.last_reason, command_all(cfg.recover_pwm, "recover"), turn_direction=self.turn_direction)
        return Decision("drive", self.last_reason, command_all(cfg.cruise_pwm, "drive"), servo_angle=sensors.servo_angle)

