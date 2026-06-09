"""Leak-aware walk-forward backtesting."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .config import BacktestConfig, GRAHAM_BASELINE
from .indicators import add_market_indicators, winsorize_training_frame
from .metrics import sharpe_ratio, summarize_returns
from .optimizers import TrialLogger, genetic_algorithm, simulated_annealing
from .prices import price_on_or_after, price_return
from .screening import screen_period


INDICATOR_COLUMNS = [
    "pl", "pvpa", "roe", "margem_liquida",
    "liquidez_corrente", "divida_liquida_lucro_oper_proxy", "dividend_yield",
]


@dataclass(frozen=True)
class Fold:
    fold_id: int
    train_periods: list[str]
    validation_periods: list[str]
    test_periods: list[str]


@dataclass
class BacktestResult:
    summary_df: pd.DataFrame
    selection_df: pd.DataFrame
    convergence_data: dict[str, list[dict]] = field(default_factory=dict)
    strategy_returns: dict[str, pd.Series] = field(default_factory=dict)
    benchmark_series: pd.Series | None = None


def make_purged_walk_forward_folds(periods: list[str], config: BacktestConfig) -> list[Fold]:
    folds: list[Fold] = []
    n = len(periods)
    width = (
        config.train_periods + config.embargo_periods
        + config.validation_periods + config.embargo_periods
        + config.test_periods
    )
    start = 0
    fold_id = 1
    while start + width <= n:
        t0 = start
        t1 = t0 + config.train_periods
        v0 = t1 + config.embargo_periods
        v1 = v0 + config.validation_periods
        s0 = v1 + config.embargo_periods
        s1 = s0 + config.test_periods
        folds.append(Fold(fold_id, periods[t0:t1], periods[v0:v1], periods[s0:s1]))
        fold_id += 1
        start += config.step_periods
    return folds


def attach_rebalance_prices(fundamentals: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in fundamentals.iterrows():
        ticker = row.get("ticker")
        if pd.isna(ticker) or not str(ticker).strip():
            rows.append({**row.to_dict(), "execution_date": pd.NaT, "execution_price": np.nan, "market_cap": np.nan})
            continue
        execution_date, execution_price = price_on_or_after(prices, str(ticker), row["signal_date"])
        market_cap = np.nan
        if execution_price is not None and pd.notna(row.get("total_shares")):
            market_cap = execution_price * float(row["total_shares"])
        rows.append({
            **row.to_dict(),
            "execution_date": execution_date,
            "execution_price": execution_price,
            "market_cap": market_cap,
        })
    return add_market_indicators(pd.DataFrame(rows))


def period_returns(
    fundamentals: pd.DataFrame,
    prices: pd.DataFrame,
    theta: dict[str, float],
    periods: list[str],
    *,
    min_assets: int = 5,
    transaction_cost_bps: float = 0.0,
) -> tuple[pd.Series, pd.DataFrame]:
    period_order = list(fundamentals["periodo"].drop_duplicates())
    returns: dict[str, float] = {}
    rows: list[dict] = []
    previous_selection: set[str] = set()

    for period in periods:
        if period not in period_order:
            continue
        idx = period_order.index(period)
        if idx + 1 >= len(period_order):
            continue
        next_period = period_order[idx + 1]
        frame = fundamentals[fundamentals["periodo"] == period]
        next_signal_date = fundamentals.loc[fundamentals["periodo"] == next_period, "signal_date"].min()
        result = screen_period(frame, theta, min_assets=min_assets)
        selected = set(result.selected)

        asset_returns: list[float] = []
        for ticker in sorted(selected):
            start_date = frame.loc[frame["ticker"] == ticker, "signal_date"].min()
            if pd.isna(start_date):
                continue
            value = price_return(prices, ticker, start_date, next_signal_date)
            if value is not None:
                asset_returns.append(value)

        gross_return = float(np.mean(asset_returns)) if asset_returns else np.nan
        turnover = _turnover(previous_selection, selected)
        cost = turnover * transaction_cost_bps / 10_000.0
        net_return = gross_return - cost if not np.isnan(gross_return) else np.nan
        returns[period] = net_return
        rows.append({
            "periodo": period,
            "selected": ",".join(sorted(selected)),
            "n_assets": len(selected),
            "gross_return": gross_return,
            "turnover": turnover,
            "transaction_cost_bps": transaction_cost_bps,
            "net_return": net_return,
            "relaxed_rules": ",".join(result.relaxed_rules),
        })
        previous_selection = selected

    return pd.Series(returns, name="return", dtype="float64"), pd.DataFrame(rows)


def _turnover(previous: set[str], current: set[str]) -> float:
    if not previous and not current:
        return 0.0
    if not previous:
        return 1.0
    return 1.0 - (len(previous & current) / max(len(previous | current), 1))


def benchmark_returns(fundamentals: pd.DataFrame, prices: pd.DataFrame, periods: list[str], benchmark: str = "^BVSP") -> pd.Series:
    period_order = list(fundamentals["periodo"].drop_duplicates())
    out: dict[str, float] = {}
    for period in periods:
        idx = period_order.index(period)
        if idx + 1 >= len(period_order):
            continue
        start_date = fundamentals.loc[fundamentals["periodo"] == period, "signal_date"].min()
        next_date = fundamentals.loc[fundamentals["periodo"] == period_order[idx + 1], "signal_date"].min()
        value = price_return(prices, benchmark, start_date, next_date)
        out[period] = np.nan if value is None else value
    return pd.Series(out, name="benchmark_return", dtype="float64")


def evaluate_theta(
    fundamentals: pd.DataFrame,
    prices: pd.DataFrame,
    theta: dict[str, float],
    periods: list[str],
    *,
    config: BacktestConfig,
    transaction_cost_bps: float,
    risk_free: float = 0.0,
) -> float:
    returns, _ = period_returns(
        fundamentals, prices, theta, periods,
        min_assets=config.min_assets,
        transaction_cost_bps=transaction_cost_bps,
    )
    return sharpe_ratio(returns, risk_free=risk_free, periods_per_year=config.rebalance_frequency_per_year)


def run_backtest(
    fundamentals: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    config: BacktestConfig = BacktestConfig(),
    cost_bps: float = 10.0,
    seed: int = 42,
    trial_log_path: str | Path | None = None,
    risk_free: float = 0.0,
    ibrx100_history: pd.DataFrame | None = None,
) -> BacktestResult:
    if ibrx100_history is not None and not ibrx100_history.empty:
        from .ibrx100 import filter_by_ibrx100
        fundamentals = filter_by_ibrx100(fundamentals, ibrx100_history)

    prepared = attach_rebalance_prices(fundamentals, prices)
    periods = list(prepared["periodo"].drop_duplicates())
    folds = make_purged_walk_forward_folds(periods, config)
    if not folds:
        raise RuntimeError("Not enough periods for purged walk-forward protocol.")

    summaries: list[dict] = []
    selections: list[pd.DataFrame] = []
    convergence_data: dict[str, list[dict]] = {}
    # Acumula retornos por estrategia ao longo de todos os folds
    returns_by_strategy: dict[str, list[pd.Series]] = {}

    for fold in folds:
        train_frame = prepared[prepared["periodo"].isin(fold.train_periods)]
        train_frame = winsorize_training_frame(train_frame, INDICATOR_COLUMNS)
        fold_frame = pd.concat([train_frame, prepared[~prepared["periodo"].isin(fold.train_periods)]], ignore_index=True)

        def fit(theta: dict[str, float]) -> float:
            return evaluate_theta(
                fold_frame, prices, theta, fold.train_periods,
                config=config, transaction_cost_bps=cost_bps, risk_free=risk_free,
            )

        ga_logger = TrialLogger(trial_log_path, strategy=f"fold_{fold.fold_id}_ga")
        sa_logger = TrialLogger(trial_log_path, strategy=f"fold_{fold.fold_id}_sa")
        ga_result = genetic_algorithm(fit, seed=seed + fold.fold_id, logger=ga_logger)
        sa_result = simulated_annealing(fit, seed=seed + 1000 + fold.fold_id, logger=sa_logger)

        convergence_data[f"fold{fold.fold_id}_ga"] = ga_result.history
        convergence_data[f"fold{fold.fold_id}_sa"] = sa_result.history

        candidates = {"ga": ga_result, "sa": sa_result}
        val_scores = {
            name: evaluate_theta(
                fold_frame, prices, result.theta, fold.validation_periods,
                config=config, transaction_cost_bps=cost_bps, risk_free=risk_free,
            )
            for name, result in candidates.items()
        }
        chosen_name = max(val_scores, key=lambda k: -1e9 if np.isnan(val_scores[k]) else val_scores[k])
        chosen_theta = candidates[chosen_name].theta

        for strategy_name, theta, trials in [
            ("ga", ga_result.theta, ga_result.trials),
            ("sa", sa_result.theta, sa_result.trials),
            ("graham_fixed", GRAHAM_BASELINE, 1),
            (f"chosen_{chosen_name}", chosen_theta, ga_result.trials + sa_result.trials),
        ]:
            test_returns, selection = period_returns(
                fold_frame, prices, theta, fold.test_periods,
                min_assets=config.min_assets, transaction_cost_bps=cost_bps,
            )
            bench = benchmark_returns(fold_frame, prices, list(test_returns.index))
            metrics = summarize_returns(
                test_returns, bench,
                risk_free=risk_free,
                periods_per_year=config.rebalance_frequency_per_year,
                n_trials=trials,
                avg_assets=selection["n_assets"].mean() if not selection.empty else None,
                avg_turnover=selection["turnover"].mean() if not selection.empty else None,
                bootstrap=True,
            )
            summaries.append({
                "fold_id": fold.fold_id,
                "strategy": strategy_name,
                "chosen_by_validation": strategy_name == f"chosen_{chosen_name}",
                "train_periods": ",".join(fold.train_periods),
                "validation_periods": ",".join(fold.validation_periods),
                "test_periods": ",".join(fold.test_periods),
                "validation_sharpe_ga": val_scores["ga"],
                "validation_sharpe_sa": val_scores["sa"],
                "transaction_cost_bps": cost_bps,
                "risk_free_rate": risk_free,
                **metrics,
                **{f"theta_{k}": v for k, v in theta.items()},
            })
            if not selection.empty:
                selection = selection.assign(fold_id=fold.fold_id, strategy=strategy_name)
                selections.append(selection)

            # Normaliza o nome da estrategia para acumular retornos
            # "chosen_ga" e "chosen_sa" viram "chosen"
            plot_name = "chosen" if strategy_name.startswith("chosen_") else strategy_name
            returns_by_strategy.setdefault(plot_name, []).append(test_returns)

            # Benchmark tambem acumula
            returns_by_strategy.setdefault("ibovespa", []).append(bench)

    summary_df = pd.DataFrame(summaries)
    selection_df = pd.concat(selections, ignore_index=True) if selections else pd.DataFrame()

    # Concatena retornos de todos os folds por estrategia (sem duplicar periodos)
    strategy_returns: dict[str, pd.Series] = {}
    for name, series_list in returns_by_strategy.items():
        combined = pd.concat(series_list)
        # Se o mesmo periodo aparece em folds diferentes, mantém o primeiro
        strategy_returns[name] = combined.groupby(combined.index).first().sort_index()

    benchmark_series = strategy_returns.pop("ibovespa", None)

    return BacktestResult(
        summary_df=summary_df,
        selection_df=selection_df,
        convergence_data=convergence_data,
        strategy_returns=strategy_returns,
        benchmark_series=benchmark_series,
    )
