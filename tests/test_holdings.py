import pytest


@pytest.fixture
def holdings(tmp_path, monkeypatch):
    # _state_dir() reads this env var fresh on every call, so no reload needed.
    monkeypatch.setenv("TRADING_ADVISOR_STATE_DIR", str(tmp_path / "state"))
    from trading_advisor import holdings as holdings_module

    return holdings_module


def test_load_holdings_empty_when_no_file(holdings):
    assert holdings.load_holdings() == {}


def test_set_held_true_then_false_roundtrips(holdings):
    holdings.set_held("aapl", True)
    data = holdings.load_holdings()
    assert data["AAPL"]["held"] is True
    assert "added_at" in data["AAPL"]

    holdings.set_held("AAPL", False)
    assert holdings.load_holdings() == {}


def test_held_tickers_only_returns_currently_held(holdings):
    holdings.set_held("AAPL", True)
    holdings.set_held("TSLA", True)
    holdings.set_held("TSLA", False)

    assert holdings.held_tickers() == ["AAPL"]


def test_save_research_attaches_to_existing_holding(holdings):
    holdings.set_held("AAPL", True)
    holdings.save_research("aapl", "some note", "claude-opus-5", "2026-01-01T00:00:00", None)

    data = holdings.load_holdings()
    assert data["AAPL"]["research"]["text"] == "some note"
    assert data["AAPL"]["research"]["model"] == "claude-opus-5"


def test_save_research_ignored_for_unheld_ticker(holdings):
    holdings.save_research("GOOGL", "note", "claude-opus-5", "2026-01-01T00:00:00", None)
    assert holdings.load_holdings() == {}


def test_persists_to_disk(holdings, tmp_path):
    holdings.set_held("MSFT", True)
    path = tmp_path / "state" / "holdings.json"
    assert path.exists()
    assert "MSFT" in path.read_text(encoding="utf-8")
