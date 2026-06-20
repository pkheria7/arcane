#!/usr/bin/env bash
set -euo pipefail

python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install "gpiozero>=2.0" "smbus2>=0.4" "pyserial>=3.5" || true

mkdir -p dataset/drives dataset/images models event_logger/evidence accident_reports/packages

echo "Install complete."
echo "On the Raspberry Pi also run:"
echo "  sudo apt update"
echo "  sudo apt install -y python3-lgpio python3-rpi-lgpio"
echo "  sudo usermod -aG gpio,video,i2c,dialout \$USER"
echo "  sudo reboot"
echo "After reboot, enable Camera, I2C, and Serial with sudo raspi-config."
