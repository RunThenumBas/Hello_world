"""Command-line entry point: python -m trading_advisor [options]"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .advisor import build_report_data
from .report import render_report
from .watchlist import SECTORS, find_sector


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate thematic BUY/SELL/HOLD trade suggestions (advisory only, no execution)."
    )
    parser.add_argument(
        "--sector",
        action="append",
        dest="sectors",
        help="Limit to one sector (repeatable). Matches by name substring, e.g. 'quantum'.",
    )
    parser.add_argument(
        "--period",
        default="1y",
        help="History window passed to the data provider, e.g. 6mo, 1y, 2y (default: 1y).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Write the Markdown report to this file in addition to stdout.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress info logging.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.ERROR if args.quiet else logging.INFO, format="%(message)s")

    sectors = SECTORS
    if args.sectors:
        resolved = []
        for name in args.sectors:
            sector = find_sector(name)
            if sector is None:
                print(f"Unknown sector: {name!r}", file=sys.stderr)
                return 2
            resolved.append(sector)
        sectors = tuple(resolved)

    data = build_report_data(sectors=sectors, period=args.period)
    report = render_report(data)

    print(report)
    if args.out:
        args.out.write_text(report, encoding="utf-8")
        print(f"\nSaved report to {args.out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
