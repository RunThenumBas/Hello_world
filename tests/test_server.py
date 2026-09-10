import json

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADING_ADVISOR_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from trading_advisor.server import create_app

    app = create_app(demo=True, period="6mo")
    app.config.update(TESTING=True)
    return app.test_client()


def test_index_loads_and_renders_dashboard(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Thematic Trade Signals" in body
    assert "refresh-btn" in body
    assert "My Holdings" in body


def test_toggle_holding_persists_and_shows_up(client):
    resp = client.post(
        "/api/holdings/toggle",
        data=json.dumps({"ticker": "aapl", "held": True}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.get_json()["holdings"]["AAPL"]["held"] is True

    body = client.get("/").get_data(as_text=True)
    assert 'data-ticker="AAPL"' in body
    assert "held-row" in body


def test_toggle_off_removes_from_holdings(client):
    client.post(
        "/api/holdings/toggle",
        data=json.dumps({"ticker": "AAPL", "held": True}),
        content_type="application/json",
    )
    resp = client.post(
        "/api/holdings/toggle",
        data=json.dumps({"ticker": "AAPL", "held": False}),
        content_type="application/json",
    )
    assert resp.get_json()["holdings"] == {}


def test_add_holding_rejects_garbage_ticker(client):
    resp = client.post(
        "/api/holdings/add",
        data=json.dumps({"ticker": "not a ticker!!"}),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_add_holding_accepts_valid_ticker(client):
    resp = client.post(
        "/api/holdings/add",
        data=json.dumps({"ticker": "nvda"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert "NVDA" in resp.get_json()["holdings"]


def test_unchecked_ticker_disappears_from_holdings_view(client):
    # Regression test: the server used to keep showing a ticker (still
    # checked) in My Holdings after it was unchecked, because the in-memory
    # cache wasn't filtered against the on-disk held state at render time.
    # AAPL is also in the curated "Advanced Technology" watchlist, so it can
    # legitimately appear once (unchecked, in its sector table) even when not
    # held -- the bug was a *second* copy in My Holdings, still checked.
    client.post(
        "/api/holdings/toggle",
        data=json.dumps({"ticker": "AAPL", "held": True}),
        content_type="application/json",
    )
    # Each row contributes data-ticker twice (the <tr> and its checkbox <input>),
    # so 2 rows (sector table + My Holdings) == 4 occurrences.
    body_while_held = client.get("/").get_data(as_text=True)
    assert body_while_held.count('data-ticker="AAPL"') == 4

    client.post(
        "/api/holdings/toggle",
        data=json.dumps({"ticker": "AAPL", "held": False}),
        content_type="application/json",
    )
    body_after_uncheck = client.get("/").get_data(as_text=True)
    assert body_after_uncheck.count('data-ticker="AAPL"') == 2  # sector row only


def test_refresh_succeeds_without_api_key(client):
    # Held ticker exists but no ANTHROPIC_API_KEY is set -- refresh must not
    # crash, and the missing-key state should be recorded, not silently dropped.
    client.post(
        "/api/holdings/toggle",
        data=json.dumps({"ticker": "AAPL", "held": True}),
        content_type="application/json",
    )
    resp = client.post("/api/refresh")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    body = client.get("/").get_data(as_text=True)
    assert "ANTHROPIC_API_KEY" in body


def test_server_binds_localhost_only():
    # This is a security property, not just a default -- app.run() would block
    # if called directly, so assert on the source instead of executing main().
    import inspect

    from trading_advisor import server

    source = inspect.getsource(server.main)
    assert 'host="127.0.0.1"' in source
    assert "0.0.0.0" not in source
