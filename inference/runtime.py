from __future__ import annotations

from pathlib import Path

from dataset.schema import FEATURE_COLUMNS
from navigation_ai.actions import ACTIONS, Action
from navigation_ai.expert_controller import Decision, ExpertController
from sensor_layer.types import SensorFrame


class NavigationRuntime:
    def __init__(self, model_path: str | Path | None = None, fallback: ExpertController | None = None) -> None:
        self.model = None
        if model_path and Path(model_path).exists():
            import joblib

            self.model = joblib.load(model_path)
        self.fallback = fallback or ExpertController()

    def decide(self, frame: SensorFrame) -> Decision:
        if self.model is None:
            return self.fallback.decide(frame)
        import pandas as pd

        row = pd.DataFrame([{column: getattr(frame, column) for column in FEATURE_COLUMNS}])
        probabilities = self._predict_probabilities(row)
        action = Action(max(probabilities, key=probabilities.get))
        expert_reason = self.fallback.decide(frame)
        ranked = sorted(probabilities.items(), key=lambda item: item[1], reverse=True)
        return Decision(
            action=action,
            reason_code=expert_reason.reason_code,
            speed=0.0 if action == Action.STOP else expert_reason.speed,
            probabilities=probabilities,
            second_best_action=Action(ranked[1][0]),
            explanation=f"ML policy selected {action.value}; rule engine reason context: {expert_reason.reason_code.value}.",
        )

    def _predict_probabilities(self, row: pd.DataFrame) -> dict[str, float]:
        if hasattr(self.model, "predict_proba"):
            raw = self.model.predict_proba(row)[0]
            classes = [str(c) for c in self.model.classes_] if hasattr(self.model, "classes_") else [str(c) for c in self.model.named_steps["model"].classes_]
            result = {action.value: 0.0 for action in ACTIONS}
            for name, probability in zip(classes, raw):
                result[name] = float(probability)
            total = sum(result.values()) or 1.0
            return {key: value / total for key, value in result.items()}
        predicted = str(self.model.predict(row)[0])
        return {action.value: (1.0 if action.value == predicted else 0.0) for action in ACTIONS}
