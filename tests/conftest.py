import numpy as np
import pandas as pd
import pytest


def make_price_history(days: int = 300, start: float = 100.0, drift: float = 0.0, seed: int = 0) -> pd.DataFrame:
    """Synthetic OHLCV series: a random walk with a configurable drift."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(loc=drift, scale=0.01, size=days)
    close = start * np.cumprod(1 + returns)
    index = pd.date_range(end=pd.Timestamp.today(), periods=days, freq="D")

    high = close * (1 + rng.uniform(0, 0.01, size=days))
    low = close * (1 - rng.uniform(0, 0.01, size=days))
    open_ = close * (1 + rng.normal(0, 0.005, size=days))
    volume = rng.integers(1_000_000, 5_000_000, size=days)

    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=index,
    )


@pytest.fixture
def uptrend_history() -> pd.DataFrame:
    return make_price_history(days=300, drift=0.003, seed=1)


@pytest.fixture
def downtrend_history() -> pd.DataFrame:
    return make_price_history(days=300, drift=-0.003, seed=2)


@pytest.fixture
def flat_history() -> pd.DataFrame:
    """A perfectly flat series (0% return throughout) for deterministic benchmark comparisons."""
    days = 300
    close = np.full(days, 100.0)
    index = pd.date_range(end=pd.Timestamp.today(), periods=days, freq="D")
    return pd.DataFrame(
        {"Open": close, "High": close, "Low": close, "Close": close, "Volume": np.full(days, 1_000_000)},
        index=index,
    )
