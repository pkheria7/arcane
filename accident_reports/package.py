from __future__ import annotations

import json
from pathlib import Path
from time import time

from event_logger.evidence import EvidenceLogger
from navigation_ai.expert_controller import Decision
from sensor_layer.types import SensorFrame


class AccidentPackager:
    def __init__(self, output_root: str | Path = "accident_reports/packages") -> None:
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)

    def create(self, frame: SensorFrame, decision: Decision, evidence: EvidenceLogger) -> Path:
        package_dir = self.output_root / f"accident_{int(time() * 1000)}"
        package_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "gps_location": {"lat": frame.gps_lat, "lon": frame.gps_lon},
            "selected_action": decision.action.value,
            "alternative_actions": sorted(decision.probabilities.items(), key=lambda item: item[1], reverse=True)[1:],
            "action_probabilities": decision.probabilities,
            "reason_code": decision.reason_code.value,
            "sensor_history": list(evidence.history),
            "current_frame": frame.__dict__,
        }
        (package_dir / "accident_package.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return package_dir
