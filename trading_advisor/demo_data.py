"""Deterministic synthetic OHLCV data for offline use.

Not real market data. Lets you preview the report/dashboard (or iterate on
layout) without a live network connection, seeded per-ticker so results are
reproducible and vary across the watchlist instead of moving in lockstep.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd


def _seed_for(ticker: str) -> int:
    return int(hashlib.sha256(ticker.encode()).hexdigest(), 16) % (2**32)


def generate_demo_history(ticker: str, days: int = 300, start: float = 100.0) -> pd.DataFrame:
    rng = np.random.default_rng(_seed_for(ticker))
    drift = rng.uniform(-0.0025, 0.0025)
    returns = rng.normal(loc=drift, scale=0.018, size=days)
    close = start * np.cumprod(1 + returns)

    index = pd.date_range(end=pd.Timestamp.today().normalize(), periods=days, freq="D")
    high = close * (1 + rng.uniform(0, 0.012, size=days))
    low = close * (1 - rng.uniform(0, 0.012, size=days))
    open_ = close * (1 + rng.normal(0, 0.006, size=days))
    volume = rng.integers(500_000, 8_000_000, size=days)

    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=index,
    )
