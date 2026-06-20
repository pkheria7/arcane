#!/usr/bin/env bash
set -euo pipefail

python -m host_server.server \
  --host 0.0.0.0 \
  --port "${ARCANE_HOST_PORT:-8765}" \
  --dataset "${ARCANE_DATASET:-dataset/drives/manual_drive_log.csv}" \
  ${ARCANE_MODEL:+--model "$ARCANE_MODEL"}
