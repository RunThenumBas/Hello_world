from trading_advisor.indicators import compute_snapshot, rsi, sma


def test_sma_matches_manual_average():
    import pandas as pd

    close = pd.Series([1, 2, 3, 4, 5], dtype=float)
    result = sma(close, window=3)
    assert result.iloc[-1] == (3 + 4 + 5) / 3
    assert result.iloc[:2].isna().all()


def test_rsi_stays_within_bounds(uptrend_history):
    values = rsi(uptrend_history["Close"]).dropna()
    assert (values >= 0).all() and (values <= 100).all()


def test_uptrend_snapshot_has_higher_rsi_than_downtrend(uptrend_history, downtrend_history):
    up_snap = compute_snapshot("UP", uptrend_history)
    down_snap = compute_snapshot("DOWN", downtrend_history)

    assert up_snap.rsi14 > down_snap.rsi14
    assert up_snap.last_close > up_snap.sma200
    assert down_snap.last_close < down_snap.sma200
    assert up_snap.pct_change_3m > down_snap.pct_change_3m
