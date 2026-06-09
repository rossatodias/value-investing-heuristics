"""Load and prepare ITR financial statement data."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from .config import NUMERIC_COLUMNS


def normalize_cnpj(value: object) -> str:
    """Return a 14 digit CNPJ string, keeping leading zeroes."""
    digits = re.sub(r"\D", "", "" if value is None else str(value))
    return digits.zfill(14) if digits else ""


def parse_period(period: str) -> tuple[int, int]:
    year, quarter = str(period).split(".")
    return int(year), int(quarter.replace("T", ""))


def quarter_end_date(year: int, quarter: int) -> pd.Timestamp:
    month = quarter * 3
    return pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)


def load_itr_csv(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";", dtype={"cnpj": "string", "periodo": "string"})
    df.columns = [c.strip() for c in df.columns]
    df["cnpj_norm"] = df["cnpj"].map(normalize_cnpj)

    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "periodo" not in df.columns:
        df["periodo"] = df["ano"].astype("Int64").astype(str) + "." + df["trimestre"].astype("Int64").astype(str) + "T"

    parsed = df["periodo"].map(parse_period)
    df["ano"] = [p[0] for p in parsed]
    df["trimestre"] = [p[1] for p in parsed]
    df["period_end"] = [quarter_end_date(y, q) for y, q in parsed]
    df = df.sort_values(["period_end", "cnpj_norm"]).reset_index(drop=True)
    return df


def add_signal_dates(df: pd.DataFrame, lag_days: int = 45) -> pd.DataFrame:
    out = df.copy()
    out["signal_date"] = out["period_end"] + pd.to_timedelta(lag_days, unit="D")
    return out


def dataset_profile(df: pd.DataFrame) -> dict[str, object]:
    numeric = df.select_dtypes(include="number")
    missing = df.isna().sum().sort_values(ascending=False)
    return {
        "rows": int(len(df)),
        "unique_cnpjs": int(df["cnpj_norm"].nunique()),
        "periods": list(df["periodo"].drop_duplicates()),
        "years": sorted(int(v) for v in df["ano"].dropna().unique()),
        "missing_top": missing[missing > 0].head(20).to_dict(),
        "numeric_min_max": {
            col: {"min": float(numeric[col].min()), "max": float(numeric[col].max())}
            for col in numeric.columns
            if numeric[col].notna().any()
        },
    }


def save_profile(profile: dict[str, object], path: str | Path) -> None:
    import json

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
