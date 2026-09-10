"""Render sector suggestions as an interactive, filterable HTML dashboard.

Everything needed to filter/sort/expand is server-rendered into the markup
as data-* attributes; the inline script only ever manipulates DOM the page
already contains -- no client-side templating, no network calls at view time.
"""

from __future__ import annotations

import math
import re
from html import escape

from .report import DISCLAIMER
from .scoring import SUGGESTIONS, Suggestion
from .watchlist import Sector

_TITLE = "Thematic Trade Signals"

# label -> (css slot, icon, display text)
_LABEL_META: dict[str, tuple[str, str, str]] = {
    "STRONG BUY": ("strong-buy", "▲▲", "Strong Buy"),
    "BUY": ("buy", "▲", "Buy"),
    "HOLD": ("hold", "–", "Hold"),
    "SELL": ("sell", "▼", "Sell"),
    "STRONG SELL": ("strong-sell", "▼▼", "Strong Sell"),
}

_CSS = """
:root {
  color-scheme: light;
  --page-bg: #f9f9f7;
  --surface: #fcfcfb;
  --surface-alt: #f3f2ee;
  --ink-primary: #0b0b0b;
  --ink-secondary: #52514e;
  --ink-muted: #898781;
  --border: #e1e0d9;
  --accent: #2a78d6;
  --accent-bg: rgba(42, 120, 214, 0.14);

  --buy-text: #086b1c;         --buy-bg: rgba(8, 107, 28, 0.16);
  --strong-buy-text: #085e18;  --strong-buy-bg: rgba(8, 94, 24, 0.16);
  --sell-text: #a12a2a;        --sell-bg: rgba(161, 42, 42, 0.14);
  --strong-sell-text: #8f1f1f; --strong-sell-bg: rgba(143, 31, 31, 0.14);
  --hold-text: #52514e;        --hold-bg: rgba(82, 81, 78, 0.10);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --page-bg: #0d0d0d;
    --surface: #1a1a19;
    --surface-alt: #202020;
    --ink-primary: #ffffff;
    --ink-secondary: #c3c2b7;
    --ink-muted: #898781;
    --border: #2c2c2a;
    --accent: #3987e5;
    --accent-bg: rgba(57, 135, 229, 0.20);

    --buy-text: #3ecf5e;         --buy-bg: rgba(62, 207, 94, 0.20);
    --strong-buy-text: #6be085;  --strong-buy-bg: rgba(107, 224, 133, 0.20);
    --sell-text: #ef9090;        --sell-bg: rgba(239, 144, 144, 0.20);
    --strong-sell-text: #ffb0b0; --strong-sell-bg: rgba(255, 176, 176, 0.16);
    --hold-text: #c3c2b7;        --hold-bg: rgba(195, 194, 183, 0.12);
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page-bg: #0d0d0d;
  --surface: #1a1a19;
  --surface-alt: #202020;
  --ink-primary: #ffffff;
  --ink-secondary: #c3c2b7;
  --ink-muted: #898781;
  --border: #2c2c2a;
  --accent: #3987e5;
  --accent-bg: rgba(57, 135, 229, 0.20);

  --buy-text: #3ecf5e;         --buy-bg: rgba(62, 207, 94, 0.20);
  --strong-buy-text: #6be085;  --strong-buy-bg: rgba(107, 224, 133, 0.20);
  --sell-text: #ef9090;        --sell-bg: rgba(239, 144, 144, 0.20);
  --strong-sell-text: #ffb0b0; --strong-sell-bg: rgba(255, 176, 176, 0.16);
  --hold-text: #c3c2b7;        --hold-bg: rgba(195, 194, 183, 0.12);
}

* { box-sizing: border-box; }

body {
  background: var(--page-bg);
  color: var(--ink-primary);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  line-height: 1.5;
}

.app {
  max-width: 1080px;
  margin: 0 auto;
  padding-inline: 20px;
  padding-block: 28px 48px;
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.header-top { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.app-header h1 { font-size: 1.6rem; margin: 0 0 4px; text-wrap: balance; }
.app-header .meta { color: var(--ink-secondary); font-size: 0.9rem; margin: 0; }
.refresh-control { display: flex; align-items: center; gap: 10px; }
.refresh-btn {
  font: inherit;
  font-size: 0.85rem;
  font-weight: 600;
  padding: 7px 14px;
  border-radius: 999px;
  border: 1px solid var(--accent);
  background: var(--accent-bg);
  color: var(--accent);
  cursor: pointer;
}
.refresh-btn:disabled { opacity: 0.6; cursor: default; }
.refresh-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.refresh-status { font-size: 0.8rem; color: var(--sell-text); }
.demo-flag {
  display: inline-block;
  margin-left: 8px;
  padding: 2px 9px;
  border-radius: 999px;
  background: var(--accent-bg);
  color: var(--accent);
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  vertical-align: middle;
}

.disclaimer {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  background: var(--surface-alt);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 16px;
  color: var(--ink-secondary);
  font-size: 0.88rem;
}
.disclaimer-icon { color: var(--accent); font-weight: 700; }
.disclaimer strong { color: var(--ink-primary); }

.controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 16px;
  position: sticky;
  top: 0;
  background: var(--page-bg);
  padding-block: 8px;
  z-index: 5;
}
.control-group { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  font: inherit;
  font-size: 0.82rem;
  padding: 6px 12px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--ink-secondary);
  cursor: pointer;
}
.chip.is-active { border-color: var(--accent); color: var(--accent); font-weight: 600; }
.chip:focus-visible, .expand-btn:focus-visible, .sort-btn:focus-visible, #ticker-search:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
#ticker-search {
  font: inherit;
  font-size: 0.85rem;
  padding: 6px 12px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--ink-primary);
  min-width: 160px;
  margin-left: auto;
}

.kpi-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(100px, 1fr)); gap: 10px; }
.kpi-tile {
  background: var(--surface);
  border: 1px solid var(--border);
  border-top: 3px solid var(--ink-muted);
  border-radius: 10px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.kpi-tile.strong-buy { border-top-color: var(--strong-buy-text); }
.kpi-tile.buy { border-top-color: var(--buy-text); }
.kpi-tile.hold { border-top-color: var(--ink-muted); }
.kpi-tile.sell { border-top-color: var(--sell-text); }
.kpi-tile.strong-sell { border-top-color: var(--strong-sell-text); }
.kpi-value { font-size: 1.5rem; font-weight: 600; }
.kpi-label { font-size: 0.78rem; color: var(--ink-secondary); }

.sector-section { display: flex; flex-direction: column; gap: 10px; }
.sector-heading h2 { font-size: 1.15rem; margin: 0; }
.sector-heading p { margin: 2px 0 0; color: var(--ink-secondary); font-size: 0.86rem; }
.benchmark { color: var(--ink-muted); }

.table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }
table { border-collapse: collapse; width: 100%; min-width: 560px; }
thead th {
  text-align: left;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--ink-muted);
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.sort-btn {
  font: inherit;
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
  padding: 0;
  text-transform: inherit;
  letter-spacing: inherit;
}
.sort-btn::after { content: ""; margin-left: 4px; font-size: 0.6rem; }
th.sort-asc .sort-btn::after { content: "▲"; }
th.sort-desc .sort-btn::after { content: "▼"; }

tbody td { padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 0.88rem; vertical-align: middle; }
tbody tr.row:last-of-type td, tbody tr.held-row:last-of-type td, tbody tr.detail-row:last-of-type td { border-bottom: none; }
.cell-ticker { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-weight: 600; }
.num { font-variant-numeric: tabular-nums; text-align: right; }
.num-pos { color: var(--buy-text); }
.num-neg { color: var(--sell-text); }

.visually-hidden {
  position: absolute;
  width: 1px; height: 1px;
  padding: 0; margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
.cell-hold { width: 1%; }
.hold-checkbox { display: inline-flex; cursor: pointer; }
.hold-toggle { width: 16px; height: 16px; cursor: pointer; accent-color: var(--accent); }
.hold-toggle:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 600;
  white-space: nowrap;
}
.badge.strong-buy { background: var(--strong-buy-bg); color: var(--strong-buy-text); }
.badge.buy { background: var(--buy-bg); color: var(--buy-text); }
.badge.hold { background: var(--hold-bg); color: var(--hold-text); }
.badge.sell { background: var(--sell-bg); color: var(--sell-text); }
.badge.strong-sell { background: var(--strong-sell-bg); color: var(--strong-sell-text); }

.cell-score { min-width: 150px; }
.score-cell { display: flex; align-items: center; gap: 8px; }
.score-bar { position: relative; display: inline-block; width: 76px; height: 6px; flex: none; }
.score-track { position: absolute; inset: 0; background: var(--border); border-radius: 3px; }
.score-zero { position: absolute; top: -2px; bottom: -2px; left: 50%; width: 1px; background: var(--ink-muted); }
.score-fill { position: absolute; top: 0; bottom: 0; border-radius: 3px; }
.score-fill.pos { background: var(--buy-text); }
.score-fill.neg { background: var(--sell-text); }
.score-value { font-variant-numeric: tabular-nums; font-size: 0.85rem; color: var(--ink-secondary); }

.expand-btn {
  font: inherit;
  font-size: 0.78rem;
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--accent);
  cursor: pointer;
}

.detail-row td { background: var(--surface-alt); padding: 12px 16px; }
.detail-panel { display: flex; flex-direction: column; gap: 8px; }
.rationale, .risk-notes { margin: 0; padding-left: 18px; font-size: 0.85rem; color: var(--ink-secondary); }
.rationale li, .risk-notes li { margin-bottom: 3px; }
.risk-notes .risk { color: var(--sell-text); }

.no-match-msg, .empty-row td { padding: 16px; text-align: center; color: var(--ink-muted); font-size: 0.85rem; }

.pinned-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
  border: 1px solid var(--accent);
  border-radius: 12px;
  padding: 14px 14px 4px;
  background: var(--accent-bg);
}
.pinned-section .table-wrap { background: var(--surface); }
.add-holding-form { display: flex; gap: 8px; flex-wrap: wrap; }
.add-holding-form input {
  font: inherit;
  font-size: 0.85rem;
  padding: 6px 12px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--ink-primary);
}
.add-holding-form button {
  font: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  padding: 6px 14px;
  border-radius: 999px;
  border: 1px solid var(--accent);
  background: var(--surface);
  color: var(--accent);
  cursor: pointer;
}

.research-block {
  margin-top: 6px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--surface);
  border: 1px solid var(--border);
  font-size: 0.85rem;
  color: var(--ink-secondary);
}
.research-heading { font-weight: 600; color: var(--ink-primary); margin: 0 0 6px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.research-tag {
  font-size: 0.68rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--accent);
  background: var(--accent-bg);
  padding: 2px 7px;
  border-radius: 999px;
}
.research-block p { margin: 0 0 6px; }
.research-block p:last-child { margin-bottom: 0; }
.research-error { color: var(--sell-text); }
.research-meta { font-size: 0.75rem; color: var(--ink-muted); margin-top: 4px; }

footer {
  border-top: 1px solid var(--border);
  padding-top: 16px;
  color: var(--ink-muted);
  font-size: 0.8rem;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
footer code { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; background: var(--surface-alt); padding: 1px 5px; border-radius: 4px; }

@media (max-width: 640px) {
  #ticker-search { margin-left: 0; width: 100%; }
  .controls { position: static; }
}
"""

_SCRIPT = """
(function () {
  const sectorChips = Array.from(document.querySelectorAll('.sector-chip'));
  const labelChips = Array.from(document.querySelectorAll('.label-chip'));
  const searchInput = document.getElementById('ticker-search');
  const rows = Array.from(document.querySelectorAll('.row'));
  const kpiTiles = new Map(
    Array.from(document.querySelectorAll('.kpi-tile')).map((t) => [t.dataset.kpi, t.querySelector('.kpi-value')])
  );

  let activeSector = 'all';
  const activeLabels = new Set(labelChips.map((c) => c.dataset.label));

  function detailRowFor(row) {
    const next = row.nextElementSibling;
    return next && next.classList.contains('detail-row') ? next : null;
  }

  function applyFilters() {
    const query = searchInput.value.trim().toLowerCase();
    const counts = {};
    activeLabels.forEach((l) => (counts[l] = 0));
    const sectionVisibleCounts = new Map();

    rows.forEach((row) => {
      const matchesSector = activeSector === 'all' || row.dataset.sector === activeSector;
      const matchesLabel = activeLabels.has(row.dataset.label);
      const matchesSearch =
        !query || row.dataset.ticker.toLowerCase().includes(query) || row.dataset.sector.toLowerCase().includes(query);
      const visible = matchesSector && matchesLabel && matchesSearch;

      row.hidden = !visible;
      const detail = detailRowFor(row);
      if (detail && !visible) {
        detail.hidden = true;
        const btn = row.querySelector('.expand-btn');
        if (btn) btn.setAttribute('aria-expanded', 'false');
      }

      if (visible) counts[row.dataset.label] = (counts[row.dataset.label] || 0) + 1;

      const section = row.closest('.sector-section');
      const key = section.dataset.sectorSection;
      sectionVisibleCounts.set(key, (sectionVisibleCounts.get(key) || 0) + (visible ? 1 : 0));
    });

    kpiTiles.forEach((el, label) => {
      el.textContent = String(counts[label] || 0);
    });

    document.querySelectorAll('.sector-section').forEach((section) => {
      const key = section.dataset.sectorSection;
      const visibleCount = sectionVisibleCounts.get(key) || 0;
      const hasAnyRows = section.querySelectorAll('.row').length > 0;
      const msg = section.querySelector('.no-match-msg');
      const table = section.querySelector('table');
      if (msg) msg.hidden = !(hasAnyRows && visibleCount === 0);
      if (table) table.hidden = hasAnyRows && visibleCount === 0;
      section.hidden = activeSector !== 'all' && activeSector !== key;
    });
  }

  sectorChips.forEach((chip) => {
    chip.addEventListener('click', () => {
      activeSector = chip.dataset.sector;
      sectorChips.forEach((c) => c.classList.toggle('is-active', c === chip));
      applyFilters();
    });
  });

  labelChips.forEach((chip) => {
    chip.addEventListener('click', () => {
      const label = chip.dataset.label;
      if (activeLabels.has(label)) activeLabels.delete(label);
      else activeLabels.add(label);
      chip.classList.toggle('is-active');
      applyFilters();
    });
  });

  searchInput.addEventListener('input', applyFilters);

  document.querySelectorAll('.expand-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const row = btn.closest('tr');
      const detail = detailRowFor(row);
      if (!detail) return;
      const expanded = btn.getAttribute('aria-expanded') === 'true';
      detail.hidden = expanded;
      btn.setAttribute('aria-expanded', String(!expanded));
    });
  });

  document.querySelectorAll('.sort-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const th = btn.closest('th');
      const table = th.closest('table');
      const tbody = table.querySelector('tbody');
      const key = btn.dataset.sort;
      const ascending = th.dataset.dir !== 'asc';

      table.querySelectorAll('th').forEach((other) => {
        other.dataset.dir = '';
        other.classList.remove('sort-asc', 'sort-desc');
      });
      th.dataset.dir = ascending ? 'asc' : 'desc';
      th.classList.add(ascending ? 'sort-asc' : 'sort-desc');

      const pairs = Array.from(tbody.querySelectorAll('.row')).map((row) => [row, detailRowFor(row)]);
      pairs.sort((a, b) => {
        const rowA = a[0];
        const rowB = b[0];
        let va;
        let vb;
        if (key === 'ticker') {
          va = rowA.dataset.ticker;
          vb = rowB.dataset.ticker;
        } else {
          va = parseFloat(rowA.dataset[key]);
          vb = parseFloat(rowB.dataset[key]);
        }
        if (va < vb) return ascending ? -1 : 1;
        if (va > vb) return ascending ? 1 : -1;
        return 0;
      });
      pairs.forEach(([row, detail]) => {
        tbody.appendChild(row);
        if (detail) tbody.appendChild(detail);
      });
    });
  });

  const holdToggles = Array.from(document.querySelectorAll('.hold-toggle'));
  holdToggles.forEach((cb) => {
    cb.addEventListener('change', () => {
      const nextHeld = cb.checked;
      cb.disabled = true;
      fetch('/api/holdings/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: cb.dataset.ticker, held: nextHeld }),
      })
        .then((r) => {
          if (!r.ok) throw new Error('Request failed');
          return r.json();
        })
        .then(() => {
          window.location.reload();
        })
        .catch(() => {
          cb.disabled = false;
          cb.checked = !nextHeld;
          window.alert('Could not save that change. Please try again.');
        });
    });
  });

  const addForm = document.getElementById('add-holding-form');
  if (addForm) {
    addForm.addEventListener('submit', (event) => {
      event.preventDefault();
      const input = document.getElementById('add-holding-input');
      const ticker = input.value.trim().toUpperCase();
      if (!ticker) return;
      fetch('/api/holdings/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker }),
      })
        .then((r) => {
          if (!r.ok) throw new Error('Request failed');
          return r.json();
        })
        .then(() => {
          window.location.reload();
        })
        .catch(() => {
          window.alert('Could not add that ticker. Please try again.');
        });
    });
  }

  const refreshBtn = document.getElementById('refresh-btn');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', () => {
      const status = document.getElementById('refresh-status');
      refreshBtn.disabled = true;
      refreshBtn.textContent = 'Refreshing…';
      if (status) {
        status.hidden = true;
        status.textContent = '';
      }
      fetch('/api/refresh', { method: 'POST' })
        .then((r) => r.json().then((body) => ({ ok: r.ok, body })))
        .then(({ ok, body }) => {
          if (!ok) throw new Error((body && body.error) || 'Refresh failed');
          window.location.reload();
        })
        .catch((err) => {
          refreshBtn.disabled = false;
          refreshBtn.textContent = '⟳ Refresh';
          if (status) {
            status.hidden = false;
            status.textContent = err.message;
          }
        });
    });
  }

  applyFilters();
})();
"""


def _slugify(text: str) -> str:
    """Collapse arbitrary text to a safe HTML id: only [A-Za-z0-9_-] survive."""
    return re.sub(r"[^A-Za-z0-9_-]+", "-", text).strip("-")


def _badge_html(label: str) -> str:
    css_slot, icon, text = _LABEL_META[label]
    return f'<span class="badge {css_slot}"><span aria-hidden="true">{icon}</span>{escape(text)}</span>'


def _score_bar_html(score: float) -> str:
    clamped = max(min(score, 100.0), -100.0)
    magnitude = abs(clamped) / 2
    side = "pos" if clamped >= 0 else "neg"
    side_style = f"left:50%;width:{magnitude:.1f}%" if clamped >= 0 else f"right:50%;width:{magnitude:.1f}%"
    return (
        '<div class="score-cell">'
        f'<div class="score-bar" role="img" aria-label="Score {clamped:+.0f} out of 100">'
        '<span class="score-track"></span>'
        f'<span class="score-fill {side}" style="{side_style}"></span>'
        '<span class="score-zero"></span>'
        "</div>"
        f'<span class="score-value">{clamped:+.0f}</span>'
        "</div>"
    )


def _count_labels(sector_suggestions: dict[Sector, list[Suggestion]]) -> dict[str, int]:
    counts = {label: 0 for label in SUGGESTIONS}
    for suggestions in sector_suggestions.values():
        for s in suggestions:
            counts[s.label] = counts.get(s.label, 0) + 1
    return counts


def _kpi_row_html(counts: dict[str, int]) -> str:
    tiles = []
    for label in SUGGESTIONS:
        css_slot, _icon, text = _LABEL_META[label]
        tiles.append(
            f'<div class="kpi-tile {css_slot}" data-kpi="{escape(label)}">'
            f'<span class="kpi-value">{counts.get(label, 0)}</span>'
            f'<span class="kpi-label">{escape(text)}</span>'
            "</div>"
        )
    return f'<div class="kpi-row">{"".join(tiles)}</div>'


def _research_block_html(research: dict | None) -> str:
    if not research:
        return ""
    error = research.get("error")
    text = research.get("text")
    generated_at = research.get("generated_at", "")
    model = research.get("model", "")

    if not text:
        message = error or "Research not available yet."
        return (
            '<div class="research-block">'
            '<p class="research-heading">Long-term hold research</p>'
            f'<p class="research-error">{escape(message)}</p>'
            "</div>"
        )

    paragraphs = "".join(f"<p>{escape(p)}</p>" for p in text.split("\n") if p.strip())
    return (
        '<div class="research-block">'
        '<p class="research-heading">Long-term hold research'
        '<span class="research-tag">AI-generated, informational only</span></p>'
        f"{paragraphs}"
        f'<p class="research-meta">Researched {escape(generated_at)} &middot; {escape(model)}</p>'
        "</div>"
    )


def _table_header_html(interactive: bool, sortable: bool = True) -> str:
    checkbox_th = '<th><span class="visually-hidden">Hold</span></th>' if interactive else ""

    def col(label: str, key: str) -> str:
        if sortable:
            return f'<th><button class="sort-btn" type="button" data-sort="{key}">{label}</button></th>'
        return f"<th>{label}</th>"

    return f"""
          <thead>
            <tr>
              {checkbox_th}
              {col("Ticker", "ticker")}
              <th>Signal</th>
              {col("Score", "score")}
              {col("3M", "pct3m")}
              {col("RSI", "rsi")}
              <th></th>
            </tr>
          </thead>
    """


def _row_html(
    sector_name: str,
    s: Suggestion,
    *,
    interactive: bool = False,
    held: bool = False,
    row_class: str = "row",
    research: dict | None = None,
) -> str:
    ticker = escape(s.ticker)
    sector_attr = escape(sector_name)
    label_attr = escape(s.label)
    pct = s.pct_change_3m * 100
    pct_class = "num-pos" if pct >= 0 else "num-neg"
    rsi_display = f"{s.rsi14:.0f}" if not math.isnan(s.rsi14) else "—"
    rsi_sort = s.rsi14 if not math.isnan(s.rsi14) else -1
    detail_id = _slugify(f"detail-{sector_name}-{s.ticker}")
    rationale_items = "".join(f"<li>{escape(note)}</li>" for note in s.rationale)
    risk_items = "".join(f'<li class="risk">⚠ {escape(note)}</li>' for note in s.risk_notes)
    risk_block = f'<ul class="risk-notes">{risk_items}</ul>' if risk_items else ""
    research_block = _research_block_html(research) if interactive else ""

    checkbox_cell = ""
    colspan = 6
    if interactive:
        checked = "checked" if held else ""
        checkbox_cell = (
            '<td class="cell-hold">'
            f'<label class="hold-checkbox"><input type="checkbox" class="hold-toggle" '
            f'data-ticker="{ticker}" {checked}>'
            f'<span class="visually-hidden">Hold {ticker}</span></label>'
            "</td>"
        )
        colspan = 7

    return (
        f'<tr class="{row_class}" data-sector="{sector_attr}" data-label="{label_attr}" data-ticker="{ticker}" '
        f'data-score="{s.score:.1f}" data-pct3m="{s.pct_change_3m:.4f}" data-rsi="{rsi_sort:.1f}">'
        f"{checkbox_cell}"
        f'<td class="cell-ticker">{ticker}</td>'
        f"<td>{_badge_html(s.label)}</td>"
        f'<td class="cell-score">{_score_bar_html(s.score)}</td>'
        f'<td class="num {pct_class}">{pct:+.1f}%</td>'
        f'<td class="num">{rsi_display}</td>'
        f'<td><button class="expand-btn" type="button" aria-expanded="false" aria-controls="{detail_id}">Details</button></td>'
        "</tr>"
        f'<tr class="detail-row" id="{detail_id}" hidden>'
        f'<td colspan="{colspan}"><div class="detail-panel">'
        f'<ul class="rationale">{rationale_items}</ul>{risk_block}{research_block}'
        "</div></td></tr>"
    )


def _sector_section_html(
    sector: Sector,
    suggestions: list[Suggestion],
    *,
    interactive: bool = False,
    held_map: dict | None = None,
) -> str:
    held_map = held_map or {}
    ranked = sorted(suggestions, key=lambda s: s.score, reverse=True)
    colspan = 7 if interactive else 6
    if ranked:
        rows = "".join(
            _row_html(
                sector.name,
                s,
                interactive=interactive,
                held=held_map.get(s.ticker, {}).get("held", False),
                research=held_map.get(s.ticker, {}).get("research"),
            )
            for s in ranked
        )
    else:
        rows = f'<tr class="empty-row"><td colspan="{colspan}">No data available for this sector right now.</td></tr>'

    return f"""
    <section class="sector-section" data-sector-section="{escape(sector.name)}">
      <div class="sector-heading">
        <h2>{escape(sector.name)}</h2>
        <p>{escape(sector.description)} &middot; <span class="benchmark">Benchmark: {escape(sector.benchmark)}</span></p>
      </div>
      <div class="table-wrap">
        <table>
          {_table_header_html(interactive)}
          <tbody>
            {rows}
          </tbody>
        </table>
        <p class="no-match-msg" hidden>No tickers match the current filters.</p>
      </div>
    </section>
    """


def _holdings_section_html(holdings_suggestions: dict[str, Suggestion], held_map: dict) -> str:
    tickers = sorted(holdings_suggestions.keys())
    if tickers:
        rows = "".join(
            _row_html(
                "My Holdings",
                holdings_suggestions[ticker],
                interactive=True,
                held=True,
                row_class="held-row",
                research=held_map.get(ticker, {}).get("research"),
            )
            for ticker in tickers
        )
    else:
        rows = (
            '<tr class="empty-row"><td colspan="7">'
            "No holdings saved yet -- check a box below, or add a ticker here."
            "</td></tr>"
        )

    return f"""
    <section class="pinned-section" data-pinned-section="holdings">
      <div class="sector-heading">
        <h2>My Holdings</h2>
        <p>Pinned regardless of filters. Checked tickers get long-term-hold research when you click Refresh.</p>
      </div>
      <form class="add-holding-form" id="add-holding-form">
        <input type="text" id="add-holding-input" placeholder="Add ticker (e.g. AAPL)" aria-label="Add ticker to holdings" autocomplete="off">
        <button type="submit">+ Add</button>
      </form>
      <div class="table-wrap">
        <table>
          {_table_header_html(interactive=True, sortable=False)}
          <tbody>
            {rows}
          </tbody>
        </table>
      </div>
    </section>
    """


def _refresh_control_html(interactive: bool) -> str:
    if not interactive:
        return ""
    return (
        '<div class="refresh-control">'
        '<button id="refresh-btn" type="button" class="refresh-btn">⟳ Refresh</button>'
        '<span id="refresh-status" class="refresh-status" role="alert" hidden></span>'
        "</div>"
    )


def _sector_chips_html(sectors: list[Sector]) -> str:
    chips = ['<button class="chip sector-chip is-active" type="button" data-sector="all">All sectors</button>']
    for sector in sectors:
        chips.append(
            f'<button class="chip sector-chip" type="button" data-sector="{escape(sector.name)}">{escape(sector.name)}</button>'
        )
    return f'<div class="control-group" role="group" aria-label="Filter by sector">{"".join(chips)}</div>'


def _label_chips_html() -> str:
    chips = []
    for label in SUGGESTIONS:
        _css_slot, _icon, text = _LABEL_META[label]
        chips.append(
            f'<button class="chip label-chip is-active" type="button" data-label="{escape(label)}">{escape(text)}</button>'
        )
    return f'<div class="control-group" role="group" aria-label="Filter by signal">{"".join(chips)}</div>'


def _disclaimer_html() -> str:
    text = escape(DISCLAIMER).replace("**not**", "<strong>not</strong>")
    return f'<div class="disclaimer" role="note"><span class="disclaimer-icon" aria-hidden="true">ⓘ</span><p>{text}</p></div>'


def _render_content(
    sector_suggestions: dict[Sector, list[Suggestion]],
    *,
    demo: bool,
    generated_at: str,
    interactive: bool = False,
    holdings_suggestions: dict[str, Suggestion] | None = None,
    held_map: dict | None = None,
) -> str:
    holdings_suggestions = holdings_suggestions or {}
    held_map = held_map or {}
    sectors = list(sector_suggestions.keys())
    counts = _count_labels(sector_suggestions)
    demo_flag = '<span class="demo-flag">Demo data</span>' if demo else ""
    sections = "".join(
        _sector_section_html(sector, suggestions, interactive=interactive, held_map=held_map)
        for sector, suggestions in sector_suggestions.items()
    )
    holdings_section = _holdings_section_html(holdings_suggestions, held_map) if interactive else ""

    return f"""
<div class="app">
  <header class="app-header">
    <div class="header-top">
      <h1>{escape(_TITLE)}</h1>
      {_refresh_control_html(interactive)}
    </div>
    <p class="meta">Generated {escape(generated_at)}{demo_flag}</p>
  </header>

  {_disclaimer_html()}

  <div class="controls">
    {_sector_chips_html(sectors)}
    {_label_chips_html()}
    <input type="search" id="ticker-search" placeholder="Search ticker…" aria-label="Search ticker or sector">
  </div>

  {_kpi_row_html(counts)}

  <main>
    {holdings_section}
    {sections}
  </main>

  <footer>
    <p>Advisory only -- no trades are placed. Regenerate with <code>python -m trading_advisor --html report.html</code>.</p>
    <p>{escape(generated_at)}</p>
  </footer>
</div>
<script>{_SCRIPT}</script>
"""


def render_dashboard_html(
    sector_suggestions: dict[Sector, list[Suggestion]],
    *,
    demo: bool = False,
    embeddable: bool = False,
    generated_at: str | None = None,
    interactive: bool = False,
    holdings_suggestions: dict[str, Suggestion] | None = None,
    held_map: dict | None = None,
) -> str:
    """Render the full dashboard.

    `embeddable=True` omits the <!doctype>/<html>/<head>/<body> wrapper and
    instead returns a flat title+style+content document -- the shape needed
    to publish this as a Claude Artifact, which supplies that wrapper itself.

    `interactive=True` adds the "Hold" checkboxes, the pinned My Holdings
    section, the add-ticker form, and the Refresh button -- all of which
    talk to a running `trading_advisor.server` backend. Leave it False (the
    default, used by the CLI's `--html` flag) for a read-only static file
    with no backend to call.
    """
    if generated_at is None:
        from datetime import datetime, timezone

        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    content = _render_content(
        sector_suggestions,
        demo=demo,
        generated_at=generated_at,
        interactive=interactive,
        holdings_suggestions=holdings_suggestions,
        held_map=held_map,
    )

    if embeddable:
        return f"<title>{escape(_TITLE)}</title>\n<style>\n{_CSS}\n</style>\n{content}"

    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(_TITLE)}</title>\n"
        f"<style>\n{_CSS}\n</style>\n"
        "</head>\n"
        f"<body>\n{content}\n</body>\n</html>\n"
    )
