"""Fundamental and market indicator calculations."""

from __future__ import annotations

import numpy as np
import pandas as pd


def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denom = denominator.replace({0: np.nan})
    return numerator / denom


def add_fundamental_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["liquidez_corrente"] = safe_divide(out["ativoCirc"], out["passivoCirc"])
    out["roe"] = safe_divide(out["lucroLiq"], out["patLiq"])
    out["margem_liquida"] = safe_divide(out["lucroLiq"], out["receitaBruta"])
    out["divida_patrimonio"] = safe_divide(out["dividaLiq"], out["patLiq"])

    valid_lucro_oper = out["lucroOper"] > 0
    out["divida_liquida_lucro_oper_proxy"] = np.where(
        valid_lucro_oper,
        out["dividaLiq"] / out["lucroOper"].replace({0: np.nan}),
        np.nan,
    )
    out["lucro_oper_proxy_valido"] = valid_lucro_oper
    return out


def add_market_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "market_cap" not in out.columns:
        out["market_cap"] = np.nan

    out["pl"] = safe_divide(out["market_cap"], out["lucroLiq"])
    out["pvpa"] = safe_divide(out["market_cap"], out["patLiq"])
    payouts = out.get("dividendosPagos", 0).fillna(0) + out.get("jcp", 0).fillna(0)
    out["dividend_yield"] = safe_divide(payouts, out["market_cap"])
    return out


def winsorize_training_frame(df: pd.DataFrame, columns: list[str], lower: float = 0.01, upper: float = 0.99) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col not in out.columns or out[col].dropna().empty:
            continue
        lo = out[col].quantile(lower)
        hi = out[col].quantile(upper)
        out[col] = out[col].clip(lo, hi)
    return out
