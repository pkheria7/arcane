from __future__ import annotations

from dataclasses import dataclass
from time import sleep

from .gpio_factory import configure_gpiozero_pin_factory


class MotorDriver:
    def forward(self, speed: float) -> None: ...
    def left(self, speed: float) -> None: ...
    def right(self, speed: float) -> None: ...
    def drive(self, left_speed: float, right_speed: float) -> None: ...
    def stop(self) -> None: ...


class Servo:
    def set_angle(self, angle: int) -> None: ...


@dataclass
class SimulatedMotorDriver(MotorDriver):
    last_command: str = "stop"
    last_speed: float = 0.0
    last_left_speed: float = 0.0
    last_right_speed: float = 0.0

    def forward(self, speed: float) -> None:
        self.last_command, self.last_speed = "straight", speed
        self.last_left_speed, self.last_right_speed = speed, speed

    def left(self, speed: float) -> None:
        self.last_command, self.last_speed = "left", speed
        self.last_left_speed, self.last_right_speed = -speed, speed

    def right(self, speed: float) -> None:
        self.last_command, self.last_speed = "right", speed
        self.last_left_speed, self.last_right_speed = speed, -speed

    def drive(self, left_speed: float, right_speed: float) -> None:
        self.last_command = "drive"
        self.last_left_speed = max(-1.0, min(1.0, left_speed))
        self.last_right_speed = max(-1.0, min(1.0, right_speed))
        self.last_speed = max(abs(self.last_left_speed), abs(self.last_right_speed))

    def stop(self) -> None:
        self.last_command, self.last_speed = "stop", 0.0
        self.last_left_speed, self.last_right_speed = 0.0, 0.0


@dataclass
class SimulatedServo(Servo):
    angle: int = 0

    def set_angle(self, angle: int) -> None:
        self.angle = max(0, min(180, int(angle)))


class PiMotorDriver(MotorDriver):
    def __init__(
        self,
        ena: int,
        in1: int,
        in2: int,
        enb: int,
        in3: int,
        in4: int,
        front_ena: int | None = None,
        front_in1: int | None = None,
        front_in2: int | None = None,
        front_enb: int | None = None,
        front_in3: int | None = None,
        front_in4: int | None = None,
        pin_factory: str = "auto",
    ) -> None:
        configure_gpiozero_pin_factory(pin_factory)
        from gpiozero import DigitalOutputDevice, PWMOutputDevice

        self.ena = PWMOutputDevice(ena)
        self.enb = PWMOutputDevice(enb)
        self.in1 = DigitalOutputDevice(in1)
        self.in2 = DigitalOutputDevice(in2)
        self.in3 = DigitalOutputDevice(in3)
        self.in4 = DigitalOutputDevice(in4)

        self._has_front = front_ena is not None
        if self._has_front:
            self.front_ena = PWMOutputDevice(front_ena)
            self.front_enb = PWMOutputDevice(front_enb)
            self.front_in1 = DigitalOutputDevice(front_in1)
            self.front_in2 = DigitalOutputDevice(front_in2)
            self.front_in3 = DigitalOutputDevice(front_in3)
            self.front_in4 = DigitalOutputDevice(front_in4)

    def _set(self, left_forward: bool, right_forward: bool, speed: float) -> None:
        value = max(0.0, min(1.0, abs(speed)))
        self.in1.value = left_forward
        self.in2.value = not left_forward
        self.in3.value = right_forward
        self.in4.value = not right_forward
        self.ena.value = value
        self.enb.value = value
        if self._has_front:
            self.front_in1.value = not left_forward
            self.front_in2.value = left_forward
            self.front_in3.value = right_forward
            self.front_in4.value = not right_forward
            self.front_ena.value = value
            self.front_enb.value = value

    def _set_side(self, forward_pin, backward_pin, pwm, speed: float) -> None:
        value = max(-1.0, min(1.0, speed))
        forward_pin.value = value >= 0
        backward_pin.value = value < 0
        pwm.value = abs(value)

    def forward(self, speed: float) -> None:
        self._set(True, True, speed)

    def left(self, speed: float) -> None:
        self._set(False, True, speed)

    def right(self, speed: float) -> None:
        self._set(True, False, speed)

    def drive(self, left_speed: float, right_speed: float) -> None:
        self._set_side(self.in1, self.in2, self.ena, left_speed)
        self._set_side(self.in3, self.in4, self.enb, right_speed)
        if self._has_front:
            self._set_side(self.front_in2, self.front_in1, self.front_ena, left_speed)
            self._set_side(self.front_in3, self.front_in4, self.front_enb, right_speed)

    def stop(self) -> None:
        self.ena.value = 0
        self.enb.value = 0
        self.in1.off()
        self.in2.off()
        self.in3.off()
        self.in4.off()
        if self._has_front:
            self.front_ena.value = 0
            self.front_enb.value = 0
            self.front_in1.off()
            self.front_in2.off()
            self.front_in3.off()
            self.front_in4.off()


class PiServo(Servo):
    def __init__(self, pin: int, min_pulse_width: float = 0.0005, max_pulse_width: float = 0.0025, pin_factory: str = "auto") -> None:
        configure_gpiozero_pin_factory(pin_factory)
        from gpiozero import AngularServo

        self.servo = AngularServo(pin, min_angle=0, max_angle=180, min_pulse_width=min_pulse_width, max_pulse_width=max_pulse_width)
        self.angle = 0
        self.servo.angle = 0
        sleep(0.05)
        print("[edge] servo -> 0 front", flush=True)

    def set_angle(self, angle: int) -> None:
        next_angle = max(0, min(180, int(angle)))
        if next_angle == self.angle:
            return
        self.angle = next_angle
        self.servo.angle = next_angle
        label = "front" if next_angle == 0 else "left" if next_angle == 90 else "right" if next_angle == 180 else "scan"
        print(f"[edge] servo -> {next_angle} {label}", flush=True)
        sleep(0.05)
