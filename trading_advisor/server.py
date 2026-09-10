"""Local desktop server: serves the live dashboard and handles Refresh/Holdings.

Binds to 127.0.0.1 only -- never exposed beyond this machine. Started by the
desktop launcher (see launch/), or directly with `python -m trading_advisor.server`.
"""

from __future__ import annotations

import argparse
import logging
import os
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from flask import Flask, jsonify, request

from . import holdings as holdings_store
from .advisor import build_holdings_data, build_report_data
from .dashboard import render_dashboard_html
from .research import generate_long_term_note
from .watchlist import SECTORS

logger = logging.getLogger(__name__)


def _load_dotenv() -> None:
    """Load ANTHROPIC_API_KEY=... (and friends) from a repo-root .env, if present.

    Never overrides a variable already set in the real environment.
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


class DashboardState:
    def __init__(self, *, demo: bool, period: str):
        self.demo = demo
        self.period = period
        self.lock = Lock()
        self.sector_data: dict = {}
        self.holdings_data: dict[str, object] = {}
        self.generated_at: str | None = None

    def _snapshot_cache(self) -> dict:
        return {}

    def ensure_loaded(self) -> None:
        with self.lock:
            if self.generated_at is not None:
                return
            self._refresh_locked(run_research=False)

    def _refresh_locked(self, *, run_research: bool) -> None:
        cache = self._snapshot_cache()
        self.sector_data = build_report_data(SECTORS, period=self.period, demo=self.demo, cache=cache)

        held = holdings_store.held_tickers()
        self.holdings_data = build_holdings_data(held, period=self.period, demo=self.demo, cache=cache)
        self.generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        if run_research:
            for ticker in held:
                snap_suggestion = self.holdings_data.get(ticker)
                if snap_suggestion is None:
                    continue
                summary = (
                    f"{snap_suggestion.label} (score {snap_suggestion.score:+.0f}), "
                    f"RSI {snap_suggestion.rsi14:.0f}, 3-month change {snap_suggestion.pct_change_3m * 100:+.1f}%."
                )
                result = generate_long_term_note(ticker, summary)
                holdings_store.save_research(
                    ticker, result.text or "", result.model, result.generated_at, result.error
                )

    def refresh(self) -> None:
        with self.lock:
            self._refresh_locked(run_research=True)

    def ensure_ticker(self, ticker: str) -> None:
        """Fetch+score one newly-added ticker immediately, without a full refresh."""
        with self.lock:
            if ticker in self.holdings_data:
                return
            cache = self._snapshot_cache()
            fetched = build_holdings_data([ticker], period=self.period, demo=self.demo, cache=cache)
            self.holdings_data.update(fetched)

    def render(self) -> str:
        with self.lock:
            held_map = holdings_store.load_holdings()
            # self.holdings_data accumulates every ticker ever fetched this
            # session; only show ones still held per the on-disk source of truth
            # (otherwise an unchecked ticker keeps reappearing, still checked).
            visible_holdings = {
                ticker: suggestion
                for ticker, suggestion in self.holdings_data.items()
                if held_map.get(ticker, {}).get("held")
            }
            return render_dashboard_html(
                self.sector_data,
                demo=self.demo,
                interactive=True,
                holdings_suggestions=visible_holdings,
                held_map=held_map,
                generated_at=self.generated_at,
            )


def create_app(*, demo: bool = False, period: str = "1y") -> Flask:
    _load_dotenv()
    app = Flask(__name__)
    state = DashboardState(demo=demo, period=period)

    @app.get("/")
    def index():
        state.ensure_loaded()
        return state.render()

    @app.post("/api/refresh")
    def refresh():
        try:
            state.refresh()
        except Exception as exc:  # noqa: BLE001 -- surface any failure to the UI rather than 500 silently
            logger.exception("Refresh failed")
            return jsonify({"ok": False, "error": str(exc)}), 500
        return jsonify({"ok": True, "generated_at": state.generated_at})

    @app.get("/api/holdings")
    def get_holdings():
        return jsonify(holdings_store.load_holdings())

    @app.post("/api/holdings/toggle")
    def toggle_holding():
        body = request.get_json(silent=True) or {}
        ticker = str(body.get("ticker", "")).strip().upper()
        held = bool(body.get("held", False))
        if not ticker:
            return jsonify({"ok": False, "error": "ticker is required"}), 400
        holdings_store.set_held(ticker, held)
        if held:
            state.ensure_ticker(ticker)
        return jsonify({"ok": True, "holdings": holdings_store.load_holdings()})

    @app.post("/api/holdings/add")
    def add_holding():
        body = request.get_json(silent=True) or {}
        ticker = str(body.get("ticker", "")).strip().upper()
        if not ticker or not ticker.replace(".", "").replace("-", "").isalnum():
            return jsonify({"ok": False, "error": "Enter a valid ticker symbol"}), 400
        holdings_store.set_held(ticker, True)
        state.ensure_ticker(ticker)
        return jsonify({"ok": True, "holdings": holdings_store.load_holdings()})

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Thematic Trade Signals desktop server.")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--period", default="1y")
    parser.add_argument("--demo", action="store_true", help="Use synthetic offline data instead of live market data.")
    parser.add_argument("--no-browser", action="store_true", help="Don't auto-open a browser tab.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    app = create_app(demo=args.demo, period=args.period)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Serving Thematic Trade Signals at {url}")
    if not args.no_browser:
        import threading

        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    app.run(host="127.0.0.1", port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
