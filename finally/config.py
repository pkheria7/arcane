from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class WheelPins:
    enable: int
    forward: int
    backward: int


@dataclass(frozen=True)
class WheelCalibration:
    invert: bool = False
    trim: float = 1.0
    min_pwm: float = 0.28


@dataclass(frozen=True)
class VehiclePins:
    rear_left: WheelPins = WheelPins(enable=18, forward=17, backward=27)
    rear_right: WheelPins = WheelPins(enable=19, forward=22, backward=23)
    # Existing wiring has the front-left motor direction reversed in the old driver.
    front_left: WheelPins = WheelPins(enable=11, forward=8, backward=7)
    front_right: WheelPins = WheelPins(enable=12, forward=9, backward=10)
    servo: int = 20
    ir_left: int = 16
    ir_center: int = 6
    ir_right: int = 5
    ultrasonic_trig: int = 4
    ultrasonic_echo: int = 21


@dataclass(frozen=True)
class RuntimeConfig:
    host: str = "0.0.0.0"
    port: int = 8080
    control_hz: float = 14.0
    camera_hz: float = 3.0
    camera_width: int = 160
    camera_height: int = 120
    jpeg_quality: int = 35
    pin_factory: str = "auto"
    camera_enabled: bool = True


@dataclass(frozen=True)
class AutonomyConfig:
    cruise_pwm: float = 0.90
    avoid_pwm: float = 0.90
    reverse_pwm: float = 0.90
    pivot_pwm: float = 0.90
    recover_pwm: float = 0.90
    steering_deadzone: float = 0.08
    full_turn_threshold: float = 0.80
    slight_turn_min_inner_ratio: float = 0.20
    pivot_inner_reverse_ratio: float = 0.60
    close_distance_cm: float = 35.0
    emergency_distance_cm: float = 14.0
    clear_distance_cm: float = 45.0
    ultrasonic_close_samples: int = 3
    ultrasonic_clear_samples: int = 2
    blocked_stop_s: float = 0.25
    reverse_s: float = 0.55
    pivot_s: float = 0.55
    side_avoid_s: float = 0.35
    recover_s: float = 0.45
    hard_stop_s: float = 0.45
    safe_gap_score: float = 0.42
    scan_angles: tuple[int, int, int] = (180, 90, 0)
    scan_servo_settle_s: float = 0.45


@dataclass(frozen=True)
class AppConfig:
    pins: VehiclePins = field(default_factory=VehiclePins)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    autonomy: AutonomyConfig = field(default_factory=AutonomyConfig)
    wheel_calibration: dict[str, WheelCalibration] = field(
        default_factory=lambda: {
            "front_left": WheelCalibration(),
            "front_right": WheelCalibration(),
            "rear_left": WheelCalibration(),
            "rear_right": WheelCalibration(),
        }
    )
