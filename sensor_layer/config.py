from __future__ import annotations

from pathlib import Path

import yaml


def load_vehicle_config(path: str | Path | None = None) -> dict:
    """Load the vehicle GPIO and navigation configuration.

    Defaults to ``config/vehicle.yaml`` in the project root.
    """
    if path is None:
        path = Path(__file__).parent.parent / "config" / "vehicle.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)
