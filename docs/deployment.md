# Raspberry Pi Deployment

## Wiring Notes

Use a separate motor power supply for the L298N. Tie motor supply ground and Raspberry Pi ground together. Do not power motors from the Pi 5V rail.

## OS Preparation

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip python3-opencv i2c-tools git python3-lgpio python3-rpi-lgpio
sudo usermod -aG gpio,video,i2c,dialout $USER
```

Reboot after changing groups.

Enable interfaces with `sudo raspi-config`:

- Camera
- I2C for MPU6050
- Serial hardware for GPS

## Mac Host Install

On your Mac:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m host_server.server --host 0.0.0.0 --port 8765 --dataset dataset/drives/manual_drive_log.csv
```

Open the dashboard at `http://127.0.0.1:8765`.

Find your Mac IP:

```bash
ipconfig getifaddr en0
```

Use that IP from the Raspberry Pi.

## Raspberry Pi Edge Install

```bash
git clone <your-repo-url> arcane-xav
cd arcane-xav
./scripts/setup_pi.sh
```

The Pi venv is created with `--system-site-packages` so it can use apt-installed `lgpio`; do not `pip install lgpio` unless you also install build tools such as `swig`.

Run the edge client:

```bash
source .venv/bin/activate
python -m rpi_edge.client --host-url http://YOUR_MAC_IP:8765 --vehicle-id rpi-car-01
```

Test the ultrasonic sensor alone before driving:

```bash
python scripts/test_ultrasonic_lgpio.py
```

Test the servo calibration:

```bash
python scripts/test_servo.py
```

## Run Raspberry Pi Edge As A Service

Edit `scripts/arcane-xav.service` and set the absolute `WorkingDirectory` and `ExecStart` paths if needed. Then:

```bash
sudo cp scripts/arcane-xav.service /etc/systemd/system/arcane-xav.service
sudo systemctl daemon-reload
sudo systemctl enable --now arcane-xav
sudo journalctl -u arcane-xav -f
```

The service must point to your Mac host URL:

```ini
Environment=ARCANE_HOST_URL=http://YOUR_MAC_IP:8765
```

## Calibration Checklist

- Confirm motor directions by running a short simulated actuation test with wheels lifted.
- Test forward and reverse from the dashboard while wheels are lifted.
- Test steering on blocks before placing the car on the floor.
- Confirm servo angle `0` points front, `90` points left side, and `180` points right side.
- Place a known obstacle at 20 cm and tune `emergency_distance_cm`.
- Collect manual dashboard driving data in `dataset/drives/manual_drive_log.csv` before training behavior-cloning models.
