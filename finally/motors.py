from __future__ import annotations

from dataclasses import dataclass
from time import sleep

from .config import AppConfig, WheelCalibration, WheelPins
from .models import MotorCommand


WHEEL_NAMES = ("front_left", "front_right", "rear_left", "rear_right")


def clamp_pwm(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))


def apply_deadband(value: float, min_pwm: float) -> float:
    value = clamp_pwm(value)
    if value == 0.0:
        return 0.0
    sign = 1.0 if value > 0 else -1.0
    return sign * max(abs(value), min_pwm)


def differential_mix(
    throttle: float,
    steering: float,
    *,
    deadzone: float = 0.08,
    full_turn_threshold: float = 0.72,
    slight_turn_min_inner_ratio: float = 0.28,
    pivot_inner_reverse_ratio: float = 0.55,
    label: str = "drive",
) -> MotorCommand:
    base = max(0.0, min(1.0, abs(float(throttle))))
    direction = 1.0 if throttle >= 0 else -1.0
    turn = clamp_pwm(steering)
    magnitude = abs(turn)

    if magnitude < deadzone:
        left = right = base
    elif magnitude >= full_turn_threshold:
        if turn < 0:
            left, right = -pivot_inner_reverse_ratio * base, base
        else:
            left, right = base, -pivot_inner_reverse_ratio * base
    else:
        span = max(0.01, full_turn_threshold - deadzone)
        reduction = 1.0 - (magnitude - deadzone) / span * (1.0 - slight_turn_min_inner_ratio)
        inner = base * max(slight_turn_min_inner_ratio, reduction)
        if turn < 0:
            left, right = inner, base
        else:
            left, right = base, inner

    left *= direction
    right *= direction
    return MotorCommand(
        front_left=left,
        rear_left=left,
        front_right=right,
        rear_right=right,
        label=label,
    )


def command_all(value: float, label: str) -> MotorCommand:
    value = clamp_pwm(value)
    return MotorCommand(value, value, value, value, label=label)


def pivot(direction: int, pwm: float, label: str = "pivot") -> MotorCommand:
    pwm = max(0.0, min(1.0, pwm))
    if direction < 0:
        return MotorCommand(-pwm, pwm, -pwm, pwm, label=f"{label}_left")
    return MotorCommand(pwm, -pwm, pwm, -pwm, label=f"{label}_right")


@dataclass
class SimulatedFourMotorDriver:
    last_command: MotorCommand = MotorCommand()

    def apply(self, command: MotorCommand) -> None:
        self.last_command = command

    def stop(self) -> None:
        self.apply(MotorCommand())


class FourMotorDriver:
    def __init__(self, config: AppConfig) -> None:
        from sensor_layer.gpio_factory import configure_gpiozero_pin_factory

        configure_gpiozero_pin_factory(config.runtime.pin_factory)
        from gpiozero import DigitalOutputDevice, PWMOutputDevice

        self.calibration = config.wheel_calibration
        pins = config.pins
        self.wheels = {
            "front_left": self._open_wheel(pins.front_left, DigitalOutputDevice, PWMOutputDevice),
            "front_right": self._open_wheel(pins.front_right, DigitalOutputDevice, PWMOutputDevice),
            "rear_left": self._open_wheel(pins.rear_left, DigitalOutputDevice, PWMOutputDevice),
            "rear_right": self._open_wheel(pins.rear_right, DigitalOutputDevice, PWMOutputDevice),
        }

    def _open_wheel(self, pins: WheelPins, output_cls, pwm_cls) -> dict:
        return {
            "pwm": pwm_cls(pins.enable),
            "forward": output_cls(pins.forward),
            "backward": output_cls(pins.backward),
        }

    def apply(self, command: MotorCommand) -> None:
        for name in WHEEL_NAMES:
            self._set_wheel(name, getattr(command, name))

    def _set_wheel(self, name: str, raw_value: float) -> None:
        cal: WheelCalibration = self.calibration[name]
        value = clamp_pwm(raw_value) * cal.trim
        if cal.invert:
            value = -value
        value = apply_deadband(value, cal.min_pwm)
        wheel = self.wheels[name]
        wheel["forward"].value = value > 0
        wheel["backward"].value = value < 0
        wheel["pwm"].value = abs(clamp_pwm(value))

    def stop(self) -> None:
        self.apply(MotorCommand())
        sleep(0.02)

