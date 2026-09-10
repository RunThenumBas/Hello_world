"""Market data access.

Wraps yfinance so the rest of the package depends on a plain pandas
DataFrame, not a specific provider. Swap `fetch_price_history` for another
data source later without touching indicators, scoring, or reporting.
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ("Open", "High", "Low", "Close", "Volume")


class DataUnavailableError(RuntimeError):
    """Raised when price history for a ticker cannot be retrieved."""


def fetch_price_history(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """Fetch OHLCV history for a single ticker.

    Raises DataUnavailableError if no usable data comes back, so callers can
    skip a ticker instead of crashing a whole report run.
    """
    import yfinance as yf

    try:
        history = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True)
    except Exception as exc:  # network/provider errors are non-fatal per ticker
        raise DataUnavailableError(f"{ticker}: fetch failed ({exc})") from exc

    if history is None or history.empty:
        raise DataUnavailableError(f"{ticker}: no price history returned")

    missing = [col for col in REQUIRED_COLUMNS if col not in history.columns]
    if missing:
        raise DataUnavailableError(f"{ticker}: missing columns {missing}")

    return history.dropna(subset=["Close"])


def fetch_many(tickers: list[str], period: str = "1y", interval: str = "1d") -> dict[str, pd.DataFrame]:
    """Fetch history for several tickers, skipping ones that fail."""
    results: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        try:
            results[ticker] = fetch_price_history(ticker, period=period, interval=interval)
        except DataUnavailableError as exc:
            logger.warning("Skipping %s: %s", ticker, exc)
    return results
