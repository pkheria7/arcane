from __future__ import annotations

from dataclasses import dataclass

from sensor_layer.types import SensorFrame


@dataclass(frozen=True)
class AccidentConfig:
    impact_acceleration_g: float = 2.6
    sharp_gyro_z_dps: float = 120.0


class AccidentDetector:
    def __init__(self, config: AccidentConfig | None = None) -> None:
        self.config = config or AccidentConfig()

    def is_collision(self, frame: SensorFrame) -> bool:
        return frame.acceleration >= self.config.impact_acceleration_g or abs(frame.gyro_z) >= self.config.sharp_gyro_z_dps
