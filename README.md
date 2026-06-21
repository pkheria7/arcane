# ARCANE XAV: Explainable Autonomous Vehicle

ARCANE XAV is a Raspberry Pi based autonomous vehicle stack for a small L298N-driven car. The Raspberry Pi acts as a thin edge device for GPIO, sensor sampling, camera capture, and actuation. Your Mac host runs the browser remote control, records real driving data, computes camera gap scores, stores evidence, and later trains/runs behavior-cloning models.

## Hardware Pinout

| Device | GPIO |
| --- | --- |
| L298N #1 ENA PWM (rear left) | 18 |
| L298N #1 IN1 / IN2 | 17 / 27 |
| L298N #1 ENB PWM (rear right) | 19 |
| L298N #1 IN3 / IN4 | 22 / 23 |
| L298N #2 ENA PWM (front left) | 11 |
| L298N #2 IN1 / IN2 | 7 / 8 |
| L298N #2 ENB PWM (front right) | 12 |
| L298N #2 IN3 / IN4 | 9 / 10 |
| Servo | 20 |
| IR left / center / right | 16 / 6 / 5 |
| Ultrasonic trig / echo | 4 / 21 |
| MPU6050 | GPIO2/3 I2C |
| GPS | GPIO14/15 UART |
| Pi Camera | CSI |

## Project Layout

- `sensor_layer/`: GPIO, camera, simulated sensors, motors, servo interfaces.
- `rpi_edge/`: Raspberry Pi client that sends sensor/image packets to the Mac and applies returned commands.
- `host_server/`: Mac host processing API.
- `edge_protocol/`: shared host/edge JSON protocol.
- `navigation_ai/`: expert rules, reason codes, gap scoring.
- `dataset/`: CSV schemas, manual driving recorder, synthetic smoke-test data, feature extraction.
- `training/`: Random Forest, LightGBM, and small neural network training and validation.
- `models/`: exported `.joblib` models and metrics.
- `inference/`: runtime policy and vehicle loop.
- `event_logger/`: evidence history and event packages.
- `accident_reports/`: impact detection and accident package creation.
- `explainability/`: Markdown accident reports.
- `tests/`: regression tests for navigation and evidence behavior.

## Quick Start On Your Mac Host

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m host_server.server --host 0.0.0.0 --port 8765 --dataset dataset/drives/manual_drive_log.csv
```

Open `http://127.0.0.1:8765` in your Mac browser. Keep this running while the Raspberry Pi is driving. The Mac receives sensor packets, shows live camera frames, records your manual commands, stores datasets/evidence, and writes accident reports.

You can test the edge client from the same machine:

```bash
python -m rpi_edge.client --simulate --host-url http://127.0.0.1:8765
```

## Raspberry Pi Setup

```bash
chmod +x scripts/setup_pi.sh
./scripts/setup_pi.sh
```

Enable required interfaces:

```bash
sudo raspi-config
```

Turn on I2C, Serial, and Camera. Disable serial login shell if using GPS on UART, but keep serial hardware enabled.

Run the thin Raspberry Pi edge client. Replace the IP address with your Mac's LAN IP:

```bash
source .venv/bin/activate
python -m rpi_edge.client --host-url http://192.168.1.25:8765 --vehicle-id rpi-car-01
```

If GPIO startup fails on the Pi, install the GPIO backends and reboot:

```bash
sudo apt update
sudo apt install -y python3-lgpio python3-rpi-lgpio
sudo usermod -aG gpio,video,i2c,dialout $USER
sudo reboot
```

Then inside the venv:

```bash
pip install gpiozero smbus2 pyserial
```

If your venv was created before this change, recreate it so apt-installed `lgpio` is visible:

```bash
rm -rf .venv
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install gpiozero smbus2 pyserial
```

To test only the HC-SR04 ultrasonic sensor with the same raw `lgpio` code used by the edge client:

```bash
python scripts/test_ultrasonic_lgpio.py
```

To test the IR sensors with the same polarity used by the edge client:

```bash
python scripts/test_ir_sensors.py
```

To test the camera servo calibration:

```bash
python scripts/test_servo.py
```

The Pi sends IR, ultrasonic, GPS, MPU6050, and camera frames to the Mac. It receives only manual command fields: `speed_cm_s`, `steering`, `servo_angle`, and `stop`, then applies those to the L298N and servo.

## Manual Data Collection

Use the Mac dashboard as the remote control:

- camera servo physical calibration: `90` front, `180` left side, `0` right side
- sweep button: captures all scan angles
- speed modes: `2`, `3`, `4`, `5 cm/s`
- forward/reverse direction buttons
- steering slider: `-1.0` full left to `+1.0` full right
- stop button: immediate manual stop command

Every telemetry cycle is written to `dataset/drives/manual_drive_log.csv`. The main labels are continuous `manual_steering`, `manual_speed_cm_s`, and `manual_direction`; a derived action label is also stored for compatibility.

## Train Models

For real driving behavior cloning, collect manual data first. Then train continuous steering/speed models:

```bash
python -m training.train_manual_models --dataset dataset/drives/manual_drive_log.csv --output models/manual
```

Synthetic data is only for smoke-testing the older autonomous classifier pipeline:

```bash
python -m dataset.build_dataset --output dataset/drives/synthetic_drive_log.csv --rows 800
python -m training.train_models --dataset dataset/drives/synthetic_drive_log.csv --output models
python -m training.validate_model --model models/best_model.joblib --dataset dataset/drives/synthetic_drive_log.csv
```

The training pipeline exports:

- `models/random_forest/model.joblib`
- `models/lightgbm/model.joblib` when LightGBM is installed
- `models/small_neural_network/model.joblib`
- `models/best_model.joblib`
- `models/metrics.json`
- `models/validation/confusion_matrix.png`

Use a trained model on the Mac host when you later enable autonomous inference:

```bash
python -m host_server.server --host 0.0.0.0 --port 8765 --model models/best_model.joblib --dataset dataset/drives/manual_drive_log.csv
```

## Navigation Rules

During manual collection, autonomous navigation is not applied to the motors. The Mac records an autonomous suggestion for later comparison, but your dashboard command is the expert label.

The suggestion engine still implements the requested safety policy:

- clear path: move straight at constant speed
- left IR obstacle: turn camera left, record evidence, avoid left turns, prefer straight
- right IR obstacle: turn camera right, record evidence, avoid right turns, prefer straight
- center/near obstacle: the Pi performs the servo/camera scan at `90, 45, 0, 135, 180`, sends scan frames to the Mac, and the Mac estimates left/right gaps and selects the bypass
- ultrasonic emergency: stop immediately

Every manual cycle stores sensors, image path, continuous steering/speed labels, derived action label, gap metrics, and the current autonomous suggestion.

## Accident Reports

The MPU6050 impact detector watches acceleration and yaw rate. On collision it writes:

- sensor history
- GPS location
- camera evidence path
- selected action
- alternative action probabilities
- reason code
- explainable Markdown report

Reports are written below `accident_reports/packages/`.

## Host/Edge Contract

The Pi posts to `POST /api/v1/cycle` with:

- sensor frame fields
- current camera frame as base64 JPEG
- scan frames as base64 JPEGs when center IR is active or the dashboard sweep button is requested

The Mac returns:

- `action`: `manual` or `stop`
- `speed_cm_s`
- `steering`
- `servo_angle`
- `stop`
- `sweep_requested`
- autonomous suggestion probabilities for visibility

This keeps camera processing, model inference, dataset generation, evidence storage, and reports on the Mac.
