from __future__ import annotations

import argparse
from time import sleep

from .config import AppConfig
from .motors import FourMotorDriver, MotorCommand, command_all, pivot


def pulse(driver: FourMotorDriver, command: MotorCommand, seconds: float) -> None:
    print(f"[motor-test] {command.label}: {command}", flush=True)
    driver.apply(command)
    sleep(seconds)
    driver.stop()
    sleep(0.5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Test four ARCANE motors with wheels lifted.")
    parser.add_argument("--pwm", type=float, default=0.35)
    parser.add_argument("--seconds", type=float, default=1.0)
    args = parser.parse_args()

    driver = FourMotorDriver(AppConfig())
    p = args.pwm
    try:
        pulse(driver, MotorCommand(front_left=p, label="front_left"), args.seconds)
        pulse(driver, MotorCommand(front_right=p, label="front_right"), args.seconds)
        pulse(driver, MotorCommand(rear_left=p, label="rear_left"), args.seconds)
        pulse(driver, MotorCommand(rear_right=p, label="rear_right"), args.seconds)
        pulse(driver, MotorCommand(front_left=p, rear_left=p, label="left_side"), args.seconds)
        pulse(driver, MotorCommand(front_right=p, rear_right=p, label="right_side"), args.seconds)
        pulse(driver, command_all(p, "forward_all"), args.seconds)
        pulse(driver, command_all(-p, "reverse_all"), args.seconds)
        pulse(driver, pivot(-1, p, "pivot"), args.seconds)
        pulse(driver, pivot(1, p, "pivot"), args.seconds)
    finally:
        driver.stop()


if __name__ == "__main__":
    main()

