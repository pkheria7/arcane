from __future__ import annotations

from pathlib import Path


def analyze_gap(image_path: str | None, vehicle_width_fraction: float = 0.28, safety_margin_fraction: float = 0.08) -> dict[str, float | bool]:
    """Estimate passability from a single monocular image.

    This is a depth-free heuristic for collecting useful labels before a depth
    sensor or trained segmentation model exists. It focuses on the lower half
    of the image where nearby obstacles and corridor boundaries matter most.
    """
    default = {
        "free_space_score": 0.5,
        "obstacle_score": 0.5,
        "narrow_pass_score": 0.5,
        "free_corridor_fraction": 0.5,
        "passable": True,
    }
    if not image_path or not Path(image_path).exists():
        return default
    try:
        import cv2
        import numpy as np

        img = cv2.imread(image_path)
        if img is None:
            return default
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        roi = gray[int(h * 0.45) :, :]
        roi = cv2.GaussianBlur(roi, (5, 5), 0)
        edges = cv2.Canny(roi, 70, 150)
        texture = cv2.Laplacian(roi, cv2.CV_64F).var() / 1200.0
        dark_mask = roi < max(35, int(roi.mean() * 0.65))
        edge_density = float((edges > 0).mean())
        dark_density = float(dark_mask.mean())
        occupancy = min(1.0, 0.55 * edge_density + 0.35 * dark_density + 0.10 * min(1.0, texture))

        column_obstacle = ((edges > 0) | dark_mask).mean(axis=0)
        free_columns = column_obstacle < 0.18
        max_run = 0
        current = 0
        for free in free_columns:
            current = current + 1 if free else 0
            max_run = max(max_run, current)
        free_corridor_fraction = max_run / max(1, w)
        required_width = min(0.95, vehicle_width_fraction + safety_margin_fraction)
        narrow_pass_score = max(0.0, min(1.0, free_corridor_fraction / required_width))
        free_space_score = max(0.0, min(1.0, 0.55 * (1.0 - occupancy) + 0.45 * narrow_pass_score))
        obstacle_score = max(0.0, min(1.0, occupancy))
        return {
            "free_space_score": free_space_score,
            "obstacle_score": obstacle_score,
            "narrow_pass_score": narrow_pass_score,
            "free_corridor_fraction": free_corridor_fraction,
            "passable": free_corridor_fraction >= required_width,
        }
    except Exception:
        return default


def image_gap_scores(image_path: str | None) -> tuple[float, float, float]:
    """Estimate left, center, and right free-space scores from a camera frame.

    The implementation is intentionally lightweight for Raspberry Pi. It uses
    low-edge-density and brighter lower-image regions as a proxy for drivable
    free space. If OpenCV or an image is unavailable, it returns neutral scores.
    """
    if not image_path or not Path(image_path).exists():
        return (0.5, 0.5, 0.5)
    try:
        import cv2
        import numpy as np

        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return (0.5, 0.5, 0.5)
        h, w = img.shape
        roi = img[int(h * 0.45) :, :]
        edges = cv2.Canny(roi, 80, 160)
        thirds = np.array_split(roi, 3, axis=1)
        edge_thirds = np.array_split(edges, 3, axis=1)
        scores: list[float] = []
        for patch, edge_patch in zip(thirds, edge_thirds):
            brightness = float(patch.mean()) / 255.0
            edge_density = float((edge_patch > 0).mean())
            scores.append(max(0.0, min(1.0, 0.65 * brightness + 0.35 * (1.0 - edge_density))))
        return (scores[0], scores[1], scores[2])
    except Exception:
        return (0.5, 0.5, 0.5)
