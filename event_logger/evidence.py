from __future__ import annotations

import json
import shutil
from collections import deque
from dataclasses import asdict
from pathlib import Path
from time import time

from navigation_ai.expert_controller import Decision
from sensor_layer.types import SensorFrame


class EvidenceLogger:
    def __init__(self, root: str | Path = "event_logger/evidence", history_size: int = 120) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.history: deque[dict] = deque(maxlen=history_size)

    def observe(self, frame: SensorFrame, decision: Decision) -> None:
        self.history.append({"frame": asdict(frame), "decision": self._decision_dict(decision)})

    def event_needed(self, frame: SensorFrame, decision: Decision) -> bool:
        return bool(frame.ir_left or frame.ir_center or frame.ir_right or decision.action.value == "stop" or abs(frame.gyro_z) > 45)

    def write_event(self, event_type: str, frame: SensorFrame, decision: Decision) -> Path:
        event_dir = self.root / f"{int(time() * 1000)}_{event_type}"
        event_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "event_type": event_type,
            "current_frame": asdict(frame),
            "decision": self._decision_dict(decision),
            "sensor_history": list(self.history),
        }
        (event_dir / "event.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        if frame.image_path and Path(frame.image_path).exists():
            shutil.copy2(frame.image_path, event_dir / Path(frame.image_path).name)
        self._write_clip(event_dir)
        return event_dir

    def _decision_dict(self, decision: Decision) -> dict:
        return {
            "action": decision.action.value,
            "reason_code": decision.reason_code.value,
            "speed": decision.speed,
            "probabilities": decision.probabilities,
            "second_best_action": decision.second_best_action.value,
            "explanation": decision.explanation,
        }

    def _write_clip(self, event_dir: Path) -> None:
        image_paths = [
            item["frame"].get("image_path")
            for item in self.history
            if item.get("frame", {}).get("image_path") and Path(item["frame"]["image_path"]).exists()
        ]
        if len(image_paths) < 2:
            return
        try:
            import cv2

            first = cv2.imread(image_paths[0])
            if first is None:
                return
            height, width = first.shape[:2]
            writer = cv2.VideoWriter(str(event_dir / "evidence_clip.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 8, (width, height))
            for path in image_paths:
                image = cv2.imread(path)
                if image is not None:
                    writer.write(cv2.resize(image, (width, height)))
            writer.release()
        except Exception:
            return
