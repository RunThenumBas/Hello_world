from trading_advisor.dashboard import render_dashboard_html
from trading_advisor.indicators import compute_snapshot
from trading_advisor.scoring import score_ticker
from trading_advisor.watchlist import Sector


def _sample_data(uptrend_history, downtrend_history):
    sector = Sector(
        name="Test & Sector",
        description="A sector for testing.",
        benchmark="BENCH",
        tickers=("UP", "DOWN"),
    )
    up_snap = compute_snapshot("UP", uptrend_history)
    down_snap = compute_snapshot("DOWN", downtrend_history)
    return {sector: [score_ticker(up_snap), score_ticker(down_snap)]}, sector


def test_standalone_dashboard_is_a_full_document(uptrend_history, downtrend_history):
    data, sector = _sample_data(uptrend_history, downtrend_history)
    html = render_dashboard_html(data)

    assert html.startswith("<!doctype html>")
    assert "<html" in html and "</html>" in html
    assert "<head>" in html and "<body>" in html
    assert "UP" in html and "DOWN" in html
    assert "Test &amp; Sector" in html


def test_embeddable_dashboard_has_no_document_wrapper(uptrend_history, downtrend_history):
    data, _sector = _sample_data(uptrend_history, downtrend_history)
    html = render_dashboard_html(data, embeddable=True)

    assert not html.lstrip().startswith("<!doctype")
    assert "<html" not in html
    assert "<head>" not in html
    assert "<body>" not in html
    assert html.lstrip().startswith("<title>")


def test_demo_flag_shown_only_when_requested(uptrend_history, downtrend_history):
    data, _sector = _sample_data(uptrend_history, downtrend_history)

    live_html = render_dashboard_html(data, demo=False)
    demo_html = render_dashboard_html(data, demo=True)

    assert '<span class="demo-flag">' not in live_html
    assert '<span class="demo-flag">' in demo_html


def test_dashboard_escapes_untrusted_looking_text(uptrend_history):
    sector = Sector(name="XSS</style><script>", description="d", benchmark="B", tickers=("UP",))
    snap = compute_snapshot("UP", uptrend_history)
    suggestion = score_ticker(snap)
    # rationale/risk_notes are our own generated strings, but prove injection-shaped
    # content still comes out escaped rather than parsed as markup.
    object.__setattr__(suggestion, "rationale", suggestion.rationale + ["<img src=x onerror=alert(1)>"])

    html = render_dashboard_html({sector: [suggestion]})

    # Exactly one <script> tag: the dashboard's own interactive script --
    # none injected from the (escaped) rationale/sector text.
    assert html.count("<script>") == 1
    assert "<img src=x" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "XSS</style><script>" not in html


def test_score_bar_direction_matches_sign(uptrend_history, downtrend_history):
    data, _sector = _sample_data(uptrend_history, downtrend_history)
    html = render_dashboard_html(data)

    assert 'class="score-fill pos"' in html
    assert 'class="score-fill neg"' in html


def test_empty_sector_renders_placeholder_row():
    sector = Sector(name="Empty", description="No data.", benchmark="BENCH", tickers=("X",))
    html = render_dashboard_html({sector: []})
    assert "No data available for this sector" in html
