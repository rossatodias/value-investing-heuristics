"""Graficos do backtesting."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


_STYLE = {
    "font.family": "sans-serif",
    "font.size": 10,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 150,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.2,
}

_COLORS = {
    "ga": "#2196F3",
    "sa": "#FF9800",
    "graham_fixed": "#4CAF50",
    "benchmark": "#9E9E9E",
    "chosen": "#E91E63",
    "ibovespa": "#9E9E9E",
}


def _ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _color(name: str) -> str:
    for key, c in _COLORS.items():
        if key in name.lower():
            return c
    return "#607D8B"


# -- Convergencia AG --

def plot_convergence(history, title="Convergencia AG", path="outputs/plots/convergence.png"):
    out = _ensure_dir(path)
    with plt.rc_context(_STYLE):
        fig, ax = plt.subplots(figsize=(8, 4.5))
        gens = [h["generation"] for h in history]
        best = [h["best_fitness"] for h in history]
        ax.plot(gens, best, color=_COLORS["ga"], linewidth=2, label="Melhor fitness")

        if "current_best" in history[0]:
            cur = [h["current_best"] for h in history]
            ax.plot(gens, cur, color=_COLORS["ga"], alpha=0.3, linewidth=1, label="Fitness geracao")

        best_val = max(best)
        stab = max(g for g, f in zip(gens, best) if f == best_val)
        ax.axvline(stab, color=_COLORS["chosen"], linestyle="--", alpha=0.6,
                   label=f"Estabilizacao (gen {stab})")

        ax.set_xlabel("Geracao")
        ax.set_ylabel("Sharpe (fitness)")
        ax.set_title(title)
        ax.legend(loc="lower right", fontsize=8)
        fig.savefig(out)
        plt.close(fig)
    return out


# -- Trajetoria SA --

def plot_sa_trajectory(history, title="Trajetoria SA", path="outputs/plots/sa_trajectory.png"):
    out = _ensure_dir(path)
    with plt.rc_context(_STYLE):
        fig, ax1 = plt.subplots(figsize=(8, 4.5))
        iters = [h["iteration"] for h in history]
        best = [h["best_fitness"] for h in history]
        temp = [h["temperature"] for h in history]

        ax1.plot(iters, best, color=_COLORS["sa"], linewidth=2, label="Melhor fitness")
        ax1.set_xlabel("Iteracao")
        ax1.set_ylabel("Sharpe (fitness)", color=_COLORS["sa"])

        ax2 = ax1.twinx()
        ax2.plot(iters, temp, color="#B0BEC5", linewidth=1, alpha=0.6, label="Temperatura")
        ax2.set_ylabel("Temperatura", color="#B0BEC5")

        h1, l1 = ax1.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax1.legend(h1 + h2, l1 + l2, loc="center right", fontsize=8)
        ax1.set_title(title)
        fig.savefig(out)
        plt.close(fig)
    return out


# -- Retorno acumulado --

def plot_cumulative_returns(strategies, benchmark=None, title="Retorno Acumulado", path="outputs/plots/cumulative_returns.png"):
    out = _ensure_dir(path)
    with plt.rc_context(_STYLE):
        fig, ax = plt.subplots(figsize=(10, 5))

        for name, returns in strategies.items():
            returns = returns.sort_index()
            wealth = (1.0 + returns.fillna(0)).cumprod()
            ax.plot(range(len(wealth)), wealth.values, color=_color(name),
                    linewidth=2, label=name, marker="o", markersize=3)

        if benchmark is not None:
            benchmark = benchmark.sort_index()
            bw = (1.0 + benchmark.fillna(0)).cumprod()
            ax.plot(range(len(bw)), bw.values, color=_COLORS["benchmark"],
                    linewidth=2, linestyle="--", label="Ibovespa", marker="s", markersize=3)

        ax.axhline(1.0, color="black", linewidth=0.5, alpha=0.3)
        ax.set_xlabel("Periodo")
        ax.set_ylabel("Riqueza acumulada (base 1.0)")
        ax.set_title(title)
        ax.legend(fontsize=8)
        fig.savefig(out)
        plt.close(fig)
    return out


# -- Drawdown --

def plot_drawdown(strategies, title="Drawdown", path="outputs/plots/drawdown.png"):
    out = _ensure_dir(path)
    with plt.rc_context(_STYLE):
        fig, ax = plt.subplots(figsize=(10, 4))
        for name, returns in strategies.items():
            returns = returns.sort_index()
            wealth = (1.0 + returns.fillna(0)).cumprod()
            dd = (wealth / wealth.cummax() - 1.0) * 100
            c = _color(name)
            ax.fill_between(range(len(dd)), dd.values, 0, alpha=0.15, color=c)
            ax.plot(range(len(dd)), dd.values, color=c, linewidth=1.5, label=name)

        ax.set_xlabel("Periodo")
        ax.set_ylabel("Drawdown (%)")
        ax.set_title(title)
        ax.legend(fontsize=8)
        fig.savefig(out)
        plt.close(fig)
    return out


# -- Sharpe comparativo --

def plot_sharpe_comparison(summary, title="Sharpe por Estrategia", path="outputs/plots/sharpe_comparison.png"):
    out = _ensure_dir(path)
    has_ci = {"sharpe_ci_lower", "sharpe_ci_upper"}.issubset(summary.columns)

    agg = {"sharpe_mean": ("sharpe", "mean")}
    if has_ci:
        agg["ci_lower"] = ("sharpe_ci_lower", "mean")
        agg["ci_upper"] = ("sharpe_ci_upper", "mean")
    grouped = summary.groupby("strategy", as_index=False).agg(**agg).sort_values("sharpe_mean", ascending=False)

    with plt.rc_context(_STYLE):
        fig, ax = plt.subplots(figsize=(8, 5))
        x = range(len(grouped))
        colors = [_color(s) for s in grouped["strategy"]]

        yerr = None
        if has_ci:
            lo = (grouped["sharpe_mean"] - grouped["ci_lower"]).clip(lower=0).values
            hi = (grouped["ci_upper"] - grouped["sharpe_mean"]).clip(lower=0).values
            yerr = [lo, hi]

        ax.bar(x, grouped["sharpe_mean"].values, color=colors, alpha=0.8,
               yerr=yerr, capsize=4, edgecolor="white", linewidth=0.5)
        ax.set_xticks(list(x))
        ax.set_xticklabels(grouped["strategy"].values, rotation=30, ha="right", fontsize=8)
        ax.set_ylabel("Sharpe Ratio (media)")
        ax.set_title(title)
        ax.axhline(0, color="black", linewidth=0.5, alpha=0.3)

        if has_ci:
            ax.annotate("IC 95% bootstrap (1000 reamostras)", xy=(0.02, 0.02),
                        xycoords="axes fraction", fontsize=7, fontstyle="italic", color="#757575")

        fig.savefig(out)
        plt.close(fig)
    return out


# -- Composicao do portfolio --

def plot_portfolio_composition(selections, title="Composicao do Portfolio", path="outputs/plots/portfolio_composition.png"):
    if selections.empty:
        return _ensure_dir(path)

    out = _ensure_dir(path)
    with plt.rc_context(_STYLE):
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
        for strategy, group in selections.groupby("strategy"):
            c = _color(str(strategy))
            ax1.plot(group["periodo"], group["n_assets"], marker="o", markersize=4,
                     linewidth=1.5, color=c, label=str(strategy))
            ax2.plot(group["periodo"], group["turnover"], marker="s", markersize=4,
                     linewidth=1.5, color=c, label=str(strategy))

        ax1.set_ylabel("N. de ativos")
        ax1.set_title(title)
        ax1.legend(fontsize=7, ncol=2)
        ax2.set_ylabel("Turnover")
        ax2.set_xlabel("Periodo")
        ax2.legend(fontsize=7, ncol=2)
        plt.xticks(rotation=45, fontsize=7)
        fig.tight_layout()
        fig.savefig(out)
        plt.close(fig)
    return out


# -- Orquestrador --

def generate_all_plots(
    summary,
    selections,
    convergence_data=None,
    strategy_returns=None,
    benchmark_returns=None,
    output_dir="outputs/plots",
):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []

    if convergence_data:
        for key, history in convergence_data.items():
            if not history:
                continue
            if "generation" in history[0]:
                paths.append(plot_convergence(history, f"Convergencia AG — {key}",
                                              output_dir / f"convergence_{key}.png"))
            elif "iteration" in history[0]:
                paths.append(plot_sa_trajectory(history, f"Trajetoria SA — {key}",
                                                output_dir / f"sa_trajectory_{key}.png"))

    if strategy_returns:
        paths.append(plot_cumulative_returns(
            strategy_returns, benchmark=benchmark_returns,
            path=output_dir / "cumulative_returns.png",
        ))
        paths.append(plot_drawdown(
            strategy_returns, path=output_dir / "drawdown.png",
        ))

    if not summary.empty:
        paths.append(plot_sharpe_comparison(summary, path=output_dir / "sharpe_comparison.png"))

    if not selections.empty:
        paths.append(plot_portfolio_composition(selections, path=output_dir / "portfolio_composition.png"))

    return paths
