from __future__ import annotations

from typing import Iterable

import pandas as pd

from src.features.schema import FEATURE_COLUMNS, FEATURE_GROUPS, FORBIDDEN_FEATURE_COLUMNS


def select_feature_columns(
    drop_feature_groups: Iterable[str] | None = None,
    drop_feature_columns: Iterable[str] | None = None,
) -> list[str]:
    columns = list(FEATURE_COLUMNS)
    forbidden_defaults = [column for column in columns if column in FORBIDDEN_FEATURE_COLUMNS]
    if forbidden_defaults:
        raise ValueError(
            "Feature schema includes forbidden leakage-prone columns: "
            + ", ".join(sorted(forbidden_defaults))
        )
    for group_name in drop_feature_groups or []:
        for column in FEATURE_GROUPS.get(group_name, []):
            if column in columns:
                columns.remove(column)
    for column in drop_feature_columns or []:
        if column in columns:
            columns.remove(column)
    return columns


def ordered_feature_frame(frame: pd.DataFrame, feature_columns: list[str] | None = None) -> pd.DataFrame:
    columns = feature_columns or FEATURE_COLUMNS
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Feature frame is missing expected columns: {missing}")
    forbidden = [column for column in columns if column in FORBIDDEN_FEATURE_COLUMNS]
    if forbidden:
        raise ValueError(f"Refusing to use leakage-prone columns as model features: {forbidden}")
    return frame.loc[:, columns].copy()


def build_logreg_preprocessor():
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    return Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )


def build_tree_preprocessor():
    from sklearn.impute import SimpleImputer

    return SimpleImputer(strategy="median")
