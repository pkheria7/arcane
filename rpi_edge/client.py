from __future__ import annotations

import argparse
import json
from socket import timeout as SocketTimeout
from pathlib import Path
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from edge_protocol.messages import EdgePacket, ImagePayload
from sensor_layer.config import load_vehicle_config
from sensor_layer.gpio_factory import GpioFactoryError, configure_gpiozero_pin_factory
from sensor_layer.actuators import PiMotorDriver, PiServo, SimulatedMotorDriver, SimulatedServo
from sensor_layer.sensors import PiSensorSuite, SimulatedSensorSuite


SERVO_FRONT = 90
SERVO_LEFT = 180
SERVO_RIGHT = 0
SCAN_ANGLES = (45, 90, 135)
MAX_SPEED_CM_S = 5.0
GAP_SCAN_DISTANCE_CM = 200.0
STEERING_DEADZONE = 0.08
FULL_TURN_THRESHOLD = 0.72
SLIGHT_TURN_MIN_INNER_RATIO = 0.22
PIVOT_INNER_REVERSE_RATIO = 0.65


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
    if frame.ultrasonic_distance < GAP_SCAN_DISTANCE_CM:
        return
    if frame.ir_left:
        servo.set_angle(SERVO_LEFT)
    elif frame.ir_right:
        servo.set_angle(SERVO_RIGHT)
    elif frame.ir_center:
        servo.set_angle(SERVO_FRONT)
    else:
        servo.set_angle(SERVO_FRONT)


def capture_gap_scan(sensors, servo, image_dir: Path, jpeg_quality: int, prefix: str) -> list[ImagePayload]:
    scan_images = []
    for angle in SCAN_ANGLES:
        servo.set_angle(angle)
        scan = capture_payload(sensors, servo, image_dir, f"{prefix}_{angle}", jpeg_quality)
        if scan:
            scan_images.append(scan)
    return scan_images


def build_packet(vehicle_id: str, sensors, servo, image_dir: Path, send_camera: bool, jpeg_quality: int) -> EdgePacket:
    frame = sensors.read_frame(servo_angle=getattr(servo, "angle", 0), image_path=None)
    set_servo_for_obstacles(servo, frame)
    image = capture_payload(sensors, servo, image_dir, "edge_cycle", jpeg_quality) if send_camera else None
    frame = frame.__class__(**{**frame.__dict__, "servo_angle": getattr(servo, "angle", 0)})
    scan_images = []
    if send_camera and frame.ultrasonic_distance < GAP_SCAN_DISTANCE_CM:
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
    print(f"[edge] Posting telemetry to {host_url.rstrip('/')}/api/v1/cycle", flush=True)
    try:
        while True:
            packet = build_packet(vehicle_id, sensors, servo, image_dir, send_camera, jpeg_quality)
            command = safe_post_packet(host_url, packet, timeout)
            if command is None:
                motor.stop()
                sleep(max(cycle_delay, 0.5))
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
    parser.add_argument("--cycle-delay", type=float, default=0.35)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--pin-factory", default="auto", choices=["auto", "lgpio", "pigpio", "rpigpio", "native"])
    parser.add_argument("--no-camera", action="store_true", help="Send sensor telemetry without camera frames for motor/control testing.")
    parser.add_argument("--camera-width", type=int, default=320)
    parser.add_argument("--camera-height", type=int, default=240)
    parser.add_argument("--jpeg-quality", type=int, default=45)
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
    )


if __name__ == "__main__":
    main()
