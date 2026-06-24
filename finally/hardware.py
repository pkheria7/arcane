from __future__ import annotations

import random
from time import sleep, time

from .config import AppConfig
from .models import SensorSnapshot
from .vision import score_jpeg


IR_ACTIVE_LOW = {"left": False, "center": False, "right": True}


class SimulatedHardware:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.tick = 0
        self.servo_angle = 90
        self.latest_jpeg: bytes | None = None

    def read_sensors(self) -> SensorSnapshot:
        self.tick += 1
        # Periodically exercise the blocked escape path in simulation.
        front_block = 30 <= self.tick % 90 <= 46
        left = 1 if self.tick % 71 in (20, 21, 22, 23) else 0
        right = 1 if self.tick % 83 in (40, 41, 42, 43) else 0
        distance = 18.0 if front_block else random.uniform(55.0, 140.0)
        gaps = score_jpeg(self.latest_jpeg)
        return SensorSnapshot(
            timestamp=time(),
            ir_left=left,
            ir_center=int(front_block),
            ir_right=right,
            ultrasonic_cm=distance,
            servo_angle=self.servo_angle,
            camera_ok=gaps.ok,
            left_gap=gaps.left,
            center_gap=0.2 if front_block else gaps.center,
            right_gap=gaps.right,
            gps_lat=28.6139 + self.tick * 0.000001,
            gps_lon=77.2090 + self.tick * 0.000001,
            gps_fix_quality=1,
        )

    def capture_camera(self) -> bytes | None:
        try:
            import cv2
            import numpy as np

            img = np.zeros((self.config.runtime.camera_height, self.config.runtime.camera_width, 3), dtype=np.uint8)
            img[:, :, 1] = 72
            ok, encoded = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), self.config.runtime.jpeg_quality])
            self.latest_jpeg = encoded.tobytes() if ok else None
            return self.latest_jpeg
        except Exception:
            self.latest_jpeg = None
            return None

    def set_servo(self, angle: int) -> None:
        self.servo_angle = max(0, min(180, int(angle)))

    def close(self) -> None:
        return


class PiHardware:
    def __init__(self, config: AppConfig) -> None:
        from sensor_layer.gpio_factory import configure_gpiozero_pin_factory

        configure_gpiozero_pin_factory(config.runtime.pin_factory)
        from gpiozero import AngularServo, DigitalInputDevice
        from sensor_layer.gps import NullGpsReader, SerialGpsReader
        from sensor_layer.imu import Mpu6050Reader, NullImuReader
        from sensor_layer.ultrasonic import LgpioUltrasonicSensor, NullUltrasonicSensor

        self.config = config
        pins = config.pins
        self.left_ir = DigitalInputDevice(pins.ir_left, pull_up=True)
        self.center_ir = DigitalInputDevice(pins.ir_center, pull_up=True)
        self.right_ir = DigitalInputDevice(pins.ir_right, pull_up=True)
        try:
            self.ultrasonic = LgpioUltrasonicSensor(pins.ultrasonic_trig, pins.ultrasonic_echo)
        except Exception:
            self.ultrasonic = NullUltrasonicSensor()
        try:
            self.imu = Mpu6050Reader()
        except Exception:
            self.imu = NullImuReader()
        try:
            # Keep GPS reads short so the autonomy loop is never slowed by UART waits.
            self.gps = SerialGpsReader(timeout=0.005)
        except Exception:
            self.gps = NullGpsReader()
        self.last_gps_lat: float | None = None
        self.last_gps_lon: float | None = None
        self.last_gps_fix_quality = 0
        self.last_gps_fix_time: float | None = None
        self.next_gps_poll = 0.0

        self.servo = AngularServo(pins.servo, min_angle=0, max_angle=180, min_pulse_width=0.0005, max_pulse_width=0.0025)
        self.servo_angle = 90
        self.servo.angle = 90
        sleep(0.2)

        self.camera = None
        if config.runtime.camera_enabled:
            try:
                from picamera2 import Picamera2

                self.camera = Picamera2()
                self.camera.configure(
                    self.camera.create_still_configuration(
                        main={"size": (config.runtime.camera_width, config.runtime.camera_height)}
                    )
                )
                self.camera.start()
            except Exception:
                self.camera = None
        self.latest_jpeg: bytes | None = None

    def _blocked(self, sensor, name: str) -> int:
        active_low = IR_ACTIVE_LOW[name]
        return int(sensor.value == (0 if active_low else 1))

    def read_sensors(self) -> SensorSnapshot:
        reading = self.ultrasonic.measure()
        imu = self.imu.read()
        now = time()
        if now >= self.next_gps_poll:
            gps = self.gps.read()
            self.next_gps_poll = now + 0.5
            if gps.fix_quality > 0 and gps.lat is not None and gps.lon is not None:
                self.last_gps_lat = gps.lat
                self.last_gps_lon = gps.lon
                self.last_gps_fix_quality = gps.fix_quality
                self.last_gps_fix_time = now
            elif self.last_gps_fix_time is None:
                self.last_gps_fix_quality = gps.fix_quality
        gaps = score_jpeg(self.latest_jpeg)
        return SensorSnapshot(
            timestamp=time(),
            ir_left=self._blocked(self.left_ir, "left"),
            ir_center=self._blocked(self.center_ir, "center"),
            ir_right=self._blocked(self.right_ir, "right"),
            ultrasonic_cm=max(0.0, reading.distance_cm if reading.distance_cm is not None else 999.0),
            servo_angle=self.servo_angle,
            camera_ok=gaps.ok,
            left_gap=gaps.left,
            center_gap=gaps.center,
            right_gap=gaps.right,
            acceleration_g=imu.acceleration,
            gyro_z_dps=imu.gyro_z,
            gps_lat=self.last_gps_lat,
            gps_lon=self.last_gps_lon,
            gps_fix_quality=self.last_gps_fix_quality,
            gps_last_fix_age_s=None if self.last_gps_fix_time is None else max(0.0, now - self.last_gps_fix_time),
            error=reading.error,
        )

    def capture_camera(self) -> bytes | None:
        if self.camera is None:
            self.latest_jpeg = None
            return None
        try:
            import cv2

            frame = self.camera.capture_array()
            frame = cv2.rotate(frame, cv2.ROTATE_180)
            if frame.ndim == 3 and frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
            elif frame.ndim == 3 and frame.shape[2] == 3:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.config.runtime.jpeg_quality])
            self.latest_jpeg = encoded.tobytes() if ok else None
            return self.latest_jpeg
        except Exception:
            self.latest_jpeg = None
            return None

    def set_servo(self, angle: int) -> None:
        next_angle = max(0, min(180, int(angle)))
        if next_angle == self.servo_angle:
            return
        self.servo_angle = next_angle
        self.servo.angle = next_angle
        sleep(0.08)

    def close(self) -> None:
        try:
            self.ultrasonic.close()
        except Exception:
            return
