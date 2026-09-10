"""Curated ticker groups for the themes the user wants coverage on.

Each sector maps to a small set of liquid, well-known tickers (mostly US-listed,
including ADRs of non-US companies so the list still reflects global markets)
plus a benchmark ETF used as a relative-strength reference. Edit these lists
freely -- they are just a starting watchlist, not a recommendation in themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Sector:
    name: str
    description: str
    benchmark: str
    tickers: tuple[str, ...] = field(default_factory=tuple)


SECTORS: tuple[Sector, ...] = (
    Sector(
        name="Quantum Computing",
        description="Companies building quantum hardware, software, and cloud access.",
        benchmark="QTUM",
        tickers=("IONQ", "RGTI", "QBTS", "IBM", "GOOGL", "MSFT", "HON"),
    ),
    Sector(
        name="Advanced Technology",
        description="Semiconductors, AI infrastructure, and platform technology leaders.",
        benchmark="QQQ",
        tickers=("NVDA", "AMD", "TSM", "ASML", "AVGO", "MSFT", "GOOGL", "AAPL"),
    ),
    Sector(
        name="Clean Energy & Environment",
        description="Solar, wind, grid storage, EVs, and climate-focused infrastructure.",
        benchmark="ICLN",
        tickers=("ENPH", "FSLR", "TSLA", "NEE", "PLUG", "BE", "RUN"),
    ),
    Sector(
        name="Emerging & Frontier Sectors",
        description="Space, robotics, biotech, and other early-stage transformative sectors.",
        benchmark="ARKK",
        tickers=("RKLB", "PLTR", "ISRG", "CRSP", "IRDM", "AXON"),
    ),
)


def all_tickers() -> list[str]:
    seen: dict[str, None] = {}
    for sector in SECTORS:
        for ticker in (*sector.tickers, sector.benchmark):
            seen[ticker] = None
    return list(seen)


def find_sector(name: str) -> Sector | None:
    lowered = name.strip().lower()
    for sector in SECTORS:
        if sector.name.lower() == lowered or lowered in sector.name.lower():
            return sector
    return None
