from __future__ import annotations

import json
from pathlib import Path


def generate_report(package_path: str | Path, output_path: str | Path | None = None) -> Path:
    package_path = Path(package_path)
    data = json.loads((package_path / "accident_package.json").read_text(encoding="utf-8"))
    probabilities = data["action_probabilities"]
    selected = data["selected_action"]
    second = data["alternative_actions"][0] if data["alternative_actions"] else ["none", 0.0]
    avoidable = "unknown"
    if probabilities.get("stop", 0.0) > probabilities.get(selected, 0.0) * 0.9 and selected != "stop":
        avoidable = "possibly avoidable; stop probability was close to the selected action"
    elif data["reason_code"] in {"emergency_stop", "no_safe_path"}:
        avoidable = "unlikely avoidable by navigation policy; system selected or preferred stopping"
    else:
        avoidable = "not enough evidence for a definitive avoidability finding"

    location = data.get("gps_location", {})
    mode = data.get("mode", "manual")
    frame = data.get("current_frame", {})
    image_path = frame.get("image_path", "unknown")
    lines = [
        "# Explainable Accident Report",
        "",
        f"- Mode at time of incident: **{mode.upper()}**",
        f"- GPS location: {location.get('lat')}, {location.get('lon')}",
        f"- Detected reason code: {data['reason_code']}",
        f"- Selected action: {selected}",
        f"- Probability of selected action: {probabilities.get(selected, 0.0):.3f}",
        f"- Second-best action: {second[0]} ({float(second[1]):.3f})",
        f"- Evidence used: sensor history, GPS, camera frame, action probabilities, and expert reason codes.",
        f"- Camera frame path: `{image_path}`",
        f"- Avoidability assessment: {avoidable}.",
        "",
        "## What The Car Detected",
        _detection_summary(data),
        "",
        "## Why This Action Was Selected",
        f"The controller associated the situation with `{data['reason_code']}` and selected `{selected}` from the softmax/action probability distribution.",
    ]
    output = Path(output_path) if output_path else package_path / "explainable_report.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def _detection_summary(data: dict) -> str:
    frame = data.get("current_frame", {})
    return (
        f"IR left={frame.get('ir_left')}, center={frame.get('ir_center')}, right={frame.get('ir_right')}; "
        f"ultrasonic distance={frame.get('ultrasonic_distance')} cm; heading={frame.get('heading')}; "
        f"acceleration={frame.get('acceleration')} g."
    )
