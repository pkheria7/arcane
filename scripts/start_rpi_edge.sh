#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${ARCANE_HOST_URL:-}" ]]; then
  echo "Set ARCANE_HOST_URL to your Mac host URL, for example http://192.168.1.25:8765"
  exit 1
fi

python -m rpi_edge.client \
  --host-url "$ARCANE_HOST_URL" \
  --vehicle-id "${ARCANE_VEHICLE_ID:-rpi-car-01}"
