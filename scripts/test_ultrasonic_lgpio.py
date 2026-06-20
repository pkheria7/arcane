from __future__ import annotations

from time import sleep

from sensor_layer.ultrasonic import LgpioUltrasonicSensor

TRIG = 4
ECHO = 21
WARN_CM = 40
STOP_CM = 20


def tag(cm: float) -> str:
    if cm < STOP_CM:
        return "!! TOO CLOSE !!"
    if cm < WARN_CM:
        return "CLOSE"
    return "clear"


def main() -> None:
    sensor = LgpioUltrasonicSensor(trig=TRIG, echo=ECHO)
    print(f"Ultrasonic test  |  STOP threshold: {STOP_CM}cm  |  WARN: {WARN_CM}cm")
    print("Point sensor at objects at different distances. Ctrl+C to stop.\n")
    try:
        while True:
            reading = sensor.measure()
            if reading.error:
                print(f"ERROR: {reading.error}")
            else:
                cm = reading.distance_cm or 999.0
                bar = "#" * int(cm / 5)
                print(f"{cm:6.1f} cm  {tag(cm):16s}  |{bar}")
            sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        sensor.close()


if __name__ == "__main__":
    main()
