"""Taxa CDI via API publica do BCB (serie 4389, base 252)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

_SGS_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"
CDI_CODE = 4389


def fetch_cdi_series(start="2020-01-01", end=None, *, timeout=30.0):
    params = {"formato": "json"}
    if start:
        params["dataInicial"] = pd.Timestamp(start).strftime("%d/%m/%Y")
    if end:
        params["dataFinal"] = pd.Timestamp(end).strftime("%d/%m/%Y")

    url = _SGS_URL.format(code=CDI_CODE)
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()

    df = pd.DataFrame(resp.json())
    df.rename(columns={"data": "date", "valor": "cdi_annual_pct"}, inplace=True)
    df["date"] = pd.to_datetime(df["date"], dayfirst=True)
    df["cdi_annual_pct"] = pd.to_numeric(df["cdi_annual_pct"], errors="coerce")
    return df.sort_values("date").reset_index(drop=True)


def save_cdi(df, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def load_cdi(path):
    return pd.read_csv(path, parse_dates=["date"])


def cdi_annual_rate_for_year(cdi_df, year):
    """Media anualizada do CDI (decimal) para um dado ano."""
    subset = cdi_df.loc[cdi_df["date"].dt.year == year, "cdi_annual_pct"]
    return float(subset.mean()) / 100.0 if not subset.empty else 0.0


def cdi_period_rate(cdi_df, start_date, end_date):
    """Media anualizada do CDI (decimal) entre duas datas."""
    mask = (cdi_df["date"] >= pd.Timestamp(start_date)) & (cdi_df["date"] <= pd.Timestamp(end_date))
    subset = cdi_df.loc[mask, "cdi_annual_pct"]
    return float(subset.mean()) / 100.0 if not subset.empty else 0.0
