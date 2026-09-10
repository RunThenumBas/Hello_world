"""Persisted "held" tickers -- the desktop app's durable state.

Stored outside the repo (the user's home directory) since this is personal
portfolio data, not something that belongs in version control. A ticker
becomes "held" by checking its box in the dashboard; it stays held across
restarts until unchecked.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _state_dir() -> Path:
    override = os.environ.get("TRADING_ADVISOR_STATE_DIR")
    if override:
        return Path(override)
    return Path.home() / ".trading_advisor"


def _holdings_path() -> Path:
    return _state_dir() / "holdings.json"


def load_holdings() -> dict[str, dict[str, Any]]:
    path = _holdings_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_holdings(data: dict[str, dict[str, Any]]) -> None:
    path = _holdings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def set_held(ticker: str, held: bool) -> dict[str, dict[str, Any]]:
    ticker = ticker.strip().upper()
    data = load_holdings()
    if held:
        entry = data.get(ticker, {})
        entry.setdefault("added_at", datetime.now(timezone.utc).isoformat())
        entry["held"] = True
        data[ticker] = entry
    else:
        data.pop(ticker, None)
    save_holdings(data)
    return data


def held_tickers() -> list[str]:
    return sorted(t for t, entry in load_holdings().items() if entry.get("held"))


def save_research(ticker: str, text: str, model: str, generated_at: str, error: str | None) -> None:
    ticker = ticker.strip().upper()
    data = load_holdings()
    if ticker not in data:
        return
    data[ticker]["research"] = {
        "text": text,
        "model": model,
        "generated_at": generated_at,
        "error": error,
    }
    save_holdings(data)
