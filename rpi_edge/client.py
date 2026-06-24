from __future__ import annotations

import argparse
import json
from socket import timeout as SocketTimeout
from pathlib import Path
from time import sleep, time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from edge_protocol.messages import EdgePacket, ImagePayload
from navigation_ai.gap_detector import image_gap_scores
from sensor_layer.config import load_vehicle_config
from sensor_layer.gpio_factory import GpioFactoryError, configure_gpiozero_pin_factory
from sensor_layer.actuators import PiMotorDriver, PiServo, SimulatedMotorDriver, SimulatedServo
from sensor_layer.sensors import PiSensorSuite, SimulatedSensorSuite
from sensor_layer.types import SensorFrame


SERVO_FRONT = 90
SERVO_LEFT = 180
SERVO_RIGHT = 0
SCAN_ANGLES = (30, 90, 150)
MAX_SPEED_CM_S = 5.0
GAP_SCAN_DISTANCE_CM = 25.0
EMERGENCY_SCAN_DISTANCE_CM = 25.0
LOCAL_EMERGENCY_STOP_DISTANCE_CM = 15.0
STEERING_DEADZONE = 0.08
FULL_TURN_THRESHOLD = 0.72
SLIGHT_TURN_MIN_INNER_RATIO = 0.22
PIVOT_INNER_REVERSE_RATIO = 0.40

# Autonomy timing / dynamics
TURN_DURATION = 0.30
RECOVER_DURATION = 0.25
SIDE_AVOID_DURATION = 0.25
HARD_STOP_CLEAR_DISTANCE_CM = 25.0
TURN_STEERING = 0.65
AVOID_STEERING = 0.55
AUTO_SPEED_CM_S = 4.0


class LocalAutonomy:
    """Rule-based autonomy state machine that runs entirely on the Pi."""

    def __init__(self, max_speed_cm_s: float = AUTO_SPEED_CM_S) -> None:
        self.max_speed = max_speed_cm_s
        self.state = "drive"
        self.state_start = 0.0
        self.turn_direction = 0
        self.ultrasonic_close_count = 0
        self.ultrasonic_close_threshold = 3

    def update_ultrasonic_filter(self, frame: SensorFrame) -> None:
        """Filter ultrasonic noise by counting consecutive close readings."""
        if frame.ultrasonic_distance < EMERGENCY_SCAN_DISTANCE_CM:
            self.ultrasonic_close_count += 1
        else:
            self.ultrasonic_close_count = 0

    @property
    def ultrasonic_blocked(self) -> bool:
        return self.ultrasonic_close_count >= self.ultrasonic_close_threshold

    def decide(self, frame: SensorFrame) -> dict:
        now = time()
        front_emergency = bool(frame.ir_center) or frame.ultrasonic_distance < LOCAL_EMERGENCY_STOP_DISTANCE_CM
        front_blocked = bool(frame.ir_center) or self.ultrasonic_blocked

        # State transitions
        if self.state == "drive":
            if front_emergency:
                self.state = "hard_stop"
                self.state_start = now
                print(f"[edge] auto: drive -> hard_stop (emergency)", flush=True)
            elif front_blocked:
                self.state = "stop_scan"
                self.state_start = now
                self.turn_direction = 0
                print(f"[edge] auto: drive -> stop_scan", flush=True)
            elif frame.ir_left:
                self.state = "side_avoid_right"
                self.state_start = now
                print(f"[edge] auto: drive -> side_avoid_right (left IR)", flush=True)
            elif frame.ir_right:
                self.state = "side_avoid_left"
                self.state_start = now
                print(f"[edge] auto: drive -> side_avoid_left (right IR)", flush=True)

        elif self.state == "hard_stop":
            cleared = (
                not bool(frame.ir_center)
                and frame.ultrasonic_distance >= HARD_STOP_CLEAR_DISTANCE_CM
            )
            if cleared:
                self.state = "drive"
                print(f"[edge] auto: hard_stop -> drive (cleared)", flush=True)

        elif self.state == "stop_scan":
            if not front_blocked:
                self.state = "drive"
                print(f"[edge] auto: stop_scan -> drive (cleared)", flush=True)
            else:
                # choose direction immediately; no extra delay
                self.turn_direction = self._choose_turn_direction(frame)
                self.state = "turn"
                self.state_start = now
                print(
                    f"[edge] auto: stop_scan -> turn ({'left' if self.turn_direction < 0 else 'right'})",
                    flush=True,
                )

        elif self.state == "turn":
            if now - self.state_start >= TURN_DURATION:
                self.state = "recover"
                self.state_start = now
                print(f"[edge] auto: turn -> recover", flush=True)

        elif self.state in ("side_avoid_left", "side_avoid_right"):
            if now - self.state_start >= SIDE_AVOID_DURATION:
                self.state = "recover"
                self.state_start = now
                print(f"[edge] auto: side_avoid -> recover", flush=True)

        elif self.state == "recover":
            if now - self.state_start >= RECOVER_DURATION:
                self.state = "drive"
                print(f"[edge] auto: recover -> drive", flush=True)

        # Generate command from current state
        return self._command_for_state(frame)

    def _choose_turn_direction(self, frame: SensorFrame) -> int:
        """Return -1 for left turn, +1 for right turn."""
        return -1 if frame.left_gap_score >= frame.right_gap_score else 1

    def _command_for_state(self, frame: SensorFrame) -> dict:
        if self.state == "hard_stop":
            return {
                "action": "stop",
                "stop": True,
                "speed_cm_s": 0.0,
                "steering": 0.0,
                "direction": "forward",
            }

        if self.state == "stop_scan":
            return {
                "action": "stop",
                "stop": True,
                "speed_cm_s": 0.0,
                "steering": 0.0,
                "direction": "forward",
            }

        if self.state == "turn":
            steering = float(self.turn_direction) * TURN_STEERING
            return {
                "action": "right" if self.turn_direction > 0 else "left",
                "stop": False,
                "speed_cm_s": self.max_speed,
                "steering": steering,
                "direction": "forward",
            }

        if self.state == "side_avoid_left":
            return {
                "action": "left",
                "stop": False,
                "speed_cm_s": self.max_speed,
                "steering": -AVOID_STEERING,
                "direction": "forward",
            }

        if self.state == "side_avoid_right":
            return {
                "action": "right",
                "stop": False,
                "speed_cm_s": self.max_speed,
                "steering": AVOID_STEERING,
                "direction": "forward",
            }

        if self.state == "recover":
            return {
                "action": "straight",
                "stop": False,
                "speed_cm_s": self.max_speed,
                "steering": 0.0,
                "direction": "forward",
            }

        # drive state: move straight. Obstacles are handled by state transitions above.
        return {
            "action": "straight",
            "stop": False,
            "speed_cm_s": self.max_speed,
            "steering": 0.0,
            "direction": "forward",
        }

def apply_command(motor, servo, command: dict) -> tuple[float, float]:
    if bool(command.get("stop", False)) or command.get("action") == "stop":
        motor.stop()
        return 0.0, 0.0
    steering = max(-1.0, min(1.0, float(command.get("steering", 0.0) or 0.0)))
    direction = str(command.get("direction", "forward") or "forward")
    speed_cm_s = max(0.0, min(MAX_SPEED_CM_S, float(command.get("speed_cm_s", 0.0) or 0.0)))
    base_pwm = speed_cm_s / MAX_SPEED_CM_S
    left_speed, right_speed = steering_to_motor_mix(base_pwm, steering, direction)
    motor.drive(left_speed, right_speed)
    return left_speed, right_speed


def steering_to_motor_mix(base_pwm: float, steering: float, direction: str = "forward") -> tuple[float, float]:
    base = max(0.0, min(1.0, base_pwm))
    turn = max(-1.0, min(1.0, steering))
    magnitude = abs(turn)
    if magnitude < STEERING_DEADZONE:
        left, right = base, base
    elif magnitude >= FULL_TURN_THRESHOLD:
        if turn < 0:
            left, right = -PIVOT_INNER_REVERSE_RATIO * base, base
        else:
            left, right = base, -PIVOT_INNER_REVERSE_RATIO * base
    elif turn < 0:
        reduction = 1.0 - (magnitude - STEERING_DEADZONE) / (FULL_TURN_THRESHOLD - STEERING_DEADZONE) * (1.0 - SLIGHT_TURN_MIN_INNER_RATIO)
        left, right = base * max(SLIGHT_TURN_MIN_INNER_RATIO, reduction), base
    else:
        reduction = 1.0 - (magnitude - STEERING_DEADZONE) / (FULL_TURN_THRESHOLD - STEERING_DEADZONE) * (1.0 - SLIGHT_TURN_MIN_INNER_RATIO)
        left, right = base, base * max(SLIGHT_TURN_MIN_INNER_RATIO, reduction)
    if direction == "reverse":
        return -left, -right
    return left, right


def post_packet(host_url: str, packet: EdgePacket, timeout: float) -> dict:
    body = json.dumps(packet.to_json_dict()).encode("utf-8")
    request = Request(f"{host_url.rstrip('/')}/api/v1/cycle", data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def safe_post_packet(host_url: str, packet: EdgePacket, timeout: float) -> dict | None:
    try:
        return post_packet(host_url, packet, timeout)
    except (TimeoutError, SocketTimeout) as exc:
        print(f"[edge] host timeout after {timeout:.1f}s: {exc}", flush=True)
    except HTTPError as exc:
        print(f"[edge] host HTTP error {exc.code}: {exc.reason}", flush=True)
    except URLError as exc:
        print(f"[edge] host network error: {exc.reason}", flush=True)
    return None


def capture_payload(sensors, servo, image_dir: Path, prefix: str, quality: int) -> ImagePayload | None:
    angle = getattr(servo, "angle", 0)
    image_bytes = sensors.capture_image_bytes(quality=quality)
    if image_bytes:
        return ImagePayload.from_bytes(image_bytes, angle=angle, filename=f"{prefix}_{int(angle)}.jpg")
    image_path = sensors.capture_image(image_dir, prefix)
    return ImagePayload.from_file(image_path, angle=angle) if image_path else None


def set_servo_for_obstacles(servo, frame) -> None:
    if frame.ir_left:
        servo.set_angle(SERVO_LEFT)
    elif frame.ir_right:
        servo.set_angle(SERVO_RIGHT)
    elif frame.ir_center:
        servo.set_angle(SERVO_FRONT)
    else:
        servo.set_angle(SERVO_FRONT)


def servo_angle_for_obstacles(frame: SensorFrame) -> int:
    if frame.ir_left:
        return SERVO_LEFT
    if frame.ir_right:
        return SERVO_RIGHT
    return SERVO_FRONT


def capture_gap_scan(sensors, servo, image_dir: Path, jpeg_quality: int, prefix: str) -> list[ImagePayload]:
    scan_images = []
    for angle in SCAN_ANGLES:
        servo.set_angle(angle)
        scan = capture_payload(sensors, servo, image_dir, f"{prefix}_{angle}", jpeg_quality)
        if scan:
            scan_images.append(scan)
    return scan_images


def gap_scores_from_scan(scan_images: list[ImagePayload], upload_dir: Path) -> dict[int, tuple[float, float, float]]:
    scores: dict[int, tuple[float, float, float]] = {}
    for image in scan_images:
        path = image.write_to(upload_dir, f"local_scan_{int(time() * 1000)}")
        scores[image.angle] = image_gap_scores(str(path))
    return scores


def frame_with_gap_scores(
    frame: SensorFrame,
    sensors,
    servo,
    image_dir: Path,
    send_camera: bool,
    jpeg_quality: int,
    should_scan: bool = False,
) -> tuple[SensorFrame, ImagePayload | None, list[ImagePayload]]:
    """Capture the current view, run a gap scan if needed, and return an updated frame."""
    # Point camera at obstacle side before capturing evidence frame
    servo.set_angle(servo_angle_for_obstacles(frame))
    cycle_image = capture_payload(sensors, servo, image_dir, "local_cycle", jpeg_quality) if send_camera else None
    frame = frame.__class__(**{**frame.__dict__, "servo_angle": getattr(servo, "angle", 0)})

    # The caller decides whether to scan (e.g. after filtering ultrasonic noise).
    needs_gap_scan = send_camera and should_scan
    scan_images: list[ImagePayload] = []
    if needs_gap_scan:
        scan_images = capture_gap_scan(sensors, servo, image_dir, jpeg_quality, "local_gap_scan")
        scores = gap_scores_from_scan(scan_images, image_dir)
        left_gap = scores.get(150, (0.0, 0.0, 0.0))[0]
        center_gap = scores.get(90, (0.0, 0.5, 0.0))[1]
        right_gap = scores.get(30, (0.0, 0.0, 0.0))[2]
        servo.set_angle(SERVO_FRONT)
    else:
        if cycle_image:
            path = cycle_image.write_to(image_dir, f"local_cycle_{int(time() * 1000)}")
            left_gap, center_gap, right_gap = image_gap_scores(str(path))
        else:
            left_gap, center_gap, right_gap = 0.5, 0.5, 0.5

    frame = frame.__class__(**{
        **frame.__dict__,
        "left_gap_score": left_gap,
        "center_gap_score": center_gap,
        "right_gap_score": right_gap,
        "servo_angle": getattr(servo, "angle", 0),
    })
    return frame, cycle_image, scan_images


def build_packet(
    vehicle_id: str,
    sensors,
    servo,
    image_dir: Path,
    send_camera: bool,
    jpeg_quality: int,
    force_gap_scan: bool = False,
    frame=None,
) -> EdgePacket:
    if frame is None:
        frame = sensors.read_frame(servo_angle=getattr(servo, "angle", 0), image_path=None)
    set_servo_for_obstacles(servo, frame)
    image = capture_payload(sensors, servo, image_dir, "edge_cycle", jpeg_quality) if send_camera else None
    frame = frame.__class__(**{**frame.__dict__, "servo_angle": getattr(servo, "angle", 0)})
    scan_images = []
    needs_gap_scan = (
        force_gap_scan
        or frame.ir_center
        or frame.ultrasonic_distance < EMERGENCY_SCAN_DISTANCE_CM
        or frame.ultrasonic_distance < GAP_SCAN_DISTANCE_CM
    )
    if send_camera and needs_gap_scan:
        scan_images = capture_gap_scan(sensors, servo, image_dir, jpeg_quality, "edge_gap_scan")
        servo.set_angle(SERVO_FRONT)
    return EdgePacket.from_frame(vehicle_id=vehicle_id, frame=frame, image=image, scan_images=scan_images)


def perform_requested_sweep(sensors, servo, image_dir: Path, jpeg_quality: int) -> list[ImagePayload]:
    return capture_gap_scan(sensors, servo, image_dir, jpeg_quality, "edge_manual_sweep")


def run(
    host_url: str,
    vehicle_id: str,
    simulate: bool,
    cycle_delay: float,
    timeout: float,
    pin_factory: str,
    send_camera: bool,
    camera_width: int,
    camera_height: int,
    jpeg_quality: int,
    local_autonomy: bool,
    model_path: str | None,
    max_speed_cm_s: float,
) -> None:
    if simulate:
        sensors = SimulatedSensorSuite()
        motor = SimulatedMotorDriver()
        servo = SimulatedServo()
    else:
        try:
            factory_name = configure_gpiozero_pin_factory(pin_factory)
            print(f"[edge] GPIO pin factory: {factory_name}", flush=True)
            cfg = load_vehicle_config()
            gpio = cfg["gpio"]
            sensors = PiSensorSuite(
                ir_left=gpio["ir"]["left"],
                ir_center=gpio["ir"]["center"],
                ir_right=gpio["ir"]["right"],
                trig=gpio["ultrasonic"]["trig"],
                echo=gpio["ultrasonic"]["echo"],
                pin_factory=pin_factory,
                camera_size=(camera_width, camera_height),
            )
            motor_cfg = gpio["motor"]
            front_cfg = gpio["front_motor"]
            motor = PiMotorDriver(
                ena=motor_cfg["ena_pwm"],
                in1=motor_cfg["in1"],
                in2=motor_cfg["in2"],
                enb=motor_cfg["enb_pwm"],
                in3=motor_cfg["in3"],
                in4=motor_cfg["in4"],
                front_ena=front_cfg["ena_pwm"],
                front_in1=front_cfg["in1"],
                front_in2=front_cfg["in2"],
                front_enb=front_cfg["enb_pwm"],
                front_in3=front_cfg["in3"],
                front_in4=front_cfg["in4"],
                pin_factory=pin_factory,
            )
            servo = PiServo(pin=gpio["servo"], pin_factory=pin_factory)
        except GpioFactoryError as exc:
            print(str(exc), flush=True)
            raise SystemExit(2) from exc

    image_dir = Path("/tmp/arcane_edge_images")
    image_dir.mkdir(parents=True, exist_ok=True)

    autonomy = LocalAutonomy(max_speed_cm_s=max_speed_cm_s) if local_autonomy else None
    print(f"[edge] Posting telemetry to {host_url.rstrip('/')}/api/v1/cycle", flush=True)
    if local_autonomy:
        print("[edge] LOCAL AUTONOMY enabled; Pi is the authority, Mac is display-only", flush=True)

    command: dict = {"stop": True, "action": "stop"}
    try:
        while True:
            frame = sensors.read_frame(servo_angle=getattr(servo, "angle", 0), image_path=None)

            if local_autonomy:
                autonomy.update_ultrasonic_filter(frame)
                should_scan = bool(frame.ir_center) or autonomy.ultrasonic_blocked
                frame, cycle_image, scan_images = frame_with_gap_scores(
                    frame, sensors, servo, image_dir, send_camera, jpeg_quality, should_scan=should_scan
                )
                command = autonomy.decide(frame)
                print(
                    f"[edge] auto: state={autonomy.state} ir={frame.ir_left}{frame.ir_center}{frame.ir_right} "
                    f"us={frame.ultrasonic_distance:.1f}cm gaps=L{frame.left_gap_score:.2f}"
                    f"C{frame.center_gap_score:.2f}R{frame.right_gap_score:.2f} "
                    f"cmd={command['action']}/s={command['steering']:+.2f}",
                    flush=True,
                )
                apply_command(motor, servo, command)

                # The Pi is the authority; the host command is only mirrored for display.
                packet = EdgePacket.from_frame(
                    vehicle_id=vehicle_id,
                    frame=frame,
                    image=cycle_image,
                    scan_images=scan_images,
                    command=command,
                )
                host_command = safe_post_packet(host_url, packet, timeout)
                if host_command:
                    print(
                        f"[edge] auto: host mirrored command={host_command.get('action')} "
                        f"stop={host_command.get('stop')} (Pi authority; not applied)",
                        flush=True,
                    )
            else:
                local_emergency = bool(frame.ir_center) or frame.ultrasonic_distance < LOCAL_EMERGENCY_STOP_DISTANCE_CM
                if local_emergency:
                    motor.stop()
                    print(
                        f"[edge] LOCAL EMERGENCY STOP ir_center={frame.ir_center} "
                        f"ultrasonic={frame.ultrasonic_distance:.1f}cm",
                        flush=True,
                    )

                force_gap_scan = bool(command.get("sweep_requested", False))
                packet = build_packet(
                    vehicle_id,
                    sensors,
                    servo,
                    image_dir,
                    send_camera,
                    jpeg_quality,
                    force_gap_scan=force_gap_scan,
                    frame=frame,
                )
                command = safe_post_packet(host_url, packet, timeout)
                if command is None:
                    motor.stop()
                    sleep(max(cycle_delay, 1.0))
                    command = {"stop": True, "action": "stop"}
                    continue
                left_speed, right_speed = apply_command(motor, servo, command)
                print(
                    "[edge] command="
                    f"action={command.get('action')} stop={command.get('stop')} "
                    f"speed_cm_s={command.get('speed_cm_s')} steering={command.get('steering')} "
                    f"direction={command.get('direction')} "
                    f"left_pwm={left_speed:.2f} right_pwm={right_speed:.2f} "
                    f"servo={getattr(servo, 'angle', command.get('servo_angle'))}",
                    flush=True,
                )

            sleep(cycle_delay)
    except KeyboardInterrupt:
        motor.stop()
    except Exception:
        motor.stop()
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host-url", required=True, help="Mac host URL, for example http://192.168.1.25:8765")
    parser.add_argument("--vehicle-id", default="rpi-car-01")
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--cycle-delay", type=float, default=0.05)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--pin-factory", default="auto", choices=["auto", "lgpio", "pigpio", "rpigpio", "native"])
    parser.add_argument("--no-camera", action="store_true", help="Send sensor telemetry without camera frames for motor/control testing.")
    parser.add_argument("--camera-width", type=int, default=160)
    parser.add_argument("--camera-height", type=int, default=120)
    parser.add_argument("--jpeg-quality", type=int, default=30)
    parser.add_argument("--local-autonomy", action="store_true", help="Run rule-based autonomy on the Pi; Mac is display-only.")
    parser.add_argument("--model", default=None, help="Optional scikit-learn model for local autonomy (default is rule-based).")
    parser.add_argument("--max-speed", type=float, default=AUTO_SPEED_CM_S, help="Maximum autonomous speed in cm/s.")
    args = parser.parse_args()
    run(
        args.host_url,
        args.vehicle_id,
        args.simulate,
        args.cycle_delay,
        args.timeout,
        args.pin_factory,
        not args.no_camera,
        args.camera_width,
        args.camera_height,
        args.jpeg_quality,
        args.local_autonomy,
        args.model,
        args.max_speed,
    )


if __name__ == "__main__":
    main()
