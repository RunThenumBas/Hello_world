"""Ties data fetching, indicators, and scoring together per sector."""

from __future__ import annotations

import logging

from .data import DataUnavailableError, fetch_price_history
from .demo_data import generate_demo_history
from .indicators import compute_snapshot
from .scoring import Suggestion, score_ticker
from .watchlist import SECTORS, Sector

logger = logging.getLogger(__name__)

# Generic benchmark for tickers outside the curated sector watchlists
# (custom holdings) -- broad market, better than no comparison at all.
DEFAULT_HOLDINGS_BENCHMARK = "SPY"


def _fetch_snapshot(ticker: str, *, demo: bool, period: str, cache: dict[str, object]):
    if ticker in cache:
        return cache[ticker]
    try:
        history = generate_demo_history(ticker) if demo else fetch_price_history(ticker, period=period)
        snap = compute_snapshot(ticker, history)
    except DataUnavailableError as exc:
        logger.warning("Skipping %s: %s", ticker, exc)
        snap = None
    cache[ticker] = snap
    return snap


def build_report_data(
    sectors: tuple[Sector, ...] = SECTORS,
    period: str = "1y",
    demo: bool = False,
    cache: dict[str, object] | None = None,
) -> dict[Sector, list[Suggestion]]:
    if cache is None:
        cache = {}

    results: dict[Sector, list[Suggestion]] = {}
    for sector in sectors:
        benchmark_snap = _fetch_snapshot(sector.benchmark, demo=demo, period=period, cache=cache)
        suggestions: list[Suggestion] = []
        for ticker in sector.tickers:
            snap = _fetch_snapshot(ticker, demo=demo, period=period, cache=cache)
            if snap is None:
                continue
            suggestions.append(score_ticker(snap, benchmark_snap))
        results[sector] = suggestions

    return results


def build_holdings_data(
    tickers: list[str],
    period: str = "1y",
    demo: bool = False,
    cache: dict[str, object] | None = None,
) -> dict[str, Suggestion]:
    """Score arbitrary tickers (e.g. custom holdings) against a generic benchmark."""
    if cache is None:
        cache = {}

    benchmark_snap = _fetch_snapshot(DEFAULT_HOLDINGS_BENCHMARK, demo=demo, period=period, cache=cache)
    results: dict[str, Suggestion] = {}
    for ticker in tickers:
        snap = _fetch_snapshot(ticker, demo=demo, period=period, cache=cache)
        if snap is None:
            continue
        results[ticker] = score_ticker(snap, benchmark_snap)

    return results
