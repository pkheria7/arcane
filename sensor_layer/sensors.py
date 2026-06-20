from __future__ import annotations

import random
from pathlib import Path
from time import sleep, time

from .gps import GpsReader, NullGpsReader, SerialGpsReader
from .gpio_factory import configure_gpiozero_pin_factory
from .imu import ImuReader, Mpu6050Reader, NullImuReader
from .types import SensorFrame
from .ultrasonic import LgpioUltrasonicSensor, NullUltrasonicSensor, UltrasonicSensor

IR_ACTIVE_LOW = {
    "left": False,
    "center": False,
    "right": True,
}


class SensorSuite:
    def read_frame(self, servo_angle: int = 0, image_path: str | None = None) -> SensorFrame: ...
    def capture_image(self, directory: str | Path, prefix: str = "frame") -> str | None: ...
    def capture_image_bytes(self, quality: int = 55) -> bytes | None: ...


class SimulatedSensorSuite(SensorSuite):
    def __init__(self) -> None:
        self.tick = 0

    def read_frame(self, servo_angle: int = 0, image_path: str | None = None) -> SensorFrame:
        self.tick += 1
        center = 1 if self.tick % 23 == 0 else 0
        left = 1 if self.tick % 31 == 0 else 0
        right = 1 if self.tick % 37 == 0 else 0
        distance = 14.0 if self.tick % 97 == 0 else random.uniform(24.0, 160.0)
        return SensorFrame(
            timestamp=time(),
            ir_left=left,
            ir_center=center,
            ir_right=right,
            ultrasonic_distance=distance,
            servo_angle=servo_angle,
            gps_lat=28.6139 + self.tick * 0.000001,
            gps_lon=77.2090 + self.tick * 0.000001,
            heading=float((self.tick * 3) % 360),
            acceleration=random.uniform(0.0, 1.4),
            accel_x=random.uniform(-0.1, 0.1),
            accel_y=random.uniform(-0.1, 0.1),
            accel_z=1.0 + random.uniform(-0.05, 0.05),
            gyro_z=random.uniform(-8.0, 8.0),
            image_path=image_path,
        )

    def capture_image(self, directory: str | Path, prefix: str = "frame") -> str | None:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{prefix}_{int(time() * 1000)}.jpg"
        try:
            import cv2
            import numpy as np

            img = np.zeros((240, 320, 3), dtype=np.uint8)
            img[:, :, 1] = 60
            cv2.imwrite(str(path), img)
            return str(path)
        except Exception:
            path.write_bytes(b"")
            return str(path)

    def capture_image_bytes(self, quality: int = 55) -> bytes | None:
        try:
            import cv2
            import numpy as np

            img = np.zeros((180, 240, 3), dtype=np.uint8)
            img[:, :, 1] = 60
            ok, encoded = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
            return encoded.tobytes() if ok else None
        except Exception:
            return None


class PiSensorSuite(SensorSuite):
    def __init__(
        self,
        ir_left: int,
        ir_center: int,
        ir_right: int,
        trig: int,
        echo: int,
        camera_enabled: bool = True,
        gps: GpsReader | None = None,
        imu: ImuReader | None = None,
        ultrasonic: UltrasonicSensor | None = None,
        pin_factory: str = "auto",
        camera_size: tuple[int, int] = (320, 240),
        ir_active_low: dict[str, bool] | None = None,
    ) -> None:
        configure_gpiozero_pin_factory(pin_factory)
        from gpiozero import DigitalInputDevice

        self.ir_active_low = IR_ACTIVE_LOW | (ir_active_low or {})
        self.left = DigitalInputDevice(ir_left, pull_up=True)
        self.center = DigitalInputDevice(ir_center, pull_up=True)
        self.right = DigitalInputDevice(ir_right, pull_up=True)
        self.ultrasonic = ultrasonic if ultrasonic is not None else self._default_ultrasonic(trig, echo)
        self.gps = gps if gps is not None else self._default_gps()
        self.imu = imu if imu is not None else self._default_imu()
        self.camera = None
        self.camera_rotation = 180
        if camera_enabled:
            try:
                from picamera2 import Picamera2

                self.camera = Picamera2()
                self.camera.configure(self.camera.create_still_configuration(main={"size": camera_size}))
                self.camera.start()
            except Exception:
                self.camera = None

    def _default_gps(self) -> GpsReader:
        try:
            return SerialGpsReader()
        except Exception:
            return NullGpsReader()

    def _default_imu(self) -> ImuReader:
        try:
            return Mpu6050Reader()
        except Exception:
            return NullImuReader()

    def _default_ultrasonic(self, trig: int, echo: int) -> UltrasonicSensor:
        try:
            return LgpioUltrasonicSensor(trig=trig, echo=echo)
        except Exception:
            return NullUltrasonicSensor()

    def read_frame(self, servo_angle: int = 0, image_path: str | None = None) -> SensorFrame:
        gps = self.gps.read()
        imu = self.imu.read()
        ultrasonic = self.ultrasonic.measure()
        return SensorFrame(
            timestamp=time(),
            ir_left=self._ir_blocked(self.left, "left"),
            ir_center=self._ir_blocked(self.center, "center"),
            ir_right=self._ir_blocked(self.right, "right"),
            ultrasonic_distance=max(0.0, ultrasonic.distance_cm if ultrasonic.distance_cm is not None else 999.0),
            servo_angle=servo_angle,
            gps_lat=gps.lat,
            gps_lon=gps.lon,
            heading=imu.heading,
            acceleration=imu.acceleration,
            accel_x=imu.accel_x,
            accel_y=imu.accel_y,
            accel_z=imu.accel_z,
            gyro_z=imu.gyro_z,
            image_path=image_path,
        )

    def _ir_blocked(self, sensor, name: str) -> int:
        active_low = self.ir_active_low[name]
        blocked = sensor.value == (0 if active_low else 1)
        return int(blocked)

    def capture_image(self, directory: str | Path, prefix: str = "frame") -> str | None:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{prefix}_{int(time() * 1000)}.jpg"
        if self.camera is None:
            return None
        image_bytes = self.capture_image_bytes()
        if image_bytes:
            path.write_bytes(image_bytes)
        else:
            self.camera.capture_file(str(path))
        sleep(0.05)
        return str(path)

    def capture_image_bytes(self, quality: int = 55) -> bytes | None:
        if self.camera is None:
            return None
        try:
            import cv2

            frame = self.camera.capture_array()
            if self.camera_rotation == 180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            if frame.ndim == 3 and frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
            elif frame.ndim == 3 and frame.shape[2] == 3:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
            return encoded.tobytes() if ok else None
        except Exception:
            return None
