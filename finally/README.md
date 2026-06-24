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
  --cruise-pwm 0.65 --avoid-pwm 0.62 --reverse-pwm 0.60 --pivot-pwm 0.78
```

Open the UI from any phone or laptop on the same network:

```text
http://<raspberry-pi-ip>:8080
```

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
- Loaded-car PWM defaults: cruise `0.58`, avoid `0.56`, reverse `0.52`, pivot `0.68`, recover `0.54`.
- Camera frames are not written continuously to disk.
- If the UI disconnects, autonomy continues.
- If a sensor/control exception happens, motors stop and the UI shows the fault.

## Behavior

The rule controller uses IR, ultrasonic, and low-rate camera gap scores. When the front is blocked, it no longer waits forever in hard stop. It pauses, scans, reverses, pivots toward the safer side, recovers, and re-checks.
