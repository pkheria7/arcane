from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
from sklearn.metrics import ConfusionMatrixDisplay, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split

from dataset.feature_extraction import load_dataset


def validate(model_path: str | Path, dataset_path: str | Path, output_dir: str | Path = "models/validation") -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    model = joblib.load(model_path)
    df = load_dataset(dataset_path)
    X = df.drop(columns=["chosen_action"])
    y = df["chosen_action"]
    _, X_test, _, y_test = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y if y.nunique() > 1 else None)
    pred = model.predict(X_test)
    labels = ["left", "straight", "right", "stop"]
    cm = confusion_matrix(y_test, pred, labels=labels)
    (output / "classification_report.txt").write_text(classification_report(y_test, pred, labels=labels, zero_division=0), encoding="utf-8")
    fig, ax = plt.subplots(figsize=(7, 6))
    ConfusionMatrixDisplay(cm, display_labels=labels).plot(ax=ax, cmap="Blues")
    fig.tight_layout()
    fig.savefig(output / "confusion_matrix.png", dpi=140)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="models/best_model.joblib")
    parser.add_argument("--dataset", default="dataset/drives/drive_log.csv")
    parser.add_argument("--output", default="models/validation")
    args = parser.parse_args()
    validate(args.model, args.dataset, args.output)


if __name__ == "__main__":
    main()
