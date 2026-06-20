from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline

from dataset.feature_extraction import build_preprocessor, load_dataset


def _lightgbm_model():
    try:
        from lightgbm import LGBMClassifier

        return LGBMClassifier(n_estimators=160, learning_rate=0.05, random_state=42)
    except Exception:
        return None


def train(dataset_path: str | Path, output_dir: str | Path = "models") -> dict[str, dict[str, float]]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    df = load_dataset(dataset_path)
    X = df.drop(columns=["chosen_action"])
    y = df["chosen_action"]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y if y.nunique() > 1 else None)

    candidates = {
        "random_forest": RandomForestClassifier(n_estimators=180, min_samples_leaf=2, random_state=42, class_weight="balanced"),
        "small_neural_network": MLPClassifier(hidden_layer_sizes=(48, 24), activation="relu", max_iter=600, random_state=42),
    }
    lgbm = _lightgbm_model()
    if lgbm is not None:
        candidates["lightgbm"] = lgbm

    metrics: dict[str, dict[str, float]] = {}
    best_name = ""
    best_accuracy = -1.0
    for name, model in candidates.items():
        pipe = Pipeline([("features", build_preprocessor()), ("model", model)])
        pipe.fit(X_train, y_train)
        pred = pipe.predict(X_test)
        accuracy = float(accuracy_score(y_test, pred))
        metrics[name] = {"accuracy": accuracy}
        (output / name).mkdir(exist_ok=True)
        joblib.dump(pipe, output / name / "model.joblib")
        (output / name / "classification_report.txt").write_text(classification_report(y_test, pred, zero_division=0), encoding="utf-8")
        if accuracy > best_accuracy:
            best_name, best_accuracy = name, accuracy
            joblib.dump(pipe, output / "best_model.joblib")

    (output / "metrics.json").write_text(json.dumps({"best_model": best_name, "models": metrics}, indent=2), encoding="utf-8")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="dataset/drives/drive_log.csv")
    parser.add_argument("--output", default="models")
    args = parser.parse_args()
    train(args.dataset, args.output)


if __name__ == "__main__":
    main()
