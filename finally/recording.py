from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from time import gmtime, strftime, time
from typing import Any

from .models import Decision, SensorSnapshot


IR_ANGLES = {
    "left": 180,
    "center": 90,
    "right": 0,
}


def active_ir_name(sensors: SensorSnapshot, current: str | None = None) -> str | None:
    if current == "left" and sensors.ir_left:
        return current
    if current == "center" and sensors.ir_center:
        return current
    if current == "right" and sensors.ir_right:
        return current
    if sensors.ir_center:
        return "center"
    if sensors.ir_left:
        return "left"
    if sensors.ir_right:
        return "right"
    return None


class IRSceneRecorder:
    def __init__(self, root: str | Path, fps: float = 3.0) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.fps = max(1.0, float(fps))
        self.active_sensor: str | None = None
        self.event_dir: Path | None = None
        self.started_at = 0.0
        self.writer = None
        self.frame_size: tuple[int, int] | None = None
        self.frame_count = 0
        self.latest_record: dict | None = None

    @property
    def active_angle(self) -> int | None:
        return IR_ANGLES[self.active_sensor] if self.active_sensor else None

    def sync_trigger(self, sensors: SensorSnapshot) -> str | None:
        next_sensor = active_ir_name(sensors, self.active_sensor)
        if next_sensor and self.active_sensor is None:
            self._start(next_sensor, sensors)
        elif next_sensor and self.active_sensor is not None and next_sensor != self.active_sensor:
            self.finish(f"{self.active_sensor} IR cleared; {next_sensor} IR active")
            self._start(next_sensor, sensors)
        elif next_sensor is None and self.active_sensor is not None:
            self.finish("IR sensor cleared")
        return self.active_sensor

    def record_loop(
        self,
        sensors: SensorSnapshot,
        decision: Decision,
        state: str,
        reason: str,
        jpeg: bytes | None = None,
    ) -> None:
        if self.event_dir is None:
            return
        row = {
            "timestamp": time(),
            "state": state,
            "reason": reason,
            "active_ir": self.active_sensor,
            "sensors": asdict(sensors),
            "decision": {
                "state": decision.state,
                "reason": decision.reason,
                "command": asdict(decision.command),
                "turn_direction": decision.turn_direction,
                "scan_active": decision.scan_active,
            },
        }
        with (self.event_dir / "actions.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")
        if jpeg:
            self._write_frame(jpeg)

    def finish(self, reason: str) -> dict | None:
        if self.event_dir is None:
            return None
        if self.writer is not None:
            self.writer.release()
        ended_at = time()
        summary = {
            "id": self.event_dir.name,
            "active_ir": self.active_sensor,
            "started_at": self.started_at,
            "ended_at": ended_at,
            "duration_s": max(0.0, ended_at - self.started_at),
            "frame_count": self.frame_count,
            "video_path": str(self.event_dir / "scene.mp4"),
            "actions_path": str(self.event_dir / "actions.jsonl"),
            "finish_reason": reason,
            "mac_report_note": "Download this record and run the Mac vision/LLM PDF generator on scene.mp4 + actions.jsonl.",
        }
        (self.event_dir / "manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        self.latest_record = summary
        self.active_sensor = None
        self.event_dir = None
        self.writer = None
        self.frame_size = None
        self.frame_count = 0
        return summary

    def active_summary(self) -> dict | None:
        if self.event_dir is None:
            return None
        return {
            "id": self.event_dir.name,
            "active_ir": self.active_sensor,
            "started_at": self.started_at,
            "duration_s": max(0.0, time() - self.started_at),
            "frame_count": self.frame_count,
            "servo_angle": self.active_angle,
        }

    def _start(self, sensor: str, sensors: SensorSnapshot) -> None:
        self.active_sensor = sensor
        self.started_at = time()
        stamp = strftime("%Y%m%d_%H%M%S", gmtime(self.started_at))
        self.event_dir = self.root / f"{stamp}_{sensor}_ir"
        self.event_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "id": self.event_dir.name,
            "active_ir": sensor,
            "servo_angle": IR_ANGLES[sensor],
            "started_at": self.started_at,
            "start_sensors": asdict(sensors),
            "video_path": str(self.event_dir / "scene.mp4"),
            "actions_path": str(self.event_dir / "actions.jsonl"),
        }
        (self.event_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def _write_frame(self, jpeg: bytes) -> None:
        if self.event_dir is None:
            return
        try:
            import cv2
            import numpy as np

            data = np.frombuffer(jpeg, dtype=np.uint8)
            frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if frame is None:
                return
            height, width = frame.shape[:2]
            if self.writer is None:
                self.frame_size = (width, height)
                self.writer = cv2.VideoWriter(
                    str(self.event_dir / "scene.mp4"),
                    cv2.VideoWriter_fourcc(*"mp4v"),
                    self.fps,
                    self.frame_size,
                )
            if self.frame_size and (width, height) != self.frame_size:
                frame = cv2.resize(frame, self.frame_size)
            self.writer.write(frame)
            self.frame_count += 1
        except Exception as exc:
            if self.event_dir is not None:
                with (self.event_dir / "recording_errors.jsonl").open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"timestamp": time(), "error": str(exc)}) + "\n")


def list_records(root: str | Path) -> list[dict[str, Any]]:
    records = []
    root = Path(root)
    if not root.exists():
        return records
    for manifest in sorted(root.glob("*/manifest.json"), reverse=True):
        try:
            records.append(json.loads(manifest.read_text(encoding="utf-8")))
        except Exception:
            continue
    return records
