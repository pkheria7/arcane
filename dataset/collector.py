from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path

from navigation_ai.expert_controller import Decision
from sensor_layer.types import SensorFrame

from .schema import DATASET_COLUMNS


class DatasetLogger:
    def __init__(self, csv_path: str | Path) -> None:
        self.csv_path = Path(csv_path)
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.csv_path.exists():
            with self.csv_path.open("w", newline="") as f:
                csv.DictWriter(f, fieldnames=DATASET_COLUMNS).writeheader()

    def append(self, frame: SensorFrame, decision: Decision) -> None:
        row = asdict(frame)
        row.update(
            {
                "chosen_action": decision.action.value,
                "reason_code": decision.reason_code.value,
                "p_left": decision.probabilities["left"],
                "p_straight": decision.probabilities["straight"],
                "p_right": decision.probabilities["right"],
                "p_stop": decision.probabilities["stop"],
            }
        )
        clean = {column: row.get(column) for column in DATASET_COLUMNS}
        with self.csv_path.open("a", newline="") as f:
            csv.DictWriter(f, fieldnames=DATASET_COLUMNS).writerow(clean)
