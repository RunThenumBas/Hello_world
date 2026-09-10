from trading_advisor.indicators import compute_snapshot
from trading_advisor.report import render_report
from trading_advisor.scoring import score_ticker
from trading_advisor.watchlist import Sector


def test_render_report_includes_sector_and_disclaimer(uptrend_history):
    sector = Sector(
        name="Test Sector",
        description="A sector for testing.",
        benchmark="BENCH",
        tickers=("UP",),
    )
    snap = compute_snapshot("UP", uptrend_history)
    suggestion = score_ticker(snap)

    report = render_report({sector: [suggestion]})

    assert "Test Sector" in report
    assert "UP" in report
    assert suggestion.label in report
    assert "not** licensed financial or" in report


def test_render_report_handles_empty_sector():
    sector = Sector(name="Empty", description="No data.", benchmark="BENCH", tickers=("X",))
    report = render_report({sector: []})
    assert "No data available" in report
