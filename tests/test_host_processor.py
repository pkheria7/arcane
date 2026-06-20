from host_server.processing import HostProcessor
from sensor_layer.types import SensorFrame


def test_host_processor_returns_command_and_logs_dataset(tmp_path):
    processor = HostProcessor(dataset_path=str(tmp_path / "drive.csv"), image_root=str(tmp_path / "images"))
    processor.update_command({"stop": False, "speed_cm_s": 3, "steering": 0.25, "servo_angle": 30})
    packet = {"vehicle_id": "test-car", "frame": SensorFrame.empty().__dict__, "image": None, "scan_images": []}
    command = processor.process_packet(packet)
    assert command.action == "manual"
    assert command.reason_code == "manual_control"
    assert command.speed_cm_s == 3.0
    assert command.steering == 0.25
    assert (tmp_path / "drive.csv").exists()


def test_host_processor_uses_scan_images_for_center_obstacle(tmp_path):
    processor = HostProcessor(dataset_path=str(tmp_path / "drive.csv"), image_root=str(tmp_path / "images"))
    frame = SensorFrame.empty().__dict__ | {"ir_center": 1, "ultrasonic_distance": 80.0}
    packet = {"vehicle_id": "test-car", "frame": frame, "image": None, "scan_images": []}
    command = processor.process_packet(packet)
    assert command.action == "stop"
    assert command.reason_code == "manual_control"
    assert processor.latest_suggestion is not None
    assert processor.latest_suggestion["action"] == "left"


def test_sweep_request_is_one_shot(tmp_path):
    processor = HostProcessor(dataset_path=str(tmp_path / "drive.csv"), image_root=str(tmp_path / "images"))
    processor.update_command({"sweep_requested": True})
    packet = {"vehicle_id": "test-car", "frame": SensorFrame.empty().__dict__, "image": None, "scan_images": []}
    first = processor.process_packet(packet)
    second = processor.process_packet(packet)
    assert first.sweep_requested is True
    assert second.sweep_requested is False
