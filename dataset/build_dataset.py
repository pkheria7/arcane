from __future__ import annotations

import argparse
import random
from pathlib import Path

from dataset.collector import DatasetLogger
from navigation_ai.expert_controller import ExpertController
from sensor_layer.types import SensorFrame


def generate_synthetic_dataset(output: str | Path, rows: int = 500) -> Path:
    logger = DatasetLogger(output)
    controller = ExpertController()
    for i in range(rows):
        scenario = random.choice(["clear", "left", "right", "front_left_gap", "front_right_gap", "blocked", "emergency"])
        values = {
            "timestamp": 1_700_000_000 + i,
            "ir_left": int(scenario == "left"),
            "ir_center": int(scenario in {"front_left_gap", "front_right_gap", "blocked"}),
            "ir_right": int(scenario == "right"),
            "ultrasonic_distance": 12.0 if scenario == "emergency" else random.uniform(22.0, 180.0),
            "servo_angle": 0,
            "gps_lat": 28.6139 + i * 0.000001,
            "gps_lon": 77.2090 + i * 0.000001,
            "heading": float((i * 7) % 360),
            "acceleration": random.uniform(0.8, 1.2),
            "accel_x": random.uniform(-0.15, 0.15),
            "accel_y": random.uniform(-0.15, 0.15),
            "accel_z": random.uniform(0.9, 1.1),
            "gyro_z": random.uniform(-12.0, 12.0),
            "left_gap_score": random.uniform(0.65, 0.95) if scenario == "front_left_gap" else random.uniform(0.05, 0.35),
            "center_gap_score": random.uniform(0.2, 0.6),
            "right_gap_score": random.uniform(0.65, 0.95) if scenario == "front_right_gap" else random.uniform(0.05, 0.35),
            "image_path": None,
        }
        if scenario == "blocked":
            values["left_gap_score"] = random.uniform(0.05, 0.2)
            values["right_gap_score"] = random.uniform(0.05, 0.2)
        frame = SensorFrame(**values)
        logger.append(frame, controller.decide(frame))
    return Path(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="dataset/drives/synthetic_drive_log.csv")
    parser.add_argument("--rows", type=int, default=500)
    args = parser.parse_args()
    generate_synthetic_dataset(args.output, args.rows)


if __name__ == "__main__":
    main()
