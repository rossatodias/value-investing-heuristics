"""Download e consulta de precos ajustados."""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd


# Tickers que mudaram de codigo no Yahoo Finance
_YAHOO_ALIASES = {
    "CPLE6": "CPLE3",    # Copel PN -> ON
}

# Tickers temporariamente indisponiveis no Yahoo Finance
_KNOWN_UNAVAILABLE = {
    "EMBR3", "MRFG3", "AZUL4", "NTCO3", "BRFS3", "ELET3",
}


def yahoo_symbol(ticker):
    ticker = str(ticker).upper().replace(".SA", "").strip()
    if ticker.startswith("^"):
        return ticker
    ticker = _YAHOO_ALIASES.get(ticker, ticker)
    return f"{ticker}.SA"


def download_yahoo_prices(tickers, start, end, benchmark="^BVSP"):
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("pip install yfinance") from exc

    raw_tickers = sorted({str(t).upper().replace(".SA", "").strip() for t in tickers if str(t).strip()})
    symbol_to_b3 = {}
    for t in raw_tickers:
        sym = yahoo_symbol(t)
        symbol_to_b3[sym] = t

    symbols = sorted(symbol_to_b3.keys())
    if benchmark:
        symbols.append(benchmark)
        symbol_to_b3[benchmark] = benchmark

    frames = []
    failed = []

    for sym in symbols:
        b3_ticker = symbol_to_b3.get(sym, sym)
        for attempt in range(3):
            try:
                data = yf.download(sym, start=start, end=end, auto_adjust=True, progress=False)
                if not data.empty and len(data) > 5:
                    df = _extract_prices(data, sym, b3_ticker)
                    if df is not None and not df.empty:
                        frames.append(df)
                        break
            except Exception:
                pass
            time.sleep(0.5 * (attempt + 1))
        else:
            if b3_ticker not in _KNOWN_UNAVAILABLE and not b3_ticker.startswith("^"):
                failed.append(b3_ticker)

    if failed:
        print(f"Aviso: {len(failed)} tickers sem dados: {failed}")

    if not frames:
        raise RuntimeError("Nenhum preco baixado.")

    out = pd.concat(frames, ignore_index=True)
    return out.sort_values(["ticker", "date"]).reset_index(drop=True)


def _extract_prices(data, symbol, b3_ticker):
    """Extrai date, adj_close, volume de um DataFrame yfinance (suporta MultiIndex)."""
    out = data.copy()

    # yfinance >= 1.4 retorna MultiIndex columns: (Price, Ticker)
    if isinstance(out.columns, pd.MultiIndex):
        # Pegar Close (que eh adjusted com auto_adjust=True)
        if "Close" in out.columns.get_level_values(0):
            close = out["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
        else:
            return None

        volume = None
        if "Volume" in out.columns.get_level_values(0):
            vol = out["Volume"]
            if isinstance(vol, pd.DataFrame):
                vol = vol.iloc[:, 0]
            volume = vol

        result = pd.DataFrame({
            "date": close.index,
            "ticker": b3_ticker,
            "adj_close": close.values,
            "volume": volume.values if volume is not None else pd.NA,
        })
    else:
        # Fallback para formato flat (versoes antigas do yfinance)
        out = out.reset_index()
        date_col = "Date" if "Date" in out.columns else "Datetime"
        close_col = next((c for c in ["Adj Close", "Close", "adj_close", "close"] if c in out.columns), None)
        if close_col is None:
            return None
        result = pd.DataFrame({
            "date": out[date_col],
            "ticker": b3_ticker,
            "adj_close": out[close_col],
            "volume": out.get("Volume", out.get("volume", pd.NA)),
        })

    result["date"] = pd.to_datetime(result["date"]).dt.tz_localize(None)
    return result.dropna(subset=["adj_close"])


def load_prices(path):
    df = pd.read_csv(path, parse_dates=["date"])
    df["ticker"] = df["ticker"].astype("string").str.upper().str.replace(".SA", "", regex=False)
    return df.sort_values(["ticker", "date"]).reset_index(drop=True)


def save_prices(df, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def price_on_or_after(prices, ticker, date):
    subset = prices[(prices["ticker"] == ticker) & (prices["date"] > pd.Timestamp(date))]
    if subset.empty:
        return None, None
    row = subset.sort_values("date").iloc[0]
    return row["date"], float(row["adj_close"])


def price_return(prices, ticker, start_date, end_date):
    start_exec, start_price = price_on_or_after(prices, ticker, start_date)
    end_exec, end_price = price_on_or_after(prices, ticker, end_date)
    if start_exec is None or end_exec is None or start_price in (None, 0) or end_price is None:
        return None
    if end_exec <= start_exec:
        return None
    return (end_price / start_price) - 1.0
