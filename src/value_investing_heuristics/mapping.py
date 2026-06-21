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


# Mapeamento validado via maisretorno.com (fonte publica B3) + CVM Dados Abertos
# Cobre os 34 CNPJs presentes no itr_completo.csv do projeto
# Ticker selecionado = mais liquido (preferencial quando disponivel; units quando aplicavel)
_KNOWN_CNPJ_TICKER = {
    "00001180000126": "ELET6",   # Centrais Eletricas Brasileiras (Eletrobras) - PNB
    "00864214000106": "ENGI11",  # Energisa - Units
    "02387241000160": "RAIL3",   # Rumo (logistica ferroviaria)
    "02429144000193": "CPFE3",   # CPFL Energia
    "02558157000162": "VIVT3",   # Telefonica Brasil (Vivo)
    "02800026000140": "COGN3",   # Cogna Educacao
    "03220438000173": "EQTL3",   # Equatorial Energia
    "04423567000121": "ENEV3",   # Eneva
    "07526557000100": "ABEV3",   # Ambev
    "07689002000189": "EMBR3",   # Embraer
    "07859971000130": "TAEE11",  # Taesa - Units
    "08312229000173": "EZTC3",   # EZ Tec (incorporadora)
    "08807432000110": "YDUQ3",   # Yduqs (ex-Estacio)
    "09346601000125": "B3SA3",   # B3 (bolsa)
    "10629105000168": "PRIO3",   # Prio (ex-Petro Rio)
    "16404287000155": "SUZB3",   # Suzano
    "16670085000155": "RENT3",   # Localiza Rent a Car
    "17155730000164": "CMIG4",   # Cemig - PN
    "33000167000101": "PETR4",   # Petrobras - PN
    "33042730000104": "CSNA3",   # Companhia Siderurgica Nacional (CSN)
    "33256439000139": "UGPA3",   # Ultrapar
    "33611500000119": "GGBR4",   # Gerdau - PN
    "42150391000170": "BRKM5",   # Braskem - PNA
    "50746577000115": "CSAN3",   # Cosan
    "53113791000122": "TOTS3",   # Totvs
    "60840055000131": "FLRY3",   # Fleury (laboratorios)
    "60894730000105": "USIM5",   # Usiminas - PNA
    "61079117000105": "ALPA4",   # Alpargatas - PN
    "67620377000114": "BEEF3",   # Minerva (carnes)
    "84429695000111": "WEGE3",   # WEG
    "89096457000155": "SLCE3",   # SLC Agricola
    "89637490000145": "KLBN11",  # Klabin - Units
    "92690783000109": "GOAU4",   # Metalurgica Gerdau - PN
    "97837181000147": "DXCO3",   # Dexco (ex-Duratex)
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
    # ticker already normalized by load_mapping; the merge only adds NaN for misses.
    return fundamentals.merge(m[cols], on="cnpj_norm", how="left")


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
