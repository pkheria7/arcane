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
        display_only: bool = False,
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
        self.display_only = display_only
        self.command = ManualCommandState()
        self.mode = "manual"
        self.auto_state = "drive"
        self.auto_state_start = 0.0
        self.turn_direction = 0
        self.stop_scan_duration = 0.0  # no delay; turn immediately on obstacle
        self.turn_duration = 0.6
        self.recover_duration = 0.3
        self.last_left_gap_score = 0.5
        self.last_right_gap_score = 0.5
        self.latest_frame: SensorFrame | None = None
        self.latest_image_path: Path | None = None
        self.latest_image_data: bytes | None = None
        self.latest_image_content_type = "image/jpeg"
        self.latest_image_updated_at = 0.0
        self.latest_gap_metrics: dict[int, dict] = {}
        self.latest_front_gap_metrics: dict = {}
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
            if self.mode != requested:
                self.mode = requested
                self._reset_auto_state()
                print(f"[host] Switched to {self.mode} mode")
        return {"mode": self.mode, "model_loaded": self.manual_model is not None}

    def state(self) -> dict:
        return {
            "command": self.command.__dict__,
            "display_only": self.display_only,
            "mode": self.mode,
            "auto_state": self.auto_state,
            "model_loaded": self.manual_model is not None,
            "model_load_error": self.model_load_error,
            "latest_frame": self.latest_frame.__dict__ if self.latest_frame else None,
            "latest_image_url": "/api/v1/latest-image?vehicle=latest" if self.latest_image_data else None,
            "latest_image_updated_at": self.latest_image_updated_at,
            "latest_gap_metrics": self.latest_gap_metrics,
            "latest_front_gap_metrics": self.latest_front_gap_metrics,
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

        front_gap_metrics = self._front_gap_metrics(image_path)
        self.latest_front_gap_metrics = front_gap_metrics

        scan_scores, scan_metrics = self._scan_scores(packet.get("scan_images") or [], upload_dir)
        has_scan_scores = bool(scan_scores)
        if scan_scores:
            frame_data["left_gap_score"] = scan_scores.get(135, (0.0, 0.0, 0.0))[0]
            frame_data["center_gap_score"] = scan_scores.get(90, (0.0, 0.5, 0.0))[1]
            frame_data["right_gap_score"] = scan_scores.get(45, (0.0, 0.0, 0.0))[2]
            self.last_left_gap_score = float(frame_data["left_gap_score"])
            self.last_right_gap_score = float(frame_data["right_gap_score"])
        else:
            frame_data["left_gap_score"] = self.last_left_gap_score
            frame_data["center_gap_score"] = 0.5
            frame_data["right_gap_score"] = self.last_right_gap_score

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
            "front_free_space_score": front_gap_metrics.get("free_space_score", 0.5),
        }

        pi_command_dict = packet.get("command")
        command_for_response, decision = self._resolve_command(
            frame, suggestion, has_scan_scores, front_gap_metrics, pi_command_dict
        )
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

        if self.display_only:
            return HostCommand(
                action="display",
                speed=0.0,
                servo_angle=command_for_response.servo_angle,
                probabilities=decision.probabilities,
                reason_code=decision.reason_code.value,
                explanation=f"Pi-local autonomy is active. Observed command: {decision.explanation}",
                speed_cm_s=0.0,
                steering=0.0,
                direction="forward",
                stop=True,
                sweep_requested=False,
                event_recorded=event_recorded,
                accident_report_path=accident_report_path,
                mode=self.mode,
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

    def _resolve_command(
        self,
        frame: SensorFrame,
        suggestion: Decision,
        has_scan_scores: bool = False,
        front_gap_metrics: dict | None = None,
        pi_command_dict: dict | None = None,
    ) -> tuple[ManualCommandState, Decision]:
        probabilities = suggestion.probabilities
        second_best_action = suggestion.second_best_action
        front_gap_metrics = front_gap_metrics or {}

        if self.display_only:
            return self._display_only_command(frame, suggestion, pi_command_dict)

        if self.mode == "auto" and self.manual_model is not None:
            return self._auto_state_machine(frame, suggestion, has_scan_scores, front_gap_metrics)

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

    def _display_only_command(
        self,
        frame: SensorFrame,
        suggestion: Decision,
        pi_command_dict: dict | None,
    ) -> tuple[ManualCommandState, Decision]:
        """In display-only mode the Pi is the authority; mirror its command for the UI."""
        if pi_command_dict:
            command = ManualCommandState(
                speed_cm_s=float(pi_command_dict.get("speed_cm_s", 0.0)),
                steering=float(pi_command_dict.get("steering", 0.0)),
                direction=str(pi_command_dict.get("direction", "forward")),
                servo_angle=int(pi_command_dict.get("servo_angle", self.command.servo_angle)),
                stop=bool(pi_command_dict.get("stop", True)),
                sweep_requested=False,
            ).normalized()
            action = self._action_from_steering(command.steering, command.stop)
            explanation = (
                f"Pi-local autonomy command mirrored on Mac display. "
                f"action={action.value}, speed={command.speed_cm_s:.1f} cm/s, "
                f"steering={command.steering:+.2f}, servo={command.servo_angle}."
            )
        else:
            command = ManualCommandState(
                speed_cm_s=0.0,
                steering=0.0,
                direction="forward",
                servo_angle=self.command.servo_angle,
                stop=True,
                sweep_requested=False,
            ).normalized()
            action = Action.STOP
            explanation = "Display-only mode; no Pi command received yet."

        self.command = command
        decision = Decision(
            action=action,
            reason_code=suggestion.reason_code,
            speed=command.speed_cm_s,
            probabilities=suggestion.probabilities,
            second_best_action=suggestion.second_best_action,
            explanation=explanation,
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

    def _reset_auto_state(self) -> None:
        self.auto_state = "drive"
        self.auto_state_start = 0.0
        self.turn_direction = 0

    def _is_front_blocked(self, frame: SensorFrame, front_gap_metrics: dict) -> bool:
        emergency_distance = self.runtime.fallback.config.emergency_distance_cm
        front_free_space = float(front_gap_metrics.get("free_space_score", 1.0))
        return (
            frame.ultrasonic_distance < emergency_distance
            or bool(frame.ir_center)
            or front_free_space < 0.35
        )

    def _choose_turn_direction(self, frame: SensorFrame, has_scan_scores: bool) -> int:
        """Return -1 for left turn, +1 for right turn."""
        if has_scan_scores:
            return -1 if frame.left_gap_score >= frame.right_gap_score else 1
        return 1  # default to right if no gap data

    def _auto_state_machine(
        self,
        frame: SensorFrame,
        suggestion: Decision,
        has_scan_scores: bool,
        front_gap_metrics: dict,
    ) -> tuple[ManualCommandState, Decision]:
        """Stateful obstacle avoidance: drive -> stop/scan -> full-power turn -> recover."""
        probabilities = suggestion.probabilities
        second_best_action = suggestion.second_best_action
        front_blocked = self._is_front_blocked(frame, front_gap_metrics)
        now = time()

        # State transitions
        if self.auto_state == "drive":
            if front_blocked:
                self.auto_state = "stop_scan"
                self.auto_state_start = now
                self.turn_direction = 0
                print(f"[host] auto: drive -> stop_scan")

        elif self.auto_state == "stop_scan":
            if not front_blocked:
                self.auto_state = "drive"
                print(f"[host] auto: stop_scan -> drive (cleared)")
            elif now - self.auto_state_start >= self.stop_scan_duration:
                self.turn_direction = self._choose_turn_direction(frame, has_scan_scores)
                self.auto_state = "turn"
                self.auto_state_start = now
                print(f"[host] auto: stop_scan -> turn ({'left' if self.turn_direction < 0 else 'right'})")

        elif self.auto_state == "turn":
            if now - self.auto_state_start >= self.turn_duration:
                self.auto_state = "recover"
                self.auto_state_start = now
                print(f"[host] auto: turn -> recover")

        elif self.auto_state == "recover":
            if now - self.auto_state_start >= self.recover_duration:
                self.auto_state = "drive"
                print(f"[host] auto: recover -> drive")

        # Generate command from current state
        if self.auto_state == "drive":
            return self._model_command(frame, suggestion)

        if self.auto_state == "stop_scan":
            return self._stop_and_scan_command(frame, front_gap_metrics, has_scan_scores)

        if self.auto_state == "turn":
            return self._turn_command(suggestion, has_scan_scores)

        # recover
        return self._recover_command(suggestion)

    def _stop_and_scan_command(
        self,
        frame: SensorFrame,
        front_gap_metrics: dict,
        has_scan_scores: bool,
    ) -> tuple[ManualCommandState, Decision]:
        probabilities = self.latest_suggestion.get("probabilities", {}) if self.latest_suggestion else {}
        suggestion = self.runtime.decide(frame)
        front_free_space = float(front_gap_metrics.get("free_space_score", 1.0))
        command = ManualCommandState(
            speed_cm_s=0.0,
            steering=0.0,
            direction="forward",
            servo_angle=self.command.servo_angle,
            stop=True,
            sweep_requested=not has_scan_scores,
        ).normalized()
        decision = Decision(
            action=Action.STOP,
            reason_code=ReasonCode.NO_SAFE_PATH,
            speed=0.0,
            probabilities=suggestion.probabilities,
            second_best_action=suggestion.second_best_action,
            explanation=(
                f"Front blocked (free_space={front_free_space:.2f}, "
                f"ultrasonic={frame.ultrasonic_distance:.1f} cm, center_ir={frame.ir_center}); "
                f"stopping and scanning for {self.stop_scan_duration:.1f}s."
            ),
        )
        return command, decision

    def _turn_command(self, suggestion: Decision, has_scan_scores: bool = False) -> tuple[ManualCommandState, Decision]:
        # Full-power pivot turn using all four wheels.
        steering = float(self.turn_direction) * 1.0
        command = ManualCommandState(
            speed_cm_s=5.0,
            steering=steering,
            direction="forward",
            servo_angle=self.command.servo_angle,
            stop=False,
            # Keep requesting sweeps until we have fresh gap scores for next time.
            sweep_requested=not has_scan_scores,
        ).normalized()
        direction_label = "right" if self.turn_direction > 0 else "left"
        action = Action.RIGHT if self.turn_direction > 0 else Action.LEFT
        decision = Decision(
            action=action,
            reason_code=ReasonCode.FRONT_OBSTACLE_LEFT_GAP if self.turn_direction < 0 else ReasonCode.FRONT_OBSTACLE_RIGHT_GAP,
            speed=5.0,
            probabilities=suggestion.probabilities,
            second_best_action=suggestion.second_best_action,
            explanation=f"Full-power {direction_label} turn to avoid obstacle (steering={steering:+.2f}, speed=5.0 cm/s).",
        )
        return command, decision

    def _recover_command(self, suggestion: Decision) -> tuple[ManualCommandState, Decision]:
        command = ManualCommandState(
            speed_cm_s=5.0,
            steering=0.0,
            direction="forward",
            servo_angle=self.command.servo_angle,
            stop=False,
            sweep_requested=False,
        ).normalized()
        decision = Decision(
            action=Action.STRAIGHT,
            reason_code=ReasonCode.CLEAR_PATH,
            speed=5.0,
            probabilities=suggestion.probabilities,
            second_best_action=suggestion.second_best_action,
            explanation="Obstacle avoided; moving forward.",
        )
        return command, decision

    def _model_command(self, frame: SensorFrame, suggestion: Decision) -> tuple[ManualCommandState, Decision]:
        probabilities = suggestion.probabilities
        second_best_action = suggestion.second_best_action
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
                sweep_requested=False,
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
            sweep_requested=False,
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

    def _front_gap_metrics(self, image_path: Path | None) -> dict:
        if image_path is None:
            return {"free_space_score": 1.0, "obstacle_score": 0.0, "passable": True}
        return analyze_gap(str(image_path))

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
