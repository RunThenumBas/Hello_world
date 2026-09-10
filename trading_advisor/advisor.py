"""Ties data fetching, indicators, and scoring together per sector."""

from __future__ import annotations

import logging

from .data import DataUnavailableError, fetch_price_history
from .demo_data import generate_demo_history
from .indicators import compute_snapshot
from .scoring import Suggestion, score_ticker
from .watchlist import SECTORS, Sector

logger = logging.getLogger(__name__)


def build_report_data(
    sectors: tuple[Sector, ...] = SECTORS,
    period: str = "1y",
    demo: bool = False,
) -> dict[Sector, list[Suggestion]]:
    snapshot_cache: dict[str, object] = {}

    def _snapshot(ticker: str):
        if ticker in snapshot_cache:
            return snapshot_cache[ticker]
        try:
            history = generate_demo_history(ticker) if demo else fetch_price_history(ticker, period=period)
            snap = compute_snapshot(ticker, history)
        except DataUnavailableError as exc:
            logger.warning("Skipping %s: %s", ticker, exc)
            snap = None
        snapshot_cache[ticker] = snap
        return snap

    results: dict[Sector, list[Suggestion]] = {}
    for sector in sectors:
        benchmark_snap = _snapshot(sector.benchmark)
        suggestions: list[Suggestion] = []
        for ticker in sector.tickers:
            snap = _snapshot(ticker)
            if snap is None:
                continue
            suggestions.append(score_ticker(snap, benchmark_snap))
        results[sector] = suggestions

    return results
