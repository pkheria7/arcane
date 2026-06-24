from __future__ import annotations

import argparse
from time import sleep, time

from .config import AppConfig, RuntimeConfig
from .controller import RuleController
from .hardware import PiHardware, SimulatedHardware
from .models import SensorSnapshot, Telemetry
from .motors import FourMotorDriver, SimulatedFourMotorDriver
from .ui_server import SharedState, start_ui_server
from .vision import score_jpeg


def servo_for_state(state: str, turn_direction: int) -> int:
    if state in {"scan", "pivot", "reverse"}:
        return 180 if turn_direction < 0 else 0
    return 90


def scan_gaps(hardware, config: AppConfig, sensors: SensorSnapshot) -> tuple[SensorSnapshot, bytes | None]:
    scores: dict[int, float] = {}
    latest_jpeg: bytes | None = None
    for angle in config.autonomy.scan_angles:
        hardware.set_servo(angle)
        latest_jpeg = hardware.capture_camera()
        gap = score_jpeg(latest_jpeg)
        scores[angle] = gap.center
    hardware.set_servo(90)
    left_angle, center_angle, right_angle = config.autonomy.scan_angles
    return (
        SensorSnapshot(
            **{
                **sensors.__dict__,
                "servo_angle": 90,
                "camera_ok": True,
                "left_gap": scores.get(left_angle, sensors.left_gap),
                "center_gap": scores.get(center_angle, sensors.center_gap),
                "right_gap": scores.get(right_angle, sensors.right_gap),
            }
        ),
        latest_jpeg,
    )


def run(config: AppConfig, simulate: bool = False, no_ui: bool = False) -> None:
    shared = SharedState()
    server = None
    if not no_ui:
        try:
            server = start_ui_server(shared, config.runtime.host, config.runtime.port)
            print(f"[finally] UI listening on http://{config.runtime.host}:{config.runtime.port}", flush=True)
        except Exception as exc:
            print(f"[finally] UI failed to start; autonomy continues: {exc}", flush=True)

    hardware = SimulatedHardware(config) if simulate else PiHardware(config)
    motors = SimulatedFourMotorDriver() if simulate else FourMotorDriver(config)
    controller = RuleController(config.autonomy)
    camera_interval = 1.0 / max(0.1, config.runtime.camera_hz)
    control_interval = 1.0 / max(1.0, config.runtime.control_hz)
    next_camera = 0.0
    last_loop = time()
    telemetry = Telemetry()

    try:
        while telemetry.running:
            loop_start = time()
            if loop_start >= next_camera:
                jpeg = hardware.capture_camera()
                if jpeg:
                    telemetry.last_camera_jpeg = jpeg
                    telemetry.camera_updated_at = loop_start
                next_camera = loop_start + camera_interval

            try:
                sensors = hardware.read_sensors()
                emergency_stop = shared.snapshot().emergency_stop
                if controller.state == "scan":
                    sensors, scan_jpeg = scan_gaps(hardware, config, sensors)
                    if scan_jpeg:
                        telemetry.last_camera_jpeg = scan_jpeg
                        telemetry.camera_updated_at = time()
                decision = controller.update(sensors, emergency_stop=emergency_stop, now=loop_start)
                hardware.set_servo(servo_for_state(decision.state, decision.turn_direction))
                telemetry.emergency_stop = emergency_stop
                if emergency_stop:
                    motors.stop()
                    command = motors.last_command if hasattr(motors, "last_command") else decision.command
                    reason = "Emergency stop active from UI."
                    state = "emergency_stop"
                else:
                    motors.apply(decision.command)
                    command = decision.command
                    reason = decision.reason
                    state = decision.state

                dt = max(1e-6, loop_start - last_loop)
                last_loop = loop_start
                telemetry.sensors = sensors
                telemetry.command = command
                telemetry.state = state
                telemetry.reason = reason
                telemetry.loop_hz = 1.0 / dt
                telemetry.error = sensors.error
                shared.update(telemetry)
            except Exception as exc:
                motors.stop()
                telemetry.state = "fault_stop"
                telemetry.reason = "Sensor/control fault; motors stopped."
                telemetry.error = str(exc)
                shared.update(telemetry)
                sleep(0.2)

            elapsed = time() - loop_start
            sleep(max(0.0, control_interval - elapsed))
    except KeyboardInterrupt:
        print("\n[finally] stopping", flush=True)
    finally:
        motors.stop()
        hardware.close()
        if server:
            server.shutdown()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pi-only ARCANE rule-based vehicle.")
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--no-ui", action="store_true")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--control-hz", type=float, default=14.0)
    parser.add_argument("--camera-hz", type=float, default=3.0)
    parser.add_argument("--camera-width", type=int, default=160)
    parser.add_argument("--camera-height", type=int, default=120)
    parser.add_argument("--pin-factory", default="auto")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = AppConfig(
        runtime=RuntimeConfig(
            host=args.host,
            port=args.port,
            control_hz=args.control_hz,
            camera_hz=args.camera_hz,
            camera_width=args.camera_width,
            camera_height=args.camera_height,
            pin_factory=args.pin_factory,
        )
    )
    run(config, simulate=args.simulate, no_ui=args.no_ui)


if __name__ == "__main__":
    main()
