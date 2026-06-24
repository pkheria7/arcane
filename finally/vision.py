from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GapScores:
    left: float = 0.5
    center: float = 0.5
    right: float = 0.5
    ok: bool = False


def score_jpeg(jpeg_bytes: bytes | None) -> GapScores:
    if not jpeg_bytes:
        return GapScores()
    try:
        import cv2
        import numpy as np

        data = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return GapScores()
        h, _ = img.shape
        roi = img[int(h * 0.45) :, :]
        roi = cv2.GaussianBlur(roi, (5, 5), 0)
        edges = cv2.Canny(roi, 70, 150)
        patches = np.array_split(roi, 3, axis=1)
        edge_patches = np.array_split(edges, 3, axis=1)
        scores: list[float] = []
        for patch, edge_patch in zip(patches, edge_patches):
            brightness = float(patch.mean()) / 255.0
            edge_density = float((edge_patch > 0).mean())
            dark_density = float((patch < max(35, int(patch.mean() * 0.65))).mean())
            score = 0.50 * brightness + 0.35 * (1.0 - edge_density) + 0.15 * (1.0 - dark_density)
            scores.append(max(0.0, min(1.0, score)))
        return GapScores(left=scores[0], center=scores[1], right=scores[2], ok=True)
    except Exception:
        return GapScores()

