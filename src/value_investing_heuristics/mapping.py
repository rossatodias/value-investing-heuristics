"""CNPJ to ticker mapping."""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .data import normalize_cnpj


# Mapeamento validado via CVM Dados Abertos + B3
# Cobre os CNPJs presentes no itr_completo.csv do projeto
_KNOWN_CNPJ_TICKER = {
    "00000000000191": "BBAS3",
    "00001180000126": "JHSF3",
    "00864214000106": "RADL3",
    "02387241000160": "HAPV3",
    "02429144000193": "ECOR3",
    "02558157000162": "CVCB3",
    "02800026000140": "MRFG3",
    "03220438000173": "TOTS3",
    "04423567000121": "POSI3",
    "07526557000100": "NTCO3",
    "07689002000189": "RAIZ4",
    "07859971000130": "BBSE3",
    "08312229000173": "TAEE11",
    "08807432000110": "PCAR3",
    "09346601000125": "VIVT3",
    "10629105000168": "BPAC11",
    "16404287000155": "AZZA3",
    "16670085000155": "ENEV3",
    "17155730000164": "EQTL3",
    "33000167000101": "PETR4",
    "33042730000104": "EMBR3",
    "33256439000139": "ELET3",
    "33611500000119": "VALE3",
    "42150391000170": "SUZB3",
    "50746577000115": "AZUL4",
    "53113791000122": "RENT3",
    "60840055000131": "SBSP3",
    "60894730000105": "ITUB4",
    "61079117000105": "BRFS3",
    "67620377000114": "ABEV3",
    "84429695000111": "WEGE3",
    "89096457000155": "CPLE6",
    "89637490000145": "CMIG4",
    "92690783000109": "SLCE3",
    "97837181000147": "GGBR4",
}


def mapping_template(cnpjs):
    collected_at = datetime.now(timezone.utc).isoformat()
    return pd.DataFrame({
        "cnpj_norm": [normalize_cnpj(c) for c in sorted(set(cnpjs))],
        "ticker": "",
        "source": "pending",
        "confidence": 0.0,
        "selected": False,
        "collected_at": collected_at,
        "notes": "Sem correspondencia publica validada.",
    })


def load_mapping(path):
    df = pd.read_csv(path, dtype={"cnpj_norm": "string", "ticker": "string"})
    if "cnpj" in df.columns and "cnpj_norm" not in df.columns:
        df["cnpj_norm"] = df["cnpj"].map(normalize_cnpj)
    df["cnpj_norm"] = df["cnpj_norm"].map(normalize_cnpj)
    df["ticker"] = df["ticker"].astype("string").str.upper().str.replace(".SA", "", regex=False)
    if "selected" not in df.columns:
        df["selected"] = True
    else:
        df["selected"] = df["selected"].map(_as_bool)
    return df


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y", "sim"}


def save_mapping(df, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def merge_mapping(fundamentals, mapping, selected_only=True):
    m = mapping.copy()
    if selected_only and "selected" in m.columns:
        m = m[m["selected"].astype(bool)]
    cols = [c for c in ["cnpj_norm", "ticker", "source", "confidence"] if c in m.columns]
    out = fundamentals.merge(m[cols], on="cnpj_norm", how="left")
    out["ticker"] = out["ticker"].astype("string").str.upper().str.replace(".SA", "", regex=False)
    return out


def build_mapping_from_known(cnpjs):
    """Constroi mapping usando dicionario interno de CNPJs conhecidos."""
    ts = datetime.now(timezone.utc).isoformat()
    rows = []
    for cnpj in sorted(set(cnpjs)):
        cnpj_clean = normalize_cnpj(cnpj)
        ticker = _KNOWN_CNPJ_TICKER.get(cnpj_clean, "")
        rows.append({
            "cnpj_norm": cnpj_clean,
            "ticker": ticker,
            "source": "cvm_validated" if ticker else "pending",
            "confidence": 1.0 if ticker else 0.0,
            "selected": bool(ticker),
            "collected_at": ts,
            "notes": "Mapeamento validado via CVM/B3." if ticker else "CNPJ sem ticker no dicionario.",
        })
    return pd.DataFrame(rows)


def _extract_cnpj(text):
    match = re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", text)
    return normalize_cnpj(match.group(0)) if match else ""


def fetch_fundamentus_mapping(target_cnpjs, *, sleep_seconds=0.5, timeout=20.0, max_tickers=None):
    """Tenta resolver CNPJs via Fundamentus; usa dicionario interno como fallback."""
    target = {normalize_cnpj(c) for c in target_cnpjs}

    # Tenta primeiro o dicionario interno (rapido e confiavel)
    known_result = build_mapping_from_known(list(target))
    resolved = set(known_result.loc[known_result["selected"], "cnpj_norm"])
    pending = target - resolved

    if not pending:
        return known_result

    # Para CNPJs nao resolvidos, tenta Fundamentus
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 value-investing-heuristics academic project"})

    base_url, response = _get_fundamentus(session, "resultado.php", timeout)
    if response is None:
        return known_result

    tables = pd.read_html(response.text)
    if not tables:
        return known_result

    tickers = sorted({str(t).upper().strip() for t in tables[0]["Papel"].dropna()})
    if max_tickers is not None:
        tickers = tickers[:max_tickers]

    collected_at = datetime.now(timezone.utc).isoformat()
    extra = []
    for ticker in tickers:
        if not pending:
            break
        try:
            detail = session.get(f"{base_url}/detalhes.php?papel={ticker}", timeout=timeout)
            if detail.status_code != 200:
                continue
            soup = BeautifulSoup(detail.text, "lxml")
            cnpj = _extract_cnpj(soup.get_text(" "))
            if cnpj in pending:
                extra.append({
                    "cnpj_norm": cnpj, "ticker": ticker, "source": "fundamentus",
                    "confidence": 1.0, "selected": True,
                    "collected_at": collected_at, "notes": "Match CNPJ exato via Fundamentus.",
                })
                pending.discard(cnpj)
        except requests.RequestException:
            continue
        time.sleep(sleep_seconds)

    if extra:
        extra_df = pd.DataFrame(extra)
        # Substituir as linhas 'pending' que foram resolvidas
        resolved_cnpjs = set(extra_df["cnpj_norm"])
        known_result = known_result[~known_result["cnpj_norm"].isin(resolved_cnpjs)]
        known_result = pd.concat([known_result, extra_df], ignore_index=True)

    return known_result.sort_values("cnpj_norm").reset_index(drop=True)


def _get_fundamentus(session, path, timeout):
    for base_url in ("https://www.fundamentus.com.br", "http://www.fundamentus.com.br"):
        try:
            response = session.get(f"{base_url}/{path}", timeout=timeout)
            response.raise_for_status()
            return base_url, response
        except requests.RequestException:
            continue
    return "https://www.fundamentus.com.br", None
