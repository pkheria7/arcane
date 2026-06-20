from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .schema import FEATURE_COLUMNS


def load_dataset(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = sorted(set(FEATURE_COLUMNS + ["chosen_action"]) - set(df.columns))
    if missing:
        raise ValueError(f"Dataset is missing columns: {missing}")
    return df


def build_preprocessor() -> ColumnTransformer:
    numeric = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())])
    return ColumnTransformer([("numeric", numeric, FEATURE_COLUMNS)], remainder="drop")


def save_pipeline(pipeline, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, path)


def load_pipeline(path: str | Path):
    return joblib.load(path)
