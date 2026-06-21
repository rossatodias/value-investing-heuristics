"""Command line interface."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

from .backtest import run_backtest
from .config import DATA_PROCESSED, DATA_RAW, DEFAULT_INPUT, OUTPUTS, BacktestConfig
from .data import add_signal_dates, dataset_profile, load_itr_csv, save_profile
from .indicators import add_fundamental_indicators
from .mapping import fetch_fundamentus_mapping, load_mapping, mapping_template, merge_mapping, save_mapping
from .prices import download_yahoo_prices, load_prices, save_prices
from .reporting import write_backtest_report


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(prog="vih", description="Value investing heuristics pipeline.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prepare = sub.add_parser("prepare", help="Prepare ITR data and fundamental indicators.")
    p_prepare.add_argument("--input", default=str(DEFAULT_INPUT))
    p_prepare.add_argument("--output", default=str(DATA_PROCESSED / "fundamentals.csv"))
    p_prepare.add_argument("--profile", default=str(OUTPUTS / "data_profile.json"))
    p_prepare.add_argument("--lag-days", type=int, default=45)

    p_template = sub.add_parser("mapping-template", help="Create a CNPJ -> ticker mapping template.")
    p_template.add_argument("--fundamentals", default=str(DATA_PROCESSED / "fundamentals.csv"))
    p_template.add_argument("--output", default=str(DATA_RAW / "cnpj_ticker_map.csv"))

    p_map = sub.add_parser("fetch-mapping", help="Fetch CNPJ -> ticker mapping from public sources.")
    p_map.add_argument("--fundamentals", default=str(DATA_PROCESSED / "fundamentals.csv"))
    p_map.add_argument("--output", default=str(DATA_RAW / "cnpj_ticker_map.csv"))
    p_map.add_argument("--max-tickers", type=int, default=None)
    p_map.add_argument("--sleep", type=float, default=0.5)

    p_prices = sub.add_parser("fetch-prices", help="Download adjusted prices from Yahoo Finance.")
    p_prices.add_argument("--mapping", default=str(DATA_RAW / "cnpj_ticker_map.csv"))
    p_prices.add_argument("--output", default=str(DATA_RAW / "prices.csv"))
    p_prices.add_argument("--start", default="2021-01-01")
    p_prices.add_argument("--end", default=None)
    p_prices.add_argument("--benchmark", default="^BVSP")

    p_cdi = sub.add_parser("fetch-cdi", help="Download CDI series from BCB (risk-free rate).")
    p_cdi.add_argument("--output", default=str(DATA_PROCESSED / "cdi.csv"))
    p_cdi.add_argument("--start", default="2020-01-01")
    p_cdi.add_argument("--end", default=None)

    p_ibrx = sub.add_parser("fetch-ibrx100", help="Download IBrX-100 composition from B3.")
    p_ibrx.add_argument("--output", default=str(DATA_PROCESSED / "ibrx100_history.csv"))
    p_ibrx.add_argument("--start-year", type=int, default=2021)
    p_ibrx.add_argument("--end-year", type=int, default=None)
    p_ibrx.add_argument("--sleep", type=float, default=1.0)

    p_backtest = sub.add_parser("backtest", help="Run purged walk-forward backtest.")
    p_backtest.add_argument("--fundamentals", default=str(DATA_PROCESSED / "fundamentals.csv"))
    p_backtest.add_argument("--mapping", default=str(DATA_RAW / "cnpj_ticker_map.csv"))
    p_backtest.add_argument("--prices", default=str(DATA_RAW / "prices.csv"))
    p_backtest.add_argument("--cdi", default=str(DATA_PROCESSED / "cdi.csv"))
    p_backtest.add_argument("--ibrx-history", default=str(DATA_PROCESSED / "ibrx100_history.csv"))
    p_backtest.add_argument("--summary", default=str(OUTPUTS / "backtest_summary.csv"))
    p_backtest.add_argument("--selections", default=str(OUTPUTS / "backtest_selections.csv"))
    p_backtest.add_argument("--trial-log", default=str(OUTPUTS / "backtest_trials.csv"))
    p_backtest.add_argument("--report", default=str(OUTPUTS / "backtest_report.md"))
    p_backtest.add_argument("--plots-dir", default=str(OUTPUTS / "plots"))
    p_backtest.add_argument("--cost-bps", type=float, default=10.0)
    p_backtest.add_argument("--seed", type=int, default=42)
    p_backtest.add_argument("--no-plots", action="store_true", help="Skip plot generation.")

    p_all = sub.add_parser("run-all", help="Run prepare + backtest using existing mapping/prices.")
    p_all.add_argument("--input", default=str(DEFAULT_INPUT))
    p_all.add_argument("--mapping", default=str(DATA_RAW / "cnpj_ticker_map.csv"))
    p_all.add_argument("--prices", default=str(DATA_RAW / "prices.csv"))
    p_all.add_argument("--cost-bps", type=float, default=10.0)

    args = parser.parse_args(argv)

    if args.command == "prepare":
        prepare(args.input, args.output, args.profile, args.lag_days)
    elif args.command == "mapping-template":
        create_mapping_template(args.fundamentals, args.output)
    elif args.command == "fetch-mapping":
        fetch_mapping(args.fundamentals, args.output, args.max_tickers, args.sleep)
    elif args.command == "fetch-prices":
        fetch_prices(args.mapping, args.output, args.start, args.end, args.benchmark)
    elif args.command == "fetch-cdi":
        cmd_fetch_cdi(args)
    elif args.command == "fetch-ibrx100":
        cmd_fetch_ibrx100(args)
    elif args.command == "backtest":
        backtest(args)
    elif args.command == "run-all":
        fundamentals = DATA_PROCESSED / "fundamentals.csv"
        profile = OUTPUTS / "data_profile.json"
        prepare(args.input, fundamentals, profile, 45)
        backtest_args = argparse.Namespace(
            fundamentals=str(fundamentals),
            mapping=args.mapping,
            prices=args.prices,
            cdi=str(DATA_PROCESSED / "cdi.csv"),
            ibrx_history=str(DATA_PROCESSED / "ibrx100_history.csv"),
            summary=str(OUTPUTS / "backtest_summary.csv"),
            selections=str(OUTPUTS / "backtest_selections.csv"),
            trial_log=str(OUTPUTS / "backtest_trials.csv"),
            report=str(OUTPUTS / "backtest_report.md"),
            plots_dir=str(OUTPUTS / "plots"),
            cost_bps=args.cost_bps,
            seed=42,
            no_plots=False,
        )
        backtest(backtest_args)
    return 0


def prepare(input_path: str | Path, output_path: str | Path, profile_path: str | Path, lag_days: int) -> None:
    df = load_itr_csv(input_path)
    df = add_signal_dates(df, lag_days=lag_days)
    df = add_fundamental_indicators(df)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    save_profile(dataset_profile(df), profile_path)
    log.info("Prepared fundamentals: %s", output_path)


def create_mapping_template(fundamentals_path: str | Path, output_path: str | Path) -> None:
    df = pd.read_csv(fundamentals_path, dtype={"cnpj_norm": "string"})
    template = mapping_template(list(df["cnpj_norm"].dropna().unique()))
    save_mapping(template, output_path)
    log.info("Mapping template: %s", output_path)


def fetch_mapping(fundamentals_path: str | Path, output_path: str | Path, max_tickers: int | None, sleep: float) -> None:
    df = pd.read_csv(fundamentals_path, dtype={"cnpj_norm": "string"})
    mapping = fetch_fundamentus_mapping(list(df["cnpj_norm"].dropna().unique()), max_tickers=max_tickers, sleep_seconds=sleep)
    save_mapping(mapping, output_path)
    log.info("Mapping saved: %s", output_path)


def fetch_prices(mapping_path: str | Path, output_path: str | Path, start: str, end: str | None, benchmark: str) -> None:
    mapping = load_mapping(mapping_path)
    tickers = list(mapping.loc[mapping["selected"].astype(bool), "ticker"].dropna().unique())
    prices = download_yahoo_prices(tickers, start=start, end=end, benchmark=benchmark)
    save_prices(prices, output_path)
    log.info("Prices saved: %s", output_path)


def cmd_fetch_cdi(args: argparse.Namespace) -> None:
    from .cdi import fetch_cdi_series, save_cdi

    log.info("Downloading CDI series from BCB (series 4389)...")
    df = fetch_cdi_series(start=args.start, end=args.end)
    save_cdi(df, args.output)
    log.info("CDI series saved (%d rows): %s", len(df), args.output)


def cmd_fetch_ibrx100(args: argparse.Namespace) -> None:
    from .ibrx100 import build_ibrx100_history, save_ibrx100_history
    from datetime import datetime

    end_year = args.end_year or datetime.now().year
    years = list(range(args.start_year, end_year + 1))
    log.info("Building IBrX-100 compositions for years %d-%d...", years[0], years[-1])
    df = build_ibrx100_history(years=years)
    save_ibrx100_history(df, args.output)
    n_tickers = df["ticker"].nunique() if not df.empty else 0
    log.info("IBrX-100 history saved (%d rows, %d unique tickers): %s", len(df), n_tickers, args.output)


def backtest(args: argparse.Namespace) -> None:
    fundamentals = pd.read_csv(args.fundamentals, parse_dates=["period_end", "signal_date"], dtype={"cnpj_norm": "string"})
    mapping = load_mapping(args.mapping)
    fundamentals = merge_mapping(fundamentals, mapping)
    prices = load_prices(args.prices)
    config = BacktestConfig()

    risk_free = 0.0
    cdi_path = Path(args.cdi)
    if cdi_path.exists():
        from .cdi import load_cdi, cdi_annual_rate_for_year

        cdi_df = load_cdi(cdi_path)
        # Mean CDI rate across the years present in fundamentals, as a simple proxy.
        years = fundamentals["ano"].dropna().unique()
        rates = [cdi_annual_rate_for_year(cdi_df, int(y)) for y in years]
        valid_rates = [r for r in rates if r > 0]
        if valid_rates:
            risk_free = sum(valid_rates) / len(valid_rates)
            log.info("Risk-free rate (CDI mean): %.4f (%.2f%%)", risk_free, risk_free * 100)
    else:
        log.warning("CDI file not found (%s), using Rf=0. Run 'vih fetch-cdi' first.", cdi_path)

    ibrx_history = None
    ibrx_path = Path(args.ibrx_history)
    if ibrx_path.exists():
        from .ibrx100 import load_ibrx100_history

        ibrx_history = load_ibrx100_history(ibrx_path)
        n_tickers = ibrx_history["ticker"].nunique() if not ibrx_history.empty else 0
        log.info("IBrX-100 history loaded (%d unique tickers).", n_tickers)
    else:
        log.warning("IBrX-100 history not found (%s), skipping survivorship filter. Run 'vih fetch-ibrx100' first.", ibrx_path)

    result = run_backtest(
        fundamentals,
        prices,
        config=config,
        cost_bps=args.cost_bps,
        seed=args.seed,
        trial_log_path=args.trial_log,
        risk_free=risk_free,
        ibrx100_history=ibrx_history,
    )

    Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
    result.summary_df.to_csv(args.summary, index=False)
    result.selection_df.to_csv(args.selections, index=False)
    write_backtest_report(result.summary_df, result.selection_df, args.report)
    log.info("Backtest summary: %s", args.summary)
    log.info("Backtest report: %s", args.report)

    if not args.no_plots:
        from .plotting import generate_all_plots

        paths = generate_all_plots(
            summary=result.summary_df,
            selections=result.selection_df,
            convergence_data=result.convergence_data,
            strategy_returns=result.strategy_returns,
            benchmark_returns=result.benchmark_series,
            output_dir=args.plots_dir,
        )
        log.info("Plots generated (%d files): %s", len(paths), args.plots_dir)


if __name__ == "__main__":
    raise SystemExit(main())
