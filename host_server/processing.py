from __future__ import annotations

from pathlib import Path
from time import time

from accident_reports.detector import AccidentDetector
from accident_reports.package import AccidentPackager
from dataset.manual_recorder import ManualCommandState, ManualDriveRecorder
from edge_protocol.messages import HostCommand, ImagePayload
from event_logger.evidence import EvidenceLogger
from explainability.report_generator import generate_report
from inference.manual_model_runtime import ManualModelRuntime
from inference.runtime import NavigationRuntime
from navigation_ai.actions import Action, ReasonCode
from navigation_ai.expert_controller import Decision
from navigation_ai.gap_detector import analyze_gap, image_gap_scores
from sensor_layer.types import SensorFrame


class HostProcessor:
    def __init__(
        self,
        model_path: str | None = None,
        dataset_path: str = "dataset/drives/manual_drive_log.csv",
        image_root: str = "dataset/images/host_uploads",
    ) -> None:
        # Expert controller provides suggestions and safety context.
        self.runtime = NavigationRuntime(model_path=None)
        self.manual_model: ManualModelRuntime | None = None
        self.model_path = model_path
        self.model_load_error: str | None = None
        if model_path and Path(model_path).exists():
            try:
                self.manual_model = ManualModelRuntime(model_path)
                print(f"[host] Loaded manual model from {model_path}")
            except Exception as exc:
                self.manual_model = None
                self.model_load_error = str(exc)
                print(f"[host] Failed to load manual model from {model_path}: {exc}")
        elif model_path:
            self.model_load_error = f"Model file not found: {model_path}"
            print(f"[host] {self.model_load_error}")
        self.recorder = ManualDriveRecorder(dataset_path)
        self.evidence = EvidenceLogger()
        self.accident_detector = AccidentDetector()
        self.packager = AccidentPackager()
        self.image_root = Path(image_root)
        self.command = ManualCommandState()
        self.mode = "manual"
        self.latest_frame: SensorFrame | None = None
        self.latest_image_path: Path | None = None
        self.latest_image_data: bytes | None = None
        self.latest_image_content_type = "image/jpeg"
        self.latest_image_updated_at = 0.0
        self.latest_gap_metrics: dict[int, dict] = {}
        self.latest_suggestion: dict | None = None
        self.latest_command_decision: Decision | None = None
        self.latest_accident_report_path: str | None = None

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

    def update_mode(self, payload: dict) -> dict:
        requested = str(payload.get("mode", self.mode)).lower()
        if requested == "auto" and self.manual_model is None:
            return {
                "mode": self.mode,
                "model_loaded": False,
                "error": self.model_load_error or "No manual model loaded; cannot enable autonomous mode.",
            }
        if requested in ("manual", "auto"):
            self.mode = requested
            print(f"[host] Switched to {self.mode} mode")
        return {"mode": self.mode, "model_loaded": self.manual_model is not None}

    def state(self) -> dict:
        return {
            "command": self.command.__dict__,
            "mode": self.mode,
            "model_loaded": self.manual_model is not None,
            "model_load_error": self.model_load_error,
            "latest_frame": self.latest_frame.__dict__ if self.latest_frame else None,
            "latest_image_url": "/api/v1/latest-image?vehicle=latest" if self.latest_image_data else None,
            "latest_image_updated_at": self.latest_image_updated_at,
            "latest_gap_metrics": self.latest_gap_metrics,
            "latest_suggestion": self.latest_suggestion,
            "latest_command_decision": self._decision_dict(self.latest_command_decision) if self.latest_command_decision else None,
            "latest_accident_report_path": self.latest_accident_report_path,
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

        command_for_response, decision = self._resolve_command(frame, suggestion)
        self.latest_command_decision = decision
        self.recorder.append(vehicle_id, frame, command_for_response, scan_metrics, best_gap_angle, best_gap_score)

        self.evidence.observe(frame, decision)

        event_recorded = False
        accident_report_path = None
        if self.evidence.event_needed(frame, decision):
            self.evidence.write_event(decision.reason_code.value, frame, decision, mode=self.mode)
            event_recorded = True
        if self.accident_detector.is_collision(frame):
            package = self.packager.create(frame, decision, self.evidence, mode=self.mode)
            accident_report_path = str(generate_report(package))
            self.latest_accident_report_path = accident_report_path

        if self.command.sweep_requested:
            self.command = ManualCommandState(
                speed_cm_s=self.command.speed_cm_s,
                steering=self.command.steering,
                direction=self.command.direction,
                servo_angle=self.command.servo_angle,
                stop=self.command.stop,
                sweep_requested=False,
            )

        action_label = "stop" if command_for_response.stop else ("autonomous" if self.mode == "auto" else "manual")

        return HostCommand(
            action=action_label,
            speed=self._pwm_from_cm_s(command_for_response.speed_cm_s),
            servo_angle=command_for_response.servo_angle,
            probabilities=decision.probabilities,
            reason_code=decision.reason_code.value,
            explanation=decision.explanation,
            speed_cm_s=command_for_response.speed_cm_s,
            steering=command_for_response.steering,
            direction=command_for_response.direction,
            stop=command_for_response.stop,
            sweep_requested=command_for_response.sweep_requested,
            event_recorded=event_recorded,
            accident_report_path=accident_report_path,
            mode=self.mode,
        )

    def _resolve_command(self, frame: SensorFrame, suggestion: Decision) -> tuple[ManualCommandState, Decision]:
        probabilities = suggestion.probabilities
        second_best_action = suggestion.second_best_action

        if self.mode == "auto" and self.manual_model is not None:
            # Hybrid safety override: rule-based obstacle avoidance wins over the learned model
            # because the collected dataset does not yet show consistent obstacle-avoidance steering.
            obstacle_command, obstacle_reason, obstacle_explanation = self._obstacle_avoidance(frame)
            if obstacle_command is not None:
                action = self._action_from_steering(obstacle_command.steering, obstacle_command.stop)
                decision = Decision(
                    action=action,
                    reason_code=obstacle_reason,
                    speed=obstacle_command.speed_cm_s,
                    probabilities=probabilities,
                    second_best_action=second_best_action,
                    explanation=obstacle_explanation,
                )
                return obstacle_command, decision

            try:
                pred = self.manual_model.predict(frame)
            except Exception as exc:
                print(f"[host] Manual model prediction failed: {exc}")
                command = ManualCommandState(
                    speed_cm_s=0.0,
                    steering=0.0,
                    direction="forward",
                    servo_angle=self.command.servo_angle,
                    stop=True,
                    sweep_requested=self.command.sweep_requested,
                ).normalized()
                decision = Decision(
                    action=Action.STOP,
                    reason_code=ReasonCode.EMERGENCY_STOP,
                    speed=0.0,
                    probabilities=probabilities,
                    second_best_action=second_best_action,
                    explanation=f"Autonomous model prediction failed; stopping as a safety fallback. Error: {exc}",
                )
                return command, decision

            # Fallback safety override: expert emergency stop always wins
            if suggestion.action == Action.STOP and suggestion.reason_code == ReasonCode.EMERGENCY_STOP:
                auto_stop = True
                reason_code = ReasonCode.EMERGENCY_STOP
                explanation = (
                    f"Autonomous model overridden by emergency stop. "
                    f"Predicted steering={pred.steering:.2f}, speed={pred.speed_cm_s:.1f} cm/s."
                )
            else:
                auto_stop = pred.stop
                reason_code = suggestion.reason_code
                explanation = (
                    f"Autonomous model active. Steering={pred.steering:.2f}, "
                    f"speed={pred.speed_cm_s:.1f} cm/s, direction={pred.direction}."
                )

            command = ManualCommandState(
                speed_cm_s=0.0 if auto_stop else pred.speed_cm_s,
                steering=pred.steering,
                direction=pred.direction,
                servo_angle=self.command.servo_angle,
                stop=auto_stop,
                sweep_requested=self.command.sweep_requested,
            ).normalized()

            action = self._action_from_steering(pred.steering, auto_stop)
            decision = Decision(
                action=action,
                reason_code=reason_code,
                speed=command.speed_cm_s,
                probabilities=probabilities,
                second_best_action=second_best_action,
                explanation=explanation,
            )
            return command, decision

        # Manual mode
        command = self.command
        action = self._action_from_steering(command.steering, command.stop)
        decision = Decision(
            action=action,
            reason_code=ReasonCode.MANUAL_CONTROL,
            speed=command.speed_cm_s,
            probabilities=probabilities,
            second_best_action=second_best_action,
            explanation="Manual Mac dashboard command is active.",
        )
        return command, decision

    def _action_from_steering(self, steering: float, stop: bool) -> Action:
        if stop:
            return Action.STOP
        if steering <= -0.2:
            return Action.LEFT
        if steering >= 0.2:
            return Action.RIGHT
        return Action.STRAIGHT

    def _obstacle_avoidance(self, frame: SensorFrame) -> tuple[ManualCommandState | None, ReasonCode | None, str | None]:
        """Rule-based override for obstacle avoidance in autonomous mode.

        Returns a (command, reason_code, explanation) tuple when an obstacle
        requires intervention, otherwise (None, None, None).
        """
        emergency_distance = self.runtime.fallback.config.emergency_distance_cm
        safe_speed = 3.0  # slower when near obstacles

        if frame.ultrasonic_distance < emergency_distance:
            return (
                ManualCommandState(
                    speed_cm_s=0.0,
                    steering=0.0,
                    direction="forward",
                    servo_angle=self.command.servo_angle,
                    stop=True,
                    sweep_requested=self.command.sweep_requested,
                ).normalized(),
                ReasonCode.EMERGENCY_STOP,
                f"Ultrasonic distance {frame.ultrasonic_distance:.1f} cm below emergency threshold {emergency_distance:.1f} cm; stopping.",
            )

        if frame.ir_center:
            # Front obstacle: steer toward the side with more free space.
            if frame.left_gap_score >= frame.right_gap_score:
                steering = -0.75  # turn left
                reason = ReasonCode.FRONT_OBSTACLE_LEFT_GAP
                explanation = "Front obstacle detected; steering left toward the larger gap."
            else:
                steering = 0.75  # turn right
                reason = ReasonCode.FRONT_OBSTACLE_RIGHT_GAP
                explanation = "Front obstacle detected; steering right toward the larger gap."
            return (
                ManualCommandState(
                    speed_cm_s=safe_speed,
                    steering=steering,
                    direction="forward",
                    servo_angle=self.command.servo_angle,
                    stop=False,
                    sweep_requested=self.command.sweep_requested,
                ).normalized(),
                reason,
                explanation,
            )

        if frame.ir_left:
            return (
                ManualCommandState(
                    speed_cm_s=safe_speed,
                    steering=0.75,  # steer right away from left obstacle
                    direction="forward",
                    servo_angle=self.command.servo_angle,
                    stop=False,
                    sweep_requested=self.command.sweep_requested,
                ).normalized(),
                ReasonCode.LEFT_OBSTACLE,
                "Left obstacle detected; steering right to avoid.",
            )

        if frame.ir_right:
            return (
                ManualCommandState(
                    speed_cm_s=safe_speed,
                    steering=-0.75,  # steer left away from right obstacle
                    direction="forward",
                    servo_angle=self.command.servo_angle,
                    stop=False,
                    sweep_requested=self.command.sweep_requested,
                ).normalized(),
                ReasonCode.RIGHT_OBSTACLE,
                "Right obstacle detected; steering left to avoid.",
            )

        return None, None, None

    def _decision_dict(self, decision: Decision | None) -> dict | None:
        if decision is None:
            return None
        return {
            "action": decision.action.value,
            "reason_code": decision.reason_code.value,
            "speed": decision.speed,
            "probabilities": decision.probabilities,
            "second_best_action": decision.second_best_action.value,
            "explanation": decision.explanation,
        }

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
