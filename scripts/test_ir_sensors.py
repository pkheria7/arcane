from __future__ import annotations

from time import sleep

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


def status(sensor: DigitalInputDevice, active_low: bool) -> str:
    blocked = sensor.value == (0 if active_low else 1)
    return "OBSTACLE" if blocked else "clear"


def main() -> None:
    print("Reading IR sensors. Press Ctrl+C to stop.")
    print("Runtime polarity: left=active-high, centre=active-high, right=active-low")
    try:
        while True:
            print(
                f"Left: {status(left_ir, active_low=False):8s} | "
                f"Centre: {status(center_ir, active_low=False):8s} | "
                f"Right: {status(right_ir, active_low=True):8s}"
            )
            sleep(0.3)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
