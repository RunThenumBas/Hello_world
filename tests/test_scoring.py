from trading_advisor.indicators import compute_snapshot
from trading_advisor.scoring import score_ticker


def test_uptrend_scores_as_buy_or_better(uptrend_history):
    snap = compute_snapshot("UP", uptrend_history)
    suggestion = score_ticker(snap)
    assert suggestion.label in {"BUY", "STRONG BUY"}
    assert suggestion.score > 0
    assert suggestion.rationale


def test_downtrend_scores_as_sell_or_worse(downtrend_history):
    snap = compute_snapshot("DOWN", downtrend_history)
    suggestion = score_ticker(snap)
    assert suggestion.label in {"SELL", "STRONG SELL"}
    assert suggestion.score < 0


def test_relative_strength_shifts_score_vs_benchmark(uptrend_history, flat_history):
    strong_snap = compute_snapshot("STRONG", uptrend_history)
    benchmark_snap = compute_snapshot("BENCH", flat_history)

    without_benchmark = score_ticker(strong_snap)
    with_benchmark = score_ticker(strong_snap, benchmark_snap)

    assert with_benchmark.score >= without_benchmark.score - 1e-9
    assert any("benchmark" in note for note in with_benchmark.rationale)
