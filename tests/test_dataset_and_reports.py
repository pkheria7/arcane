import json

from accident_reports.package import AccidentPackager
from dataset.collector import DatasetLogger
from event_logger.evidence import EvidenceLogger
from explainability.report_generator import generate_report
from navigation_ai.expert_controller import ExpertController
from sensor_layer.types import SensorFrame


def test_dataset_logger_writes_required_columns(tmp_path):
    path = tmp_path / "drive.csv"
    frame = SensorFrame.empty()
    decision = ExpertController().decide(frame)
    DatasetLogger(path).append(frame, decision)
    text = path.read_text(encoding="utf-8")
    assert "chosen_action" in text
    assert "reason_code" in text
    assert "clear_path" in text


def test_accident_package_and_report(tmp_path):
    frame = SensorFrame.empty()
    decision = ExpertController().decide(frame)
    evidence = EvidenceLogger(tmp_path / "evidence")
    evidence.observe(frame, decision)
    package = AccidentPackager(tmp_path / "packages").create(frame, decision, evidence)
    data = json.loads((package / "accident_package.json").read_text(encoding="utf-8"))
    assert data["selected_action"] == "straight"
    report = generate_report(package)
    assert "Explainable Accident Report" in report.read_text(encoding="utf-8")
