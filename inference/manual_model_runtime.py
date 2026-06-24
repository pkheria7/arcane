from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import pandas as pd

from dataset.schema import FEATURE_COLUMNS
from sensor_layer.types import SensorFrame


@dataclass(frozen=True)
class ManualModelPrediction:
    steering: float
    speed_cm_s: float
    direction: str
    stop: bool


class ManualModelRuntime:
    def __init__(self, model_path: str | Path) -> None:
        self.model = joblib.load(model_path)

    def predict(self, frame: SensorFrame) -> ManualModelPrediction:
        row = pd.DataFrame([{column: getattr(frame, column) for column in FEATURE_COLUMNS}])
        pred = self.model.predict(row)[0]
        steering = float(pred[0])
        speed_cm_s = float(pred[1])
        direction_value = float(pred[2])

        # Clamp to safe ranges
        steering = max(-1.0, min(1.0, steering))
        speed_cm_s = max(0.0, min(5.0, speed_cm_s))
        direction = "reverse" if direction_value < 0 else "forward"

        # Treat very low predicted speed as a stop command
        stop = speed_cm_s < 0.5

        return ManualModelPrediction(
            steering=steering,
            speed_cm_s=speed_cm_s,
            direction=direction,
            stop=stop,
        )
