from rpi_edge.client import GAP_SCAN_DISTANCE_CM, SERVO_LEFT, SERVO_RIGHT, set_servo_for_obstacles
from sensor_layer.types import SensorFrame


class FakeServo:
    def __init__(self):
        self.angle = 0
        self.calls = []

    def set_angle(self, angle: int) -> None:
        self.angle = angle
        self.calls.append(angle)


def frame(**updates):
    data = SensorFrame.empty().__dict__ | updates
    return SensorFrame(**data)


def test_left_ir_moves_camera_left():
    servo = FakeServo()
    set_servo_for_obstacles(servo, frame(ir_left=1, ultrasonic_distance=999.0))
    assert servo.calls == [SERVO_LEFT]


def test_right_ir_moves_camera_right():
    servo = FakeServo()
    set_servo_for_obstacles(servo, frame(ir_right=1, ultrasonic_distance=999.0))
    assert servo.calls == [SERVO_RIGHT]


def test_no_ir_obstacle_points_camera_front():
    servo = FakeServo()
    set_servo_for_obstacles(servo, frame(ultrasonic_distance=GAP_SCAN_DISTANCE_CM - 1))
    assert servo.calls == [90]
