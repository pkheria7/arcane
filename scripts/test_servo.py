from __future__ import annotations

from time import sleep

from sensor_layer.actuators import PiServo


def main() -> None:
    servo = PiServo(pin=20, pin_factory="lgpio")
    try:
        while True:
            servo.set_angle(90)
            print("Front")
            sleep(2)

            servo.set_angle(180)
            print("Left side")
            sleep(2)

            servo.set_angle(0)
            print("Right side")
            sleep(2)
    except KeyboardInterrupt:
        try:
            servo.servo.detach()
        except Exception:
            pass
        print("\nStopped.")


if __name__ == "__main__":
    main()
