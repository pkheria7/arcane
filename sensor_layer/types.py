from __future__ import annotations

from dataclasses import dataclass
from time import time


@dataclass(frozen=True)
class GpsReading:
    lat: float | None = None
    lon: float | None = None
    fix_quality: int = 0


@dataclass(frozen=True)
class ImuReading:
    heading: float = 0.0
    acceleration: float = 0.0
    accel_x: float = 0.0
    accel_y: float = 0.0
    accel_z: float = 0.0
    gyro_z: float = 0.0


@dataclass(frozen=True)
class SensorFrame:
    timestamp: float
    ir_left: int
    ir_center: int
    ir_right: int
    ultrasonic_distance: float
    servo_angle: int
    gps_lat: float | None
    gps_lon: float | None
    heading: float
    acceleration: float
    accel_x: float
    accel_y: float
    accel_z: float
    gyro_z: float
    image_path: str | None = None
    left_gap_score: float = 0.0
    center_gap_score: float = 0.0
    right_gap_score: float = 0.0

    @classmethod
    def empty(cls) -> "SensorFrame":
        return cls(
            timestamp=time(),
            ir_left=0,
            ir_center=0,
            ir_right=0,
            ultrasonic_distance=999.0,
            servo_angle=0,
            gps_lat=None,
            gps_lon=None,
            heading=0.0,
            acceleration=0.0,
            accel_x=0.0,
            accel_y=0.0,
            accel_z=1.0,
            gyro_z=0.0,
        )
