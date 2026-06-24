from __future__ import annotations

from dataclasses import asdict, dataclass, field
from time import time


@dataclass(frozen=True)
class SensorSnapshot:
    timestamp: float
    ir_left: int
    ir_center: int
    ir_right: int
    ultrasonic_cm: float
    servo_angle: int
    camera_ok: bool = False
    left_gap: float = 0.5
    center_gap: float = 0.5
    right_gap: float = 0.5
    acceleration_g: float = 0.0
    gyro_z_dps: float = 0.0
    gps_lat: float | None = None
    gps_lon: float | None = None
    gps_fix_quality: int = 0
    error: str | None = None

    @classmethod
    def empty(cls) -> "SensorSnapshot":
        return cls(
            timestamp=time(),
            ir_left=0,
            ir_center=0,
            ir_right=0,
            ultrasonic_cm=999.0,
            servo_angle=90,
        )


@dataclass(frozen=True)
class MotorCommand:
    front_left: float = 0.0
    front_right: float = 0.0
    rear_left: float = 0.0
    rear_right: float = 0.0
    label: str = "stop"

    def stopped(self) -> bool:
        return not any((self.front_left, self.front_right, self.rear_left, self.rear_right))


@dataclass(frozen=True)
class Decision:
    state: str
    reason: str
    command: MotorCommand
    servo_angle: int = 90
    turn_direction: int = 0
    scan_active: bool = False


@dataclass
class Telemetry:
    running: bool = True
    emergency_stop: bool = False
    state: str = "starting"
    reason: str = "Booting."
    sensors: SensorSnapshot = field(default_factory=SensorSnapshot.empty)
    command: MotorCommand = field(default_factory=MotorCommand)
    last_camera_jpeg: bytes | None = None
    camera_updated_at: float = 0.0
    loop_hz: float = 0.0
    error: str | None = None
    active_recording: dict | None = None
    latest_record: dict | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data.pop("last_camera_jpeg", None)
        return data
