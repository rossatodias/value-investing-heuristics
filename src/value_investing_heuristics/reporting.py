"""Relatorio markdown do backtesting."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_backtest_report(summary, selections, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Relatorio de Backtesting PO-236",
        "",
        "Walk-forward purgado com embargo. O backtest e validacao final, nao ferramenta de descoberta.",
        "",
        "## Controles",
        "",
        "- Look-ahead bias: sinais apos `signal_date`, execucao no proximo fechamento.",
        "- Data snooping: tentativas registradas no log de trials.",
        "- Test-set leakage: teste nao participa da escolha de parametros.",
        "- Custos: retornos liquidos por turnover (bps).",
        "- Long-only, winsorizacao apenas no treino.",
        "- Survivorship bias: filtro IBrX-100 (quando disponivel).",
        "- Rf: CDI anualizado (serie 4389/BCB).",
        "",
    ]

    if summary.empty:
        lines.extend(["## Resultados", "", "Nenhum resultado gerado."])
    else:
        has_ci = {"sharpe_ci_lower", "sharpe_ci_upper"}.issubset(summary.columns)

        cols = ["fold_id", "strategy", "test_periods", "transaction_cost_bps"]
        if "risk_free_rate" in summary.columns:
            cols.append("risk_free_rate")
        cols.append("cumulative_return")
        cols.append("sharpe")
        if has_ci:
            cols.extend(["sharpe_ci_lower", "sharpe_ci_upper"])
        cols.extend(["deflated_sharpe_proxy", "sortino", "max_drawdown", "avg_assets", "avg_turnover"])
        cols = [c for c in cols if c in summary.columns]

        lines.extend(["## Resultados por fold", "", summary[cols].to_markdown(index=False), ""])

        agg_cols = ["cumulative_return", "sharpe", "deflated_sharpe_proxy", "sortino",
                    "max_drawdown", "avg_assets", "avg_turnover"]
        if has_ci:
            agg_cols.extend(["sharpe_ci_lower", "sharpe_ci_upper"])
        agg_cols = [c for c in agg_cols if c in summary.columns]

        grouped = (summary.groupby("strategy", as_index=False)[agg_cols]
                   .mean(numeric_only=True).sort_values("sharpe", ascending=False))
        lines.extend(["## Media por estrategia", "", grouped.to_markdown(index=False), ""])

        if has_ci:
            lines.extend([
                "> **Nota:** IC 95% via bootstrap (1000 reamostras). Carater exploratorio.",
                "",
            ])

    if not selections.empty:
        show = ["fold_id", "strategy", "periodo", "selected", "n_assets", "turnover", "relaxed_rules"]
        lines.extend(["## Selecoes", "", selections[show].head(50).to_markdown(index=False), ""])

    lines.extend([
        "## Limitacoes",
        "",
        "- `deflated_sharpe_proxy`: penalizacao conservadora, nao DSR completo.",
        "- Depende da qualidade do de/para CNPJ->ticker e precos ajustados.",
        "- Amostra 2021-2025: curta para conclusoes estatisticas fortes.",
        "- Custos simplificados em bps.",
        "- Bounds do otimizador: P/VPA em [0.3, 0.7]. Baseline Graham: P/VPA <= 1.5.",
    ])
    Path(path).write_text("\n".join(lines), encoding="utf-8")
