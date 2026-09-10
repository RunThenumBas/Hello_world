# Hello_world

The beginning of another long story

Hello all RunThenumBas here,

Currently invested in the trade welding and its great and all but I feel as though there are bigger and better opertunities out there then for me. I am very intriuded by the exploration of space, futher development in technoligy and upper limits to the human brain and what we can acheive as a collective. Learning to code I feel will give me a foot in the door towards pursuing one of those inerests if not all of them!

## Thematic Market Advisory Tool

A small Python tool that researches global markets and generates plain-English
BUY / SELL / HOLD **suggestions**, grouped by theme:

- Quantum computing
- Advanced technology (AI infrastructure, semiconductors)
- Clean energy & environment
- Emerging / frontier sectors (space, robotics, biotech, and other
  humanity-reshaping fields)

**It never places trades.** It only pulls price data, computes trend/momentum
indicators, and prints a report for you to read and act on manually.

> This is not licensed financial or investment advice. It's a heuristic,
> rules-based screening tool for your own research. Markets in these themes
> can be highly volatile -- do your own due diligence.

### How it works

1. `trading_advisor/watchlist.py` -- curated tickers per sector plus a
   benchmark ETF for relative-strength comparisons. Edit freely to track
   different companies.
2. `trading_advisor/data.py` -- fetches OHLCV price history via
   [yfinance](https://github.com/ranaroussi/yfinance) (covers US and many
   international/ADR-listed tickers). Swap this module to plug in a different
   data provider (Alpha Vantage, Polygon, a broker API, etc.) without touching
   the rest of the pipeline.
3. `trading_advisor/indicators.py` -- SMA50/200, RSI, MACD, volatility, and
   drawdown-from-52-week-high, computed directly on pandas Series.
4. `trading_advisor/scoring.py` -- combines trend, momentum, and relative
   strength vs. the sector benchmark into a -100..+100 score and a
   STRONG SELL / SELL / HOLD / BUY / STRONG BUY label with a rationale.
5. `trading_advisor/report.py` -- renders everything as a Markdown report,
   sorted by score within each sector.
6. `trading_advisor/dashboard.py` -- renders the same data as a self-contained,
   interactive HTML dashboard (filter by sector/signal, search, sort, expand
   a row for the full rationale). No server, no build step -- just open the
   file in a browser.

### Usage

```bash
pip install -r requirements.txt

# Full report across all sectors
python -m trading_advisor

# Just one sector, and save to a file
python -m trading_advisor --sector quantum --out reports/quantum.md

# Shorter/longer lookback window (anything yfinance accepts: 3mo, 6mo, 1y, 2y, ...)
python -m trading_advisor --period 6mo

# Visual dashboard -- writes an HTML file, then open it in your browser
python -m trading_advisor --html reports/dashboard.html

# Try it without a live network connection (synthetic data, clearly labeled "Demo data")
python -m trading_advisor --demo --html reports/dashboard.html
```

The dashboard (`--html`) opens with a KPI row (counts by signal), a filter bar
(sector, signal, ticker search), and a sortable table per sector. Click
**Details** on any row to expand its full rationale and risk notes.

### Extending it

- **More tickers/sectors**: edit `SECTORS` in `trading_advisor/watchlist.py`.
- **More signals** (e.g. news sentiment, earnings surprises, options flow):
  add a module alongside `indicators.py` and fold its output into
  `scoring.score_ticker`.
- **Automation**: schedule `python -m trading_advisor --html reports/dashboard.html`
  (e.g. via cron or a Claude Code Routine) to get a fresh dashboard on a
  cadence. It only ever writes local files -- wiring it to an actual
  broker/execution API is a deliberate next step you'd add yourself, not
  something this tool does.

### Tests

```bash
python -m pytest tests/
```

Tests run entirely against synthetic price data, so they don't require
network access or live market data.
