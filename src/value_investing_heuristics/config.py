"""Project configuration defaults."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "itr_completo.csv"
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
OUTPUTS = ROOT / "outputs"


NUMERIC_COLUMNS = [
    "versao",
    "tipo",
    "passivoTotal",
    "ativoTotal",
    "ativoCirc",
    "caixa",
    "aplicacoesFin",
    "disponivel",
    "contasReceber",
    "estoques",
    "ativoLP",
    "passivoCirc",
    "passivoLP",
    "dividaBruta",
    "dividaLiq",
    "patLiq",
    "receitaBruta",
    "cmv",
    "lucroBruto",
    "despesasOper",
    "lucroOper",
    "receitasDespesasFin",
    "impostoRenda",
    "lair",
    "lucroLiq",
    "dividendosPagos",
    "jcp",
    "total_shares",
    "on_shares",
    "pn_shares",
    "ano",
    "trimestre",
]


@dataclass(frozen=True)
class BacktestConfig:
    train_periods: int = 8
    embargo_periods: int = 1
    validation_periods: int = 2
    test_periods: int = 1
    step_periods: int = 1
    min_assets: int = 5
    reporting_lag_days: int = 45
    rebalance_frequency_per_year: int = 4
    transaction_cost_bps: tuple[float, ...] = (0.0, 10.0, 25.0)


THETA_BOUNDS = {
    "max_pl": (1.0, 25.0),
    "max_pvpa": (0.3, 0.7),
    "min_roe": (0.0, 0.30),
    "min_margem_liquida": (-0.10, 0.30),
    "min_liquidez_corrente": (0.5, 3.0),
    "max_divida_liquida_lucro_oper_proxy": (0.0, 6.0),
    "min_dividend_yield": (0.0, 0.15),
}

GRAHAM_BASELINE = {
    "max_pl": 15.0,
    "max_pvpa": 1.5,
    "min_roe": 0.10,
    "min_margem_liquida": -0.10,
    "min_liquidez_corrente": 2.0,
    "max_divida_liquida_lucro_oper_proxy": 3.0,
    "min_dividend_yield": 0.0,
}
