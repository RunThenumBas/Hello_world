"""Technical indicators computed from plain OHLCV DataFrames.

No external TA library dependency -- these are the handful of indicators the
scoring model needs, implemented directly against pandas so behavior is
transparent and easy to unit test with synthetic data.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def sma(close: pd.Series, window: int) -> pd.Series:
    return close.rolling(window=window, min_periods=window).mean()


def ema(close: pd.Series, span: int) -> pd.Series:
    return close.ewm(span=span, adjust=False).mean()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))
    return result.fillna(50)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series]:
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = ema(macd_line, signal)
    return macd_line, signal_line


def annualized_volatility(close: pd.Series, window: int = 20) -> pd.Series:
    daily_returns = close.pct_change()
    return daily_returns.rolling(window=window).std() * np.sqrt(252)


def drawdown_from_high(close: pd.Series, window: int = 252) -> float:
    """How far the latest close sits below its trailing high (0 = at high)."""
    trailing_high = close.tail(window).max()
    latest = close.iloc[-1]
    if trailing_high <= 0:
        return 0.0
    return (trailing_high - latest) / trailing_high


@dataclass(frozen=True)
class IndicatorSnapshot:
    ticker: str
    last_close: float
    sma50: float
    sma200: float
    rsi14: float
    macd_line: float
    macd_signal: float
    volatility: float
    drawdown_from_52w_high: float
    pct_change_3m: float


def compute_snapshot(ticker: str, history: pd.DataFrame) -> IndicatorSnapshot:
    close = history["Close"]
    sma50_series = sma(close, 50)
    sma200_series = sma(close, 200)
    rsi_series = rsi(close)
    macd_line, macd_signal = macd(close)
    vol_series = annualized_volatility(close)

    lookback_3m = min(len(close) - 1, 63)
    pct_change_3m = 0.0
    if lookback_3m > 0 and close.iloc[-1 - lookback_3m] != 0:
        pct_change_3m = (close.iloc[-1] / close.iloc[-1 - lookback_3m]) - 1

    def _last(series: pd.Series) -> float:
        value = series.dropna()
        return float(value.iloc[-1]) if not value.empty else float("nan")

    return IndicatorSnapshot(
        ticker=ticker,
        last_close=float(close.iloc[-1]),
        sma50=_last(sma50_series),
        sma200=_last(sma200_series),
        rsi14=_last(rsi_series),
        macd_line=_last(macd_line),
        macd_signal=_last(macd_signal),
        volatility=_last(vol_series),
        drawdown_from_52w_high=drawdown_from_high(close),
        pct_change_3m=float(pct_change_3m),
    )
