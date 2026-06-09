import pandas as pd

from value_investing_heuristics.backtest import make_purged_walk_forward_folds, period_returns
from value_investing_heuristics.config import BacktestConfig, GRAHAM_BASELINE


def test_purged_walk_forward_respects_embargo():
    periods = [f"202{i}.1T" for i in range(20)]
    folds = make_purged_walk_forward_folds(periods, BacktestConfig())
    assert folds
    first = folds[0]
    assert first.train_periods[-1] == periods[7]
    assert first.validation_periods[0] == periods[9]
    assert first.test_periods[0] == periods[12]


def test_period_returns_executes_after_signal_date():
    fundamentals = pd.DataFrame(
        {
            "periodo": ["2024.1T", "2024.1T", "2024.2T", "2024.2T"],
            "ticker": ["AAA", "BBB", "AAA", "BBB"],
            "signal_date": pd.to_datetime(["2024-05-15", "2024-05-15", "2024-08-14", "2024-08-14"]),
            "pl": [10.0, 11.0, 10.0, 11.0],
            "pvpa": [1.0, 1.1, 1.0, 1.1],
            "roe": [0.2, 0.2, 0.2, 0.2],
            "margem_liquida": [0.1, 0.1, 0.1, 0.1],
            "liquidez_corrente": [2.1, 2.1, 2.1, 2.1],
            "divida_liquida_lucro_oper_proxy": [1.0, 1.0, 1.0, 1.0],
            "dividend_yield": [0.01, 0.01, 0.01, 0.01],
        }
    )
    prices = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-05-15", "2024-05-16", "2024-08-14", "2024-08-15"] * 2),
            "ticker": ["AAA"] * 4 + ["BBB"] * 4,
            "adj_close": [999, 100, 999, 110, 999, 200, 999, 220],
            "volume": [1] * 8,
        }
    )
    returns, details = period_returns(fundamentals, prices, GRAHAM_BASELINE, ["2024.1T"], min_assets=2)
    assert round(float(returns.iloc[0]), 6) == 0.10
    assert details.loc[0, "n_assets"] == 2
