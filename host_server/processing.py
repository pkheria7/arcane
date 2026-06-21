from __future__ import annotations

from pathlib import Path
from time import time

from accident_reports.detector import AccidentDetector
from accident_reports.package import AccidentPackager
from dataset.manual_recorder import ManualCommandState, ManualDriveRecorder
from edge_protocol.messages import HostCommand, ImagePayload
from event_logger.evidence import EvidenceLogger
from explainability.report_generator import generate_report
from inference.runtime import NavigationRuntime
from navigation_ai.gap_detector import analyze_gap, image_gap_scores
from sensor_layer.types import SensorFrame


class HostProcessor:
    def __init__(
        self,
        model_path: str | None = None,
        dataset_path: str = "dataset/drives/manual_drive_log.csv",
        image_root: str = "dataset/images/host_uploads",
    ) -> None:
        self.runtime = NavigationRuntime(model_path=model_path)
        self.recorder = ManualDriveRecorder(dataset_path)
        self.evidence = EvidenceLogger()
        self.accident_detector = AccidentDetector()
        self.packager = AccidentPackager()
        self.image_root = Path(image_root)
        self.command = ManualCommandState()
        self.latest_frame: SensorFrame | None = None
        self.latest_image_path: Path | None = None
        self.latest_image_data: bytes | None = None
        self.latest_image_content_type = "image/jpeg"
        self.latest_image_updated_at = 0.0
        self.latest_gap_metrics: dict[int, dict] = {}
        self.latest_suggestion: dict | None = None

    def update_command(self, payload: dict) -> ManualCommandState:
        sweep_requested = bool(payload.get("sweep_requested", False))
        self.command = ManualCommandState(
            speed_cm_s=float(payload.get("speed_cm_s", self.command.speed_cm_s)),
            steering=float(payload.get("steering", self.command.steering)),
            direction=str(payload.get("direction", self.command.direction)),
            servo_angle=int(payload.get("servo_angle", self.command.servo_angle)),
            stop=bool(payload.get("stop", self.command.stop)),
            sweep_requested=sweep_requested,
        ).normalized()
        return self.command

    def state(self) -> dict:
        return {
            "command": self.command.__dict__,
            "latest_frame": self.latest_frame.__dict__ if self.latest_frame else None,
            "latest_image_url": "/api/v1/latest-image?vehicle=latest" if self.latest_image_data else None,
            "latest_image_updated_at": self.latest_image_updated_at,
            "latest_gap_metrics": self.latest_gap_metrics,
            "latest_suggestion": self.latest_suggestion,
        }

    def process_packet(self, packet: dict) -> HostCommand:
        vehicle_id = str(packet.get("vehicle_id", "vehicle"))
        upload_dir = self.image_root / vehicle_id
        frame_data = dict(packet["frame"])

        image_path = self._store_image(packet.get("image"), upload_dir, "cycle")
        if image_path:
            frame_data["image_path"] = str(image_path)

        scan_scores, scan_metrics = self._scan_scores(packet.get("scan_images") or [], upload_dir)
        if scan_scores:
            frame_data["left_gap_score"] = scan_scores.get(135, (0.0, 0.0, 0.0))[0]
            frame_data["center_gap_score"] = scan_scores.get(90, (0.0, 0.5, 0.0))[1]
            frame_data["right_gap_score"] = scan_scores.get(45, (0.0, 0.0, 0.0))[2]
        else:
            frame_data["left_gap_score"] = 0.5
            frame_data["center_gap_score"] = 0.5
            frame_data["right_gap_score"] = 0.5

        frame = SensorFrame(**frame_data)
        suggestion = self.runtime.decide(frame)
        self.latest_frame = frame
        self.latest_image_path = image_path
        self.latest_gap_metrics = scan_metrics
        best_gap_angle, best_gap_score = self._best_gap(scan_metrics)
        self.latest_suggestion = {
            "action": suggestion.action.value,
            "reason_code": suggestion.reason_code.value,
            "probabilities": suggestion.probabilities,
            "best_gap_angle": best_gap_angle,
            "best_gap_score": best_gap_score,
        }
        self.recorder.append(vehicle_id, frame, self.command, scan_metrics, best_gap_angle, best_gap_score)

        decision = suggestion
        self.evidence.observe(frame, decision)

        event_recorded = False
        accident_report_path = None
        if self.evidence.event_needed(frame, decision):
            self.evidence.write_event(decision.reason_code.value, frame, decision)
            event_recorded = True
        if self.accident_detector.is_collision(frame):
            package = self.packager.create(frame, decision, self.evidence)
            accident_report_path = str(generate_report(package))

        command_for_response = self.command
        if self.command.sweep_requested:
            self.command = ManualCommandState(
                speed_cm_s=self.command.speed_cm_s,
                steering=self.command.steering,
                direction=self.command.direction,
                servo_angle=self.command.servo_angle,
                stop=self.command.stop,
                sweep_requested=False,
            )

        return HostCommand(
            action="stop" if command_for_response.stop else "manual",
            speed=self._pwm_from_cm_s(command_for_response.speed_cm_s),
            servo_angle=command_for_response.servo_angle,
            probabilities=decision.probabilities,
            reason_code="manual_control",
            explanation="Manual Mac dashboard command is active; autonomous suggestion is recorded but not applied.",
            speed_cm_s=command_for_response.speed_cm_s,
            steering=command_for_response.steering,
            direction=command_for_response.direction,
            stop=command_for_response.stop,
            sweep_requested=command_for_response.sweep_requested,
            event_recorded=event_recorded,
            accident_report_path=accident_report_path,
        )

    def _store_image(self, payload: dict | None, upload_dir: Path, prefix: str) -> Path | None:
        if not payload:
            return None
        image = ImagePayload(**payload)
        self.latest_image_data = image.to_bytes()
        self.latest_image_content_type = image.content_type
        self.latest_image_updated_at = time()
        return image.write_to(upload_dir, f"{int(time() * 1000)}_{prefix}")

    def _scan_scores(self, payloads: list[dict], upload_dir: Path) -> tuple[dict[int, tuple[float, float, float]], dict[int, dict]]:
        scores = {}
        metrics = {}
        for payload in payloads:
            image = ImagePayload(**payload)
            path = image.write_to(upload_dir, f"{int(time() * 1000)}_scan")
            scores[image.angle] = image_gap_scores(str(path))
            metrics[image.angle] = analyze_gap(str(path))
        return scores, metrics

    def latest_image_bytes(self) -> tuple[bytes, str] | None:
        if self.latest_image_data is not None:
            return self.latest_image_data, self.latest_image_content_type
        if not self.latest_image_path or not self.latest_image_path.exists():
            return None
        return self.latest_image_path.read_bytes(), "image/jpeg"

    def _best_gap(self, metrics: dict[int, dict]) -> tuple[int | None, float]:
        if not metrics:
            return None, 0.0
        ranked = sorted(metrics.items(), key=lambda item: float(item[1].get("free_space_score", 0.0)), reverse=True)
        return ranked[0][0], float(ranked[0][1].get("free_space_score", 0.0))

    def _pwm_from_cm_s(self, speed_cm_s: float) -> float:
        return max(0.0, min(1.0, float(speed_cm_s) / 5.0))
