"""Composicao do IBrX-100 para mitigacao de survivorship bias.

A API publica da B3 usa protecao Cloudflare, o que impede requests diretas.
Este modulo usa uma composicao estatica do IBrX-100 (atualizada periodicamente)
como aproximacao para filtrar o universo de ativos.

Para atualizar: acessar sistemaswebb3-listados.b3.com.br/indexPage/ via navegador,
selecionar IBXX, exportar a lista e substituir _IBRX100_STATIC abaixo.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


# Composicao aproximada do IBrX-100 (2024-2025)
# Fonte: B3 carteira teorica IBXX
_IBRX100_STATIC = [
    "ABEV3","ALPA4","ALOS3","ARZZ3","ASAI3","AZZA3","AZUL4",
    "B3SA3","BBAS3","BBDC4","BBSE3","BEEF3","BHIA3","BPAC11","BRAP4","BRFS3",
    "BRKM5",
    "CCRO3","CIEL3","CMIG4","COGN3","CPLE6","CPFE3","CSAN3","CVCB3","CXSE3",
    "ECOR3","EGIE3","ELET3","ELET6","EMBR3","ENEV3","ENGI11","EQTL3",
    "FLRY3",
    "GGBR4","GOAU4","GOLL4",
    "HAPV3","HYPE3",
    "IGTI11","IRBR3","ITSA4","ITUB4",
    "JBSS3","JHSF3",
    "KLBN11",
    "LREN3",
    "MGLU3","MRFG3","MRVE3","MULT3",
    "NTCO3",
    "PCAR3","PETR3","PETR4","PETZ3","POSI3","PRIO3",
    "RADL3","RAIL3","RAIZ4","RDOR3","RENT3","RRRP3",
    "SANB11","SBSP3","SLCE3","SMTO3","STBP3","SUZB3",
    "TAEE11","TIMS3","TOTS3","TRPL4",
    "UGPA3","USIM5",
    "VALE3","VAMO3","VBBR3","VIVT3","VULC3",
    "WEGE3",
    "YDUQ3",
]


def get_ibrx100_tickers():
    """Retorna set dos tickers do IBrX-100."""
    return set(_IBRX100_STATIC)


def build_ibrx100_history(years=None):
    """Constroi DataFrame com composicao para cada ano/segmento (composicao estatica)."""
    if years is None:
        years = list(range(2021, datetime.now().year + 1))

    ts = datetime.now(timezone.utc).isoformat()
    rows = []
    for year in years:
        for segment in (1, 2, 3):
            for ticker in _IBRX100_STATIC:
                rows.append({
                    "ticker": ticker,
                    "company": "",
                    "type": "",
                    "weight_pct": 1.0,
                    "theoretical_qty": 0,
                    "segment": segment,
                    "year": year,
                    "collected_at": ts,
                })
    return pd.DataFrame(rows)


def save_ibrx100_history(df, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def load_ibrx100_history(path):
    return pd.read_csv(path)


def tickers_for_period(history, year, quarter):
    """Tickers do IBrX-100 para um dado ano/trimestre."""
    _SEG_BY_MONTH = {1: 1, 2: 1, 3: 1, 4: 1, 5: 2, 6: 2, 7: 2, 8: 2, 9: 3, 10: 3, 11: 3, 12: 3}
    mid_month = {1: 2, 2: 5, 3: 8, 4: 11}[quarter]
    segment = _SEG_BY_MONTH[mid_month]
    mask = (history["year"] == year) & (history["segment"] == segment)
    subset = history.loc[mask, "ticker"]
    if subset.empty:
        subset = history.loc[history["year"] == year, "ticker"]
    return set(subset.str.upper().str.strip())


def filter_by_ibrx100(fundamentals, history):
    """Filtra fundamentals para manter apenas tickers que estavam no IBrX-100."""
    if history.empty:
        return fundamentals

    out = fundamentals.dropna(subset=["ticker"]).copy()
    keep = pd.Series(False, index=out.index)
    for (year, quarter), group in out.groupby(["ano", "trimestre"]):
        allowed = tickers_for_period(history, int(year), int(quarter))
        if allowed:
            keep.loc[group.index] = group["ticker"].str.upper().str.strip().isin(allowed)
        else:
            keep.loc[group.index] = True
    return out.loc[keep].reset_index(drop=True)
