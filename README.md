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
6. `trading_advisor/dashboard.py` -- renders the same data as an interactive
   HTML dashboard (filter by sector/signal, search, sort, expand a row for
   the full rationale). `--html` writes it as a plain static file; the
   desktop server (below) serves a live version with Hold checkboxes, a
   Refresh button, and AI research for held stocks.
7. `trading_advisor/server.py` + `trading_advisor/holdings.py` +
   `trading_advisor/research.py` -- the desktop app. A local Flask server
   (127.0.0.1 only) that serves the live dashboard, persists which stocks
   you've marked "held," and on Refresh re-scores everything and runs
   AI-assisted long-term-hold research (via Claude + live web search) for
   held stocks specifically.

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

### Desktop app: live dashboard with Holdings + AI research

This runs a small local server instead of a one-off static file, so the page
in your browser has a **Refresh** button and **Hold** checkboxes that actually
do something.

**Setup (macOS):**

```bash
pip install -r requirements.txt
```

Then double-click `launch/Trading Advisor.command`. First run creates a
virtual environment and installs dependencies (~1 minute); after that it
starts instantly. It opens your browser to `http://127.0.0.1:8787/` and keeps
running as long as that Terminal window is open -- close it (or Ctrl+C) to
stop the server. To make it a real desktop icon: drag `Trading Advisor.command`
onto your Desktop (or right-click -> Make Alias and drag the alias there); to
give it a custom icon, select an image, Cmd+C it, then Get Info on the
`.command` file, click its icon in the top-left of the Info panel, and Cmd+V.

Not on macOS? Run the server directly instead of using the launcher:

```bash
python -m trading_advisor.server            # opens your browser automatically
python -m trading_advisor.server --demo     # offline/synthetic data
python -m trading_advisor.server --port 9000 --no-browser
```

**What Refresh does:** re-fetches live prices and recomputes every signal
(free, no API key needed) -- and for any ticker you've checked as **held**,
also asks Claude to research it as a long-term hold (see below). The server
only ever binds to `127.0.0.1` -- it's not reachable from your network.

**Holdings ("so they don't disappear"):** check a ticker's box anywhere in
the dashboard (or type a ticker into the **+ Add** box in **My Holdings**,
for anything outside the curated sector lists) and it's saved to
`~/.trading_advisor/holdings.json` -- pinned in the always-visible **My
Holdings** section at the top, immune to the sector/signal filters, and
persisted across restarts. Uncheck it to remove it.

**AI long-term-hold research (held stocks only, on Refresh):** requires an
Anthropic API key. Either export it:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

or create a `.env` file in the repo root (already gitignored):

```
ANTHROPIC_API_KEY=sk-ant-...
```

Without a key, Refresh still works -- held stocks just show "ANTHROPIC_API_KEY
is not set" instead of a research note, and every technical signal keeps
updating normally. With a key, each held ticker gets a short note (thesis,
recent developments grounded in live web search, key risks, what would change
the picture) using Claude Opus 5 -- a few cents per held ticker per refresh,
only for stocks you've explicitly checked, never for the whole watchlist.
This is informational research, not investment advice, and no trades are
ever placed.

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
