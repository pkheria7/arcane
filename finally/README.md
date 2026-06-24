# ARCANE Pi-Only Rule-Based Car

This folder is a clean Raspberry Pi first implementation. It does not load trained models and does not use the old host `/api/v1/cycle` command loop.

## Run On Raspberry Pi

```bash
source .venv/bin/activate
python -m finally.main --host 0.0.0.0 --port 8080
```

If the loaded car needs more torque, tune PWM from the command line:

```bash
python -m finally.main --host 0.0.0.0 --port 8080 \
  --cruise-pwm 0.90 --avoid-pwm 0.90 --reverse-pwm 0.90 --pivot-pwm 0.90
```

If it has power but does not rotate far enough, increase pivot time:

```bash
python -m finally.main --host 0.0.0.0 --port 8080 --pivot-seconds 0.9
```

The scan servo uses physical angles `180=left`, `90=front`, `0=right`. Use `--scan-settle 0.7` if you want the camera to visibly pause longer at each angle.

Open the UI from any phone or laptop on the same network:

```text
http://<raspberry-pi-ip>:8080
```

The UI uses Leaflet with OpenStreetMap tiles. When the GPS module has a fix, it shows the current coordinates, a live marker, and a short trail of recent movement.

Find the Pi IP with:

```bash
hostname -I
```

## Simulation

```bash
python -m finally.main --simulate
```

Then open:

```text
http://127.0.0.1:8080
```

## Hardware Test Order

Lift the wheels before motor tests.

```bash
python -m finally.motor_test --pwm 0.55 --seconds 1.0
python scripts/test_ir_sensors.py
python scripts/test_ultrasonic_lgpio.py
python scripts/test_servo.py
```

If one wheel spins backward during a forward test, update that wheel's `invert` calibration in `finally/config.py`.

## Runtime Defaults

- Control loop: about 14 Hz.
- Camera scoring: about 3 Hz.
- Camera size: 160x120.
- Loaded-car PWM defaults: cruise `0.90`, avoid `0.90`, reverse `0.90`, pivot `0.90`, recover `0.90`.
- Camera frames are not written continuously to disk.
- If the UI disconnects, autonomy continues.
- If a sensor/control exception happens, motors stop and the UI shows the fault.

## Behavior

The rule controller uses IR, ultrasonic, and low-rate camera gap scores. When the front is blocked, it no longer waits forever in hard stop. It pauses, scans, reverses, pivots toward the safer side, recovers, and re-checks.

## Evidence Records For Compliance Reports

The Pi records evidence packages when an IR sensor is active:

- Right IR active: servo turns to `0` and records the right-side scene.
- Center IR active: servo turns to `90` and records the front scene.
- Left IR active: servo turns to `180` and records the left-side scene.
- The camera stays locked to the triggering IR direction until that same IR goes low.
- Every event folder contains `scene.mp4`, `actions.jsonl`, and `manifest.json`.
- `actions.jsonl` logs sensor values, controller state, reason, and motor command for every control loop.

Records are stored under:

```text
finally_records/
```

The web UI lists recent evidence records and provides a `Download record` link. Download the `.zip` on your Mac and run the Mac-side vision/LLM/PDF generator against `scene.mp4` plus `actions.jsonl`.
