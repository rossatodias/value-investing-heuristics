"""Graham-style screening logic."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import GRAHAM_BASELINE


@dataclass(frozen=True)
class ScreeningResult:
    selected: list[str]
    relaxed_rules: list[str]


RULE_ORDER = [
    "min_dividend_yield",
    "min_margem_liquida",
    "max_pvpa",
    "max_divida_liquida_lucro_oper_proxy",
    "max_pl",
    "min_liquidez_corrente",
    "min_roe",
]


def _conditions(frame: pd.DataFrame, theta: dict[str, float], disabled: set[str]) -> dict[str, pd.Series]:
    idx = frame.index
    conditions = {
        "max_pl": frame["pl"].between(0, theta["max_pl"], inclusive="right"),
        "max_pvpa": frame["pvpa"].between(0, theta["max_pvpa"], inclusive="right"),
        "min_roe": frame["roe"] >= theta["min_roe"],
        "min_margem_liquida": frame["margem_liquida"] >= theta["min_margem_liquida"],
        "min_liquidez_corrente": frame["liquidez_corrente"] >= theta["min_liquidez_corrente"],
        "max_divida_liquida_lucro_oper_proxy": frame["divida_liquida_lucro_oper_proxy"].between(
            0, theta["max_divida_liquida_lucro_oper_proxy"], inclusive="both"
        ),
        "min_dividend_yield": frame["dividend_yield"] >= theta["min_dividend_yield"],
    }
    return {k: v.reindex(idx).fillna(False) for k, v in conditions.items() if k not in disabled}


def _rank_fallback(frame: pd.DataFrame, n: int) -> list[str]:
    scoring = pd.DataFrame(index=frame.index)
    scoring["pl"] = frame["pl"].replace([np.inf, -np.inf], np.nan).rank(ascending=True, na_option="bottom")
    scoring["pvpa"] = frame["pvpa"].replace([np.inf, -np.inf], np.nan).rank(ascending=True, na_option="bottom")
    scoring["roe"] = frame["roe"].rank(ascending=False, na_option="bottom")
    scoring["margem"] = frame["margem_liquida"].rank(ascending=False, na_option="bottom")
    scoring["liquidez"] = frame["liquidez_corrente"].rank(ascending=False, na_option="bottom")
    scoring["divida"] = frame["divida_liquida_lucro_oper_proxy"].rank(ascending=True, na_option="bottom")
    scoring["dy"] = frame["dividend_yield"].rank(ascending=False, na_option="bottom")
    total = scoring.sum(axis=1)
    return list(frame.loc[total.sort_values().head(n).index, "ticker"])


def screen_period(frame: pd.DataFrame, theta: dict[str, float] | None = None, min_assets: int = 5) -> ScreeningResult:
    theta = dict(GRAHAM_BASELINE if theta is None else theta)
    required_columns = {
        "ticker",
        "pl",
        "pvpa",
        "roe",
        "margem_liquida",
        "liquidez_corrente",
        "divida_liquida_lucro_oper_proxy",
        "dividend_yield",
    }
    missing = required_columns - set(frame.columns)
    if missing:
        raise ValueError(f"Missing screening columns: {sorted(missing)}")

    universe = frame.dropna(subset=["ticker"]).copy()
    if universe.empty:
        return ScreeningResult(selected=[], relaxed_rules=["empty_universe"])

    disabled: set[str] = set()
    relaxed: list[str] = []
    selected: list[str] = []

    for _ in range(len(RULE_ORDER) + 1):
        conds = _conditions(universe, theta, disabled)
        mask = pd.Series(True, index=universe.index)
        for cond in conds.values():
            mask &= cond
        selected = list(universe.loc[mask, "ticker"].drop_duplicates())
        if len(selected) >= min_assets or len(disabled) == len(RULE_ORDER):
            break
        rule = RULE_ORDER[len(disabled)]
        disabled.add(rule)
        relaxed.append(rule)

    if len(selected) < min_assets:
        selected = _rank_fallback(universe, min(min_assets, universe["ticker"].nunique()))
        relaxed.append("rank_fallback")

    return ScreeningResult(selected=selected, relaxed_rules=relaxed)
