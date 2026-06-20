from __future__ import annotations

from dataclasses import dataclass
from time import sleep, time

from .system_packages import add_system_dist_packages


@dataclass(frozen=True)
class UltrasonicReading:
    distance_cm: float | None
    error: str | None = None


class UltrasonicSensor:
    def measure(self) -> UltrasonicReading: ...
    def close(self) -> None: ...


class NullUltrasonicSensor(UltrasonicSensor):
    def measure(self) -> UltrasonicReading:
        return UltrasonicReading(distance_cm=999.0)

    def close(self) -> None:
        return


class LgpioUltrasonicSensor(UltrasonicSensor):
    """HC-SR04 reader using raw lgpio timing.

    Pins are BCM GPIO numbers. Echo must be level-shifted to 3.3V before it
    reaches the Raspberry Pi.
    """

    def __init__(self, trig: int, echo: int, chip: int = 0, timeout_s: float = 0.05) -> None:
        add_system_dist_packages()
        import lgpio

        self.lgpio = lgpio
        self.trig = trig
        self.echo = echo
        self.timeout_s = timeout_s
        self.handle = lgpio.gpiochip_open(chip)
        lgpio.gpio_claim_output(self.handle, trig, 0)
        lgpio.gpio_claim_input(self.handle, echo)

    def measure(self) -> UltrasonicReading:
        self.lgpio.gpio_write(self.handle, self.trig, 1)
        sleep(0.00001)
        self.lgpio.gpio_write(self.handle, self.trig, 0)

        deadline = time() + self.timeout_s
        while self.lgpio.gpio_read(self.handle, self.echo) == 0:
            if time() > deadline:
                return UltrasonicReading(None, "NO_RESPONSE_ECHO_NEVER_HIGH")

        start = time()
        deadline = time() + self.timeout_s
        while self.lgpio.gpio_read(self.handle, self.echo) == 1:
            if time() > deadline:
                return UltrasonicReading(None, "STUCK_HIGH_ECHO_NEVER_LOW")

        duration = time() - start
        cm = (duration * 34300.0) / 2.0
        return UltrasonicReading(distance_cm=cm)

    def close(self) -> None:
        try:
            self.lgpio.gpiochip_close(self.handle)
        except Exception:
            return
