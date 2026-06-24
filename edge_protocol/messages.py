from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sensor_layer.types import SensorFrame


@dataclass(frozen=True)
class ImagePayload:
    angle: int
    filename: str
    content_type: str
    data_b64: str

    @classmethod
    def from_file(cls, path: str | Path, angle: int, content_type: str = "image/jpeg") -> "ImagePayload":
        path = Path(path)
        return cls(angle=angle, filename=path.name, content_type=content_type, data_b64=base64.b64encode(path.read_bytes()).decode("ascii"))

    @classmethod
    def from_bytes(cls, data: bytes, angle: int, filename: str, content_type: str = "image/jpeg") -> "ImagePayload":
        return cls(angle=angle, filename=filename, content_type=content_type, data_b64=base64.b64encode(data).decode("ascii"))

    def to_bytes(self) -> bytes:
        return base64.b64decode(self.data_b64.encode("ascii"))

    def write_to(self, directory: str | Path, prefix: str) -> Path:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        safe_name = self.filename.replace("/", "_").replace("\\", "_")
        path = directory / f"{prefix}_{self.angle}_{safe_name}"
        path.write_bytes(self.to_bytes())
        return path


@dataclass(frozen=True)
class EdgePacket:
    vehicle_id: str
    frame: dict[str, Any]
    image: dict[str, Any] | None = None
    scan_images: list[dict[str, Any]] | None = None

    @classmethod
    def from_frame(
        cls,
        vehicle_id: str,
        frame: SensorFrame,
        image: ImagePayload | None = None,
        scan_images: list[ImagePayload] | None = None,
    ) -> "EdgePacket":
        return cls(
            vehicle_id=vehicle_id,
            frame=asdict(frame),
            image=asdict(image) if image else None,
            scan_images=[asdict(item) for item in scan_images or []],
        )

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HostCommand:
    action: str
    speed: float
    servo_angle: int
    probabilities: dict[str, float]
    reason_code: str
    explanation: str
    speed_cm_s: float | None = None
    steering: float | None = None
    direction: str = "forward"
    stop: bool = False
    sweep_requested: bool = False
    event_recorded: bool = False
    accident_report_path: str | None = None
    mode: str = "manual"

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)
