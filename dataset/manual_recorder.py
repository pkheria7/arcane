from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from sensor_layer.types import SensorFrame


MANUAL_DATASET_COLUMNS = [
    "timestamp",
    "vehicle_id",
    "ir_left",
    "ir_center",
    "ir_right",
    "ultrasonic_distance",
    "servo_angle",
    "gps_lat",
    "gps_lon",
    "heading",
    "acceleration",
    "accel_x",
    "accel_y",
    "accel_z",
    "gyro_z",
    "image_path",
    "manual_steering",
    "manual_speed_cm_s",
    "manual_direction",
    "manual_stop",
    "derived_action",
    "left_gap_score",
    "center_gap_score",
    "right_gap_score",
    "best_gap_angle",
    "best_gap_score",
    "gap_metrics_json",
]


@dataclass(frozen=True)
class ManualCommandState:
    speed_cm_s: float = 5.0
    steering: float = 0.0
    direction: str = "forward"
    servo_angle: int = 0
    stop: bool = True
    sweep_requested: bool = False

    def normalized(self) -> "ManualCommandState":
        speed_modes = (0.0, 2.0, 3.0, 4.0, 5.0)
        speed = min(speed_modes, key=lambda value: abs(value - float(self.speed_cm_s)))
        return ManualCommandState(
            speed_cm_s=speed,
            steering=max(-1.0, min(1.0, float(self.steering))),
            direction="reverse" if self.direction == "reverse" else "forward",
            servo_angle=max(0, min(180, int(self.servo_angle))),
            stop=bool(self.stop),
            sweep_requested=bool(self.sweep_requested),
        )


def derived_action(steering: float, stop: bool, direction: str = "forward") -> str:
    if stop:
        return "stop"
    prefix = "reverse_" if direction == "reverse" else ""
    if steering <= -0.75:
        return f"{prefix}full_left"
    if steering < -0.2:
        return f"{prefix}slight_left"
    if steering >= 0.75:
        return f"{prefix}full_right"
    if steering > 0.2:
        return f"{prefix}slight_right"
    return f"{prefix}straight"


class ManualDriveRecorder:
    def __init__(self, csv_path: str | Path) -> None:
        self.csv_path = Path(csv_path)
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.csv_path.exists():
            with self.csv_path.open("w", newline="") as f:
                csv.DictWriter(f, fieldnames=MANUAL_DATASET_COLUMNS).writeheader()

    def append(
        self,
        vehicle_id: str,
        frame: SensorFrame,
        command: ManualCommandState,
        gap_metrics: dict[int, dict],
        best_gap_angle: int | None,
        best_gap_score: float,
    ) -> None:
        row = asdict(frame)
        row.update(
            {
                "vehicle_id": vehicle_id,
                "manual_steering": command.steering,
                "manual_speed_cm_s": command.speed_cm_s,
                "manual_direction": command.direction,
                "manual_stop": int(command.stop),
                "derived_action": derived_action(command.steering, command.stop, command.direction),
                "best_gap_angle": best_gap_angle,
                "best_gap_score": best_gap_score,
                "gap_metrics_json": json.dumps(gap_metrics, sort_keys=True),
            }
        )
        clean = {column: row.get(column) for column in MANUAL_DATASET_COLUMNS}
        with self.csv_path.open("a", newline="") as f:
            csv.DictWriter(f, fieldnames=MANUAL_DATASET_COLUMNS).writerow(clean)
