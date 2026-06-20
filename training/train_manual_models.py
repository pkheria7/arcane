from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import train_test_split
from sklearn.multioutput import MultiOutputRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import Pipeline

from dataset.feature_extraction import build_preprocessor
from dataset.schema import FEATURE_COLUMNS

TARGET_COLUMNS = ["manual_steering", "manual_speed_cm_s", "manual_direction_value"]


def _lightgbm_model():
    try:
        from lightgbm import LGBMRegressor

        return MultiOutputRegressor(LGBMRegressor(n_estimators=180, learning_rate=0.05, random_state=42))
    except Exception:
        return None


def train(dataset_path: str | Path, output_dir: str | Path = "models/manual") -> dict[str, dict[str, float]]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(dataset_path)
    if "manual_direction" not in df.columns:
        df["manual_direction"] = "forward"
    df["manual_direction_value"] = df["manual_direction"].map({"forward": 1.0, "reverse": -1.0}).fillna(1.0)
    missing = sorted(set(FEATURE_COLUMNS + TARGET_COLUMNS) - set(df.columns))
    if missing:
        raise ValueError(f"Manual dataset is missing columns: {missing}")
    X = df[FEATURE_COLUMNS]
    y = df[TARGET_COLUMNS]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42)

    candidates = {
        "random_forest_regressor": RandomForestRegressor(n_estimators=180, min_samples_leaf=2, random_state=42),
        "small_neural_network_regressor": MLPRegressor(hidden_layer_sizes=(48, 24), activation="relu", max_iter=600, random_state=42),
    }
    lgbm = _lightgbm_model()
    if lgbm is not None:
        candidates["lightgbm_regressor"] = lgbm

    metrics: dict[str, dict[str, float]] = {}
    best_name = ""
    best_mae = float("inf")
    for name, model in candidates.items():
        pipe = Pipeline([("features", build_preprocessor()), ("model", model)])
        pipe.fit(X_train, y_train)
        pred = pipe.predict(X_test)
        mae = float(mean_absolute_error(y_test, pred))
        mse = float(mean_squared_error(y_test, pred))
        metrics[name] = {"mae": mae, "mse": mse}
        (output / name).mkdir(exist_ok=True)
        joblib.dump(pipe, output / name / "model.joblib")
        if mae < best_mae:
            best_name, best_mae = name, mae
            joblib.dump(pipe, output / "best_manual_model.joblib")

    (output / "metrics.json").write_text(json.dumps({"best_model": best_name, "models": metrics}, indent=2), encoding="utf-8")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="dataset/drives/manual_drive_log.csv")
    parser.add_argument("--output", default="models/manual")
    args = parser.parse_args()
    train(args.dataset, args.output)


if __name__ == "__main__":
    main()
