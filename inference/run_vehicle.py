from __future__ import annotations

import argparse
from pathlib import Path
from time import sleep

from accident_reports.detector import AccidentDetector
from accident_reports.package import AccidentPackager
from dataset.collector import DatasetLogger
from event_logger.evidence import EvidenceLogger
from explainability.report_generator import generate_report
from navigation_ai.expert_controller import ExpertController
from navigation_ai.gap_detector import image_gap_scores
from sensor_layer.actuators import PiMotorDriver, PiServo, SimulatedMotorDriver, SimulatedServo
from sensor_layer.config import load_vehicle_config
from sensor_layer.sensors import PiSensorSuite, SimulatedSensorSuite

from .runtime import NavigationRuntime


def apply_action(motor, decision) -> None:
    if decision.action.value == "left":
        motor.left(decision.speed)
    elif decision.action.value == "right":
        motor.right(decision.speed)
    elif decision.action.value == "straight":
        motor.forward(decision.speed)
    else:
        motor.stop()


def run(simulate: bool, model_path: str | None, dataset_path: str, cycle_delay: float) -> None:
    if simulate:
        sensors = SimulatedSensorSuite()
        motor = SimulatedMotorDriver()
        servo = SimulatedServo()
    else:
        cfg = load_vehicle_config()
        gpio = cfg["gpio"]
        sensors = PiSensorSuite(
            ir_left=gpio["ir"]["left"],
            ir_center=gpio["ir"]["center"],
            ir_right=gpio["ir"]["right"],
            trig=gpio["ultrasonic"]["trig"],
            echo=gpio["ultrasonic"]["echo"],
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
        )
        servo = PiServo(pin=gpio["servo"])

    expert = ExpertController()
    runtime = NavigationRuntime(model_path=model_path, fallback=expert)
    dataset = DatasetLogger(dataset_path)
    evidence = EvidenceLogger()
    accident_detector = AccidentDetector()
    packager = AccidentPackager()
    image_dir = Path("dataset/images")

    try:
        while True:
            image_path = sensors.capture_image(image_dir, "cycle")
            frame = sensors.read_frame(servo_angle=getattr(servo, "angle", 0), image_path=image_path)
            if frame.ir_center:
                scan_scores = {}
                for angle in (-60, -30, 0, 30, 60):
                    servo.set_angle(angle)
                    scan_image = sensors.capture_image(image_dir, f"scan_{angle}")
                    scan_scores[angle] = image_gap_scores(scan_image)
                left_gap = max(scan_scores[-60][0], scan_scores[-30][0])
                center_gap = scan_scores[0][1]
                right_gap = max(scan_scores[30][2], scan_scores[60][2])
                frame = frame.__class__(**{**frame.__dict__, "left_gap_score": left_gap, "center_gap_score": center_gap, "right_gap_score": right_gap})
            else:
                left_gap, center_gap, right_gap = image_gap_scores(image_path)
                frame = frame.__class__(**{**frame.__dict__, "left_gap_score": left_gap, "center_gap_score": center_gap, "right_gap_score": right_gap})

            if frame.ir_left:
                servo.set_angle(-60)
            elif frame.ir_right:
                servo.set_angle(60)
            else:
                servo.set_angle(0)

            decision = runtime.decide(frame)
            apply_action(motor, decision)
            dataset.append(frame, decision)
            evidence.observe(frame, decision)
            if evidence.event_needed(frame, decision):
                evidence.write_event(decision.reason_code.value, frame, decision)
            if accident_detector.is_collision(frame):
                package = packager.create(frame, decision, evidence)
                generate_report(package)
                motor.stop()
            sleep(cycle_delay)
    except KeyboardInterrupt:
        motor.stop()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--model", default=None)
    parser.add_argument("--dataset", default="dataset/drives/drive_log.csv")
    parser.add_argument("--cycle-delay", type=float, default=0.12)
    args = parser.parse_args()
    run(args.simulate, args.model, args.dataset, args.cycle_delay)


if __name__ == "__main__":
    main()
