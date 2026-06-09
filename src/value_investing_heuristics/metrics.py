"""Metricas de desempenho."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def cumulative_return(returns):
    return float((1.0 + returns.fillna(0)).prod() - 1.0)


def annualized_return(returns, periods_per_year=4):
    clean = returns.dropna()
    if clean.empty:
        return float("nan")
    total = cumulative_return(clean)
    years = len(clean) / periods_per_year
    return float((1.0 + total) ** (1.0 / years) - 1.0) if years > 0 else float("nan")


def annualized_volatility(returns, periods_per_year=4):
    clean = returns.dropna()
    if len(clean) < 2:
        return float("nan")
    return float(clean.std(ddof=1) * math.sqrt(periods_per_year))


def sharpe_ratio(returns, risk_free=0.0, periods_per_year=4):
    clean = returns.dropna()
    if len(clean) < 2:
        return float("nan")
    excess = clean - (risk_free / periods_per_year)
    vol = clean.std(ddof=1)
    if vol == 0 or np.isnan(vol):
        return float("nan")
    return float(excess.mean() / vol * math.sqrt(periods_per_year))


def sortino_ratio(returns, target=0.0, periods_per_year=4):
    clean = returns.dropna()
    if len(clean) < 2:
        return float("nan")
    downside = clean[clean < target] - target
    if downside.empty:
        return float("inf")
    dd = downside.std(ddof=1)
    if dd == 0 or np.isnan(dd):
        return float("nan")
    return float((clean.mean() - target) / dd * math.sqrt(periods_per_year))


def max_drawdown(returns):
    wealth = (1.0 + returns.fillna(0)).cumprod()
    dd = wealth / wealth.cummax() - 1.0
    return float(dd.min()) if not dd.empty else float("nan")


def alpha_beta(returns, benchmark, risk_free=0.0, periods_per_year=4):
    joined = pd.concat([returns, benchmark], axis=1, join="inner").dropna()
    if len(joined) < 2:
        return float("nan"), float("nan")
    y = joined.iloc[:, 0] - (risk_free / periods_per_year)
    x = joined.iloc[:, 1] - (risk_free / periods_per_year)
    var = x.var(ddof=1)
    if var == 0 or np.isnan(var):
        return float("nan"), float("nan")
    beta = y.cov(x) / var
    alpha_period = y.mean() - beta * x.mean()
    return float(alpha_period * periods_per_year), float(beta)


def deflated_sharpe_proxy(sharpe, n_trials, n_obs):
    """Penalizacao conservadora pelo numero de tentativas (nao e o DSR completo)."""
    if np.isnan(sharpe) or n_obs <= 1:
        return float("nan")
    penalty = math.sqrt(2.0 * math.log(max(n_trials, 1)) / max(n_obs, 1))
    return float(sharpe - penalty)


def bootstrap_sharpe_ci(returns, *, risk_free=0.0, periods_per_year=4,
                        n_bootstrap=1000, confidence=0.95, seed=42):
    """IC bootstrap para o Sharpe ratio."""
    clean = returns.dropna()
    nan_result = {"sharpe_ci_lower": float("nan"), "sharpe_ci_upper": float("nan"),
                  "sharpe_ci_mean": float("nan"), "sharpe_ci_std": float("nan")}
    if len(clean) < 3:
        return nan_result

    rng = np.random.default_rng(seed)
    values = clean.values
    n = len(values)
    sharpes = []
    for _ in range(n_bootstrap):
        sample = pd.Series(rng.choice(values, size=n, replace=True))
        sr = sharpe_ratio(sample, risk_free=risk_free, periods_per_year=periods_per_year)
        if not np.isnan(sr):
            sharpes.append(sr)

    if not sharpes:
        return nan_result

    arr = np.array(sharpes)
    alpha = (1.0 - confidence) / 2.0
    return {
        "sharpe_ci_lower": float(np.percentile(arr, 100 * alpha)),
        "sharpe_ci_upper": float(np.percentile(arr, 100 * (1.0 - alpha))),
        "sharpe_ci_mean": float(arr.mean()),
        "sharpe_ci_std": float(arr.std(ddof=1)) if len(arr) > 1 else float("nan"),
    }


def summarize_returns(returns, benchmark=None, *, risk_free=0.0, periods_per_year=4,
                      n_trials=1, avg_assets=None, avg_turnover=None,
                      bootstrap=True, n_bootstrap=1000, bootstrap_seed=42):
    sr = sharpe_ratio(returns, risk_free=risk_free, periods_per_year=periods_per_year)
    summary = {
        "cumulative_return": cumulative_return(returns),
        "annualized_return": annualized_return(returns, periods_per_year),
        "annualized_volatility": annualized_volatility(returns, periods_per_year),
        "sharpe": sr,
        "deflated_sharpe_proxy": deflated_sharpe_proxy(sr, n_trials, len(returns.dropna())),
        "sortino": sortino_ratio(returns, periods_per_year=periods_per_year),
        "max_drawdown": max_drawdown(returns),
        "avg_assets": float(avg_assets) if avg_assets is not None else float("nan"),
        "avg_turnover": float(avg_turnover) if avg_turnover is not None else float("nan"),
    }

    if bootstrap:
        summary.update(bootstrap_sharpe_ci(
            returns, risk_free=risk_free, periods_per_year=periods_per_year,
            n_bootstrap=n_bootstrap, seed=bootstrap_seed,
        ))
    else:
        summary.update({"sharpe_ci_lower": float("nan"), "sharpe_ci_upper": float("nan"),
                        "sharpe_ci_mean": float("nan"), "sharpe_ci_std": float("nan")})

    if benchmark is not None:
        a, b = alpha_beta(returns, benchmark, risk_free=risk_free, periods_per_year=periods_per_year)
        summary["jensen_alpha"] = a
        summary["beta_vs_benchmark"] = b
    else:
        summary["jensen_alpha"] = float("nan")
        summary["beta_vs_benchmark"] = float("nan")

    return summary
