"""Turn indicator snapshots into a plain-English trade suggestion.

This is a rules-based heuristic, not a predictive model: it combines trend
(price vs. moving averages, golden/death cross), momentum (RSI, MACD), and
relative strength vs. a sector benchmark into a single -100..+100 score, then
maps the score to a suggestion label. Treat it as a starting point for your
own research, not a signal to act on blindly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .indicators import IndicatorSnapshot

SUGGESTIONS = ("STRONG SELL", "SELL", "HOLD", "BUY", "STRONG BUY")


@dataclass(frozen=True)
class Suggestion:
    ticker: str
    score: float
    label: str
    rationale: list[str]
    risk_notes: list[str]
    rsi14: float
    pct_change_3m: float


def _trend_score(snap: IndicatorSnapshot) -> tuple[float, list[str]]:
    notes: list[str] = []
    score = 0.0

    if not math.isnan(snap.sma200):
        if snap.last_close > snap.sma200:
            score += 25
            notes.append("Trading above the 200-day moving average (long-term uptrend).")
        else:
            score -= 25
            notes.append("Trading below the 200-day moving average (long-term downtrend).")

    if not math.isnan(snap.sma50) and not math.isnan(snap.sma200):
        if snap.sma50 > snap.sma200:
            score += 15
            notes.append("50-day average above the 200-day average (golden-cross posture).")
        else:
            score -= 15
            notes.append("50-day average below the 200-day average (death-cross posture).")

    return score, notes


def _momentum_score(snap: IndicatorSnapshot) -> tuple[float, list[str]]:
    notes: list[str] = []
    score = 0.0

    if snap.rsi14 >= 70:
        score -= 10
        notes.append(f"RSI at {snap.rsi14:.0f} suggests overbought conditions.")
    elif snap.rsi14 <= 30:
        score += 10
        notes.append(f"RSI at {snap.rsi14:.0f} suggests oversold conditions.")
    else:
        contribution = (snap.rsi14 - 50) / 2
        score += contribution
        notes.append(f"RSI at {snap.rsi14:.0f} (neutral zone).")

    if not math.isnan(snap.macd_line) and not math.isnan(snap.macd_signal):
        if snap.macd_line > snap.macd_signal:
            score += 15
            notes.append("MACD line above signal line (bullish momentum).")
        else:
            score -= 15
            notes.append("MACD line below signal line (bearish momentum).")

    if snap.pct_change_3m > 0:
        score += min(snap.pct_change_3m * 50, 20)
        notes.append(f"Up {snap.pct_change_3m * 100:.1f}% over the last ~3 months.")
    else:
        score += max(snap.pct_change_3m * 50, -20)
        notes.append(f"Down {abs(snap.pct_change_3m) * 100:.1f}% over the last ~3 months.")

    return score, notes


def _risk_notes(snap: IndicatorSnapshot) -> list[str]:
    notes: list[str] = []
    if not math.isnan(snap.volatility):
        notes.append(f"Annualized volatility ~{snap.volatility * 100:.0f}%.")
    if snap.drawdown_from_52w_high > 0.01:
        notes.append(f"Currently {snap.drawdown_from_52w_high * 100:.1f}% below its 52-week high.")
    if not math.isnan(snap.volatility) and snap.volatility > 0.6:
        notes.append("High volatility -- consider smaller position size / wider stop.")
    return notes


def _label_for_score(score: float) -> str:
    if score >= 40:
        return "STRONG BUY"
    if score >= 15:
        return "BUY"
    if score <= -40:
        return "STRONG SELL"
    if score <= -15:
        return "SELL"
    return "HOLD"


def score_ticker(snap: IndicatorSnapshot, benchmark_snap: IndicatorSnapshot | None = None) -> Suggestion:
    trend_pts, trend_notes = _trend_score(snap)
    momentum_pts, momentum_notes = _momentum_score(snap)
    total = trend_pts + momentum_pts
    rationale = trend_notes + momentum_notes

    if benchmark_snap is not None:
        relative = snap.pct_change_3m - benchmark_snap.pct_change_3m
        rel_pts = max(min(relative * 40, 15), -15)
        total += rel_pts
        if relative > 0:
            rationale.append(
                f"Outperforming its benchmark by {relative * 100:.1f} pts over ~3 months."
            )
        else:
            rationale.append(
                f"Underperforming its benchmark by {abs(relative) * 100:.1f} pts over ~3 months."
            )

    total = max(min(total, 100.0), -100.0)
    return Suggestion(
        ticker=snap.ticker,
        score=total,
        label=_label_for_score(total),
        rationale=rationale,
        risk_notes=_risk_notes(snap),
        rsi14=snap.rsi14,
        pct_change_3m=snap.pct_change_3m,
    )
