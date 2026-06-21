# ARCANE XAV Knowledge Base

## Overview

**ARCANE XAV** is an explainable autonomous vehicle stack for a small L298N-driven Raspberry Pi car. The architecture splits work across two devices:

- **Raspberry Pi (edge)**: thin client for GPIO, sensor sampling, camera capture, and actuation.
- **Mac (host)**: browser remote control, manual driving data recording, camera gap scoring, evidence storage, model training, and autonomous inference.

> Project name: `arcane-xav`  
> Version: `0.1.0`  
> Python: `>=3.10`

---

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

**Wiring note:** Use a separate motor power supply for the L298N and tie the motor supply ground to the Pi ground. Do **not** power motors from the Pi 5V rail.

---

## Project Layout

- `sensor_layer/` — GPIO, camera, simulated sensors, motors, servo interfaces.
- `rpi_edge/` — Raspberry Pi client that sends sensor/image packets to the Mac and applies returned commands.
- `host_server/` — Mac host processing API.
- `edge_protocol/` — shared host/edge JSON protocol.
- `navigation_ai/` — expert rules, reason codes, gap scoring.
- `dataset/` — CSV schemas, manual driving recorder, synthetic smoke-test data, feature extraction.
- `training/` — Random Forest, LightGBM, and small neural network training and validation.
- `models/` — exported `.joblib` models and metrics.
- `inference/` — runtime policy and vehicle loop.
- `event_logger/` — evidence history and event packages.
- `accident_reports/` — impact detection and accident package creation.
- `explainability/` — Markdown accident reports.
- `tests/` — regression tests for navigation and evidence behavior.
- `scripts/` — setup, start, and hardware test scripts.
- `config/vehicle.yaml` — GPIO pin and navigation parameter configuration.

---

## Mac Host Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m host_server.server --host 0.0.0.0 --port 8765 --dataset dataset/drives/manual_drive_log.csv
```

Open `http://127.0.0.1:8765` in a browser. The dashboard receives telemetry, shows live camera frames, records manual commands, stores datasets/evidence, and writes accident reports.

To enable autonomous inference later, add a trained model:

```bash
python -m host_server.server --host 0.0.0.0 --port 8765 \
  --model models/best_model.joblib \
  --dataset dataset/drives/manual_drive_log.csv
```

Find the Mac's LAN IP with:

```bash
ipconfig getifaddr en0
```

---

## Raspberry Pi Setup

1. Install OS packages and add the user to required groups:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip python3-opencv i2c-tools git python3-lgpio python3-rpi-lgpio
sudo usermod -aG gpio,video,i2c,dialout $USER
sudo reboot
```

2. Enable interfaces via `sudo raspi-config`:
   - Camera
   - I2C (MPU6050)
   - Serial hardware (GPS); disable serial login shell if using GPS on UART.

3. Create the project venv with system site-packages so `lgpio` is visible:

```bash
git clone <repo-url> arcane-xav
cd arcane-xav
./scripts/setup_pi.sh
source .venv/bin/activate
```

4. Run the edge client (replace with the Mac IP):

```bash
python -m rpi_edge.client --host-url http://YOUR_MAC_IP:8765 --vehicle-id rpi-car-01
```

5. Run as a `systemd` service:

```bash
sudo cp scripts/arcane-xav.service /etc/systemd/system/arcane-xav.service
sudo systemctl daemon-reload
sudo systemctl enable --now arcane-xav
sudo journalctl -u arcane-xav -f
```

The service must set:

```ini
Environment=ARCANE_HOST_URL=http://YOUR_MAC_IP:8765
```

### Pi Hardware Tests

| Test | Command |
| --- | --- |
| Ultrasonic sensor (raw lgpio) | `python scripts/test_ultrasonic_lgpio.py` |
| IR sensor polarity | `python scripts/test_ir_sensors.py` |
| Servo calibration | `python scripts/test_servo.py` |

---

## Manual Data Collection

The dashboard is the remote control:

- **Camera servo calibration:** `90` front, `180` left side, `0` right side.
- **Sweep button:** captures all scan angles.
- **Speed modes:** `4`, `5 cm/s`.
- **Direction buttons:** forward / reverse.
- **Steering slider:** `-1.0` full left to `+1.0` full right.
- **Stop button:** immediate manual stop command.

Every telemetry cycle is appended to `dataset/drives/manual_drive_log.csv`.

---

## Dataset Schema

Manual remote-control cycles are stored in `dataset/drives/manual_drive_log.csv`.

| Column | Description |
| --- | --- |
| `timestamp` | Unix timestamp in seconds |
| `ir_left`, `ir_center`, `ir_right` | Normalized binary obstacle signals (`1` = obstacle, `0` = clear) |
| `ultrasonic_distance` | Distance in centimeters |
| `servo_angle` | Camera servo angle (`90` front, `180` left side, `0` right side) |
| `gps_lat`, `gps_lon` | GPS coordinates when available |
| `heading` | IMU-derived heading |
| `acceleration`, `accel_x`, `accel_y`, `accel_z`, `gyro_z` | MPU6050 features |
| `image_path` | Captured frame path |
| `manual_steering` | Continuous steering label from `-1.0` full left to `+1.0` full right |
| `manual_speed_cm_s` | Selected dashboard speed mode |
| `manual_direction` | Manual drive direction: `forward` or `reverse` |
| `manual_stop` | Manual stop state |
| `derived_action` | Direction-aware label: e.g. `straight`, `full_left`, `reverse_straight`, `reverse_full_right`, `stop` |
| `left_gap_score`, `center_gap_score`, `right_gap_score` | Camera-derived free-space estimates |
| `best_gap_angle`, `best_gap_score` | Best passability estimate from the latest scan/current view |
| `gap_metrics_json` | Per-angle free-space, obstacle, narrow-pass, corridor-width, and passability metrics |

An older synthetic/expert classifier schema still exists for pipeline smoke tests, but real training should use the manual dataset.

---

## Training

### Behavior cloning (manual data)

```bash
python -m training.train_manual_models --dataset dataset/drives/manual_drive_log.csv --output models/manual
```

### Synthetic smoke-test pipeline (older classifier)

```bash
python -m dataset.build_dataset --output dataset/drives/synthetic_drive_log.csv --rows 800
python -m training.train_models --dataset dataset/drives/synthetic_drive_log.csv --output models
python -m training.validate_model --model models/best_model.joblib --dataset dataset/drives/synthetic_drive_log.csv
```

### Exported artifacts

- `models/random_forest/model.joblib`
- `models/lightgbm/model.joblib` (when LightGBM is installed)
- `models/small_neural_network/model.joblib`
- `models/best_model.joblib`
- `models/metrics.json`
- `models/validation/confusion_matrix.png`

---

## Navigation Rules

During manual collection, autonomous navigation is **not** applied to the motors; the Mac records an autonomous suggestion for later comparison. The dashboard command is treated as the expert label.

Safety policy suggestions:

- **Clear path:** move straight at constant speed.
- **Left IR obstacle:** turn camera left, record evidence, avoid left turns, prefer straight.
- **Right IR obstacle:** turn camera right, record evidence, avoid right turns, prefer straight.
- **Center / near obstacle:** the Pi performs a servo/camera scan at `90, 45, 0, 135, 180`, sends scan frames to the Mac, and the Mac estimates left/right gaps and selects the bypass.
- **Ultrasonic emergency:** stop immediately.

Every manual cycle stores sensors, image path, continuous steering/speed labels, derived action label, gap metrics, and the current autonomous suggestion.

---

## Host / Edge Contract

### Edge → Host

The Pi posts to `POST /api/v1/cycle` with:

- sensor frame fields
- current camera frame as base64 JPEG
- scan frames as base64 JPEGs when center IR is active or the dashboard sweep button is requested

### Host → Edge

The Mac returns:

| Field | Meaning |
| --- | --- |
| `action` | `manual` or `stop` |
| `speed_cm_s` | commanded speed |
| `steering` | commanded steering |
| `servo_angle` | camera servo angle |
| `stop` | stop flag |
| `sweep_requested` | request a full camera sweep |
| autonomous suggestion probabilities | for dashboard visibility |

This keeps camera processing, model inference, dataset generation, evidence storage, and reports on the Mac.

---

## Accident Reports

The MPU6050 impact detector watches acceleration and yaw rate. On collision it writes a package below `accident_reports/packages/` containing:

- sensor history
- GPS location
- camera evidence path
- selected action
- alternative action probabilities
- reason code
- explainable Markdown report

### Example report summary

- GPS location: None, None
- Detected reason code: `front_obstacle_left_gap`
- Selected action: `left`
- Probability of selected action: `0.750`
- Second-best action: `straight` (`0.083`)
- Evidence used: sensor history, GPS, camera path, action probabilities, and expert reason codes.
- Avoidability assessment: not enough evidence for a definitive avoidability finding.

**What the car detected:** IR left=0, center=1, right=0; ultrasonic distance=999.0 cm; heading=111.64; acceleration=0.79 g.

**Why this action was selected:** the controller associated the situation with `front_obstacle_left_gap` and selected `left` from the softmax/action probability distribution.

---

## Configuration (`config/vehicle.yaml`)

### GPIO pins

```yaml
gpio:
  motor:
    ena_pwm: 18
    in1: 17
    in2: 27
    enb_pwm: 19
    in3: 22
    in4: 23
  front_motor:
    ena_pwm: 11
    in1: 7
    in2: 8
    enb_pwm: 12
    in3: 9
    in4: 10
  servo: 20
  ir:
    # Physical left/right IR sensors are swapped relative to the layout image.
    left: 16
    center: 6
    right: 5
  ultrasonic:
    trig: 4
    echo: 21
  i2c:
    sda: 2
    scl: 3
  gps_uart:
    tx: 14
    rx: 15
```

### Navigation parameters

| Parameter | Value | Purpose |
| --- | --- | --- |
| `constant_speed` | `0.42` | Default forward speed |
| `turn_speed` | `0.36` | Speed while turning |
| `emergency_distance_cm` | `18.0` | Ultrasonic stop threshold |
| `safe_gap_threshold` | `0.35` | Minimum passable gap score |
| `center_scan_angles` | `[-60, -30, 0, 30, 60]` | Servo angles used during center/near obstacle scans |
| `evidence_pre_seconds` | `6` | Seconds of sensor history before an accident |
| `evidence_post_seconds` | `4` | Seconds of sensor history after an accident |

---

## Dependencies

Core requirements (from `requirements.txt` / `pyproject.toml`):

```text
numpy>=1.24
pandas>=2.0
scikit-learn>=1.3
joblib>=1.3
opencv-python>=4.8
matplotlib>=3.7
pytest>=7.4
```

Optional Raspberry Pi extras:

```text
gpiozero>=2.0
smbus2>=0.4
pyserial>=3.5
picamera2>=0.3
```

Optional training extras:

```text
lightgbm>=4.0
torch>=2.0
```

---

## Calibration Checklist

- Confirm motor directions with a short simulated actuation test (wheels lifted).
- Test forward and reverse from the dashboard (wheels lifted).
- Test steering on blocks before placing the car on the floor.
- Confirm servo angle `90` points front, `180` points left side, and `0` points right side.
- Place a known obstacle at 20 cm and tune `emergency_distance_cm`.
- Collect manual dashboard driving data in `dataset/drives/manual_drive_log.csv` before training behavior-cloning models.

---

## Useful Commands Summary

| Task | Command |
| --- | --- |
| Start host server | `python -m host_server.server --host 0.0.0.0 --port 8765 --dataset dataset/drives/manual_drive_log.csv` |
| Simulate edge client locally | `python -m rpi_edge.client --simulate --host-url http://127.0.0.1:8765` |
| Train manual models | `python -m training.train_manual_models --dataset dataset/drives/manual_drive_log.csv --output models/manual` |
| Build synthetic dataset | `python -m dataset.build_dataset --output dataset/drives/synthetic_drive_log.csv --rows 800` |
| Train smoke-test models | `python -m training.train_models --dataset dataset/drives/synthetic_drive_log.csv --output models` |
| Validate model | `python -m training.validate_model --model models/best_model.joblib --dataset dataset/drives/synthetic_drive_log.csv` |
| Test ultrasonic sensor | `python scripts/test_ultrasonic_lgpio.py` |
| Test IR sensors | `python scripts/test_ir_sensors.py` |
| Test servo | `python scripts/test_servo.py` |
| Run tests | `pytest` |
