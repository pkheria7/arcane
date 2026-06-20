from __future__ import annotations

import sys
from pathlib import Path


def add_system_dist_packages() -> None:
    """Expose apt-installed Raspberry Pi Python packages inside a venv.

    Raspberry Pi OS ships hardware bindings such as lgpio in
    /usr/lib/python3/dist-packages. A regular venv does not include that path,
    so we add it explicitly before importing GPIO backends.
    """
    candidates = [Path("/usr/lib/python3/dist-packages")]
    for path in candidates:
        value = str(path)
        if path.exists() and value not in sys.path:
            sys.path.append(value)
