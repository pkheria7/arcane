from __future__ import annotations

import sys
from pathlib import Path
from time import sleep

# Allow running this script directly from the scripts/ directory.
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from sensor_layer.gpio_factory import configure_gpiozero_pin_factory

configure_gpiozero_pin_factory("lgpio")

from gpiozero import DigitalInputDevice

# Physical left/right IR sensors are swapped relative to the layout image.
LEFT_PIN = 16
CENTER_PIN = 6
RIGHT_PIN = 5

left_ir = DigitalInputDevice(LEFT_PIN, pull_up=True)
center_ir = DigitalInputDevice(CENTER_PIN, pull_up=True)
right_ir = DigitalInputDevice(RIGHT_PIN, pull_up=True)


def interpret(raw_value: int, active_low: bool) -> str:
    blocked = raw_value == (0 if active_low else 1)
    return "BLOCKED" if blocked else "clear"


def main() -> None:
    print("IR polarity diagnostic")
    print("Move your hand near ONE sensor at a time and watch which column changes.")
    print("Columns show raw GPIO value + blocked interpretation for both polarities.")
    print("Press Ctrl+C to stop.\n")
    print(
        f"{'LEFT':>18} | {'CENTER':>18} | {'RIGHT':>18}"
    )
    print(
        f"{'raw | high block | low block':>18} | "
        f"{'raw | high block | low block':>18} | "
        f"{'raw | high block | low block':>18}"
    )
    print("-" * 60)
    try:
        while True:
            left_raw = int(left_ir.value)
            center_raw = int(center_ir.value)
            right_raw = int(right_ir.value)
            print(
                f"{left_raw:>3} | {interpret(left_raw, active_low=False):>10} | {interpret(left_raw, active_low=True):>9} | "
                f"{center_raw:>3} | {interpret(center_raw, active_low=False):>10} | {interpret(center_raw, active_low=True):>9} | "
                f"{right_raw:>3} | {interpret(right_raw, active_low=False):>10} | {interpret(right_raw, active_low=True):>9}"
            )
            sleep(0.3)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
