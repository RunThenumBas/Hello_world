"""Web-search-grounded long-term-hold research for stocks you've marked held.

Only runs for held tickers, and only when you click Refresh -- checking the
"held" box never by itself triggers an API call. Requires ANTHROPIC_API_KEY;
if it's not set, every call fails soft (a ResearchResult with `.error` set)
so a refresh never breaks just because research isn't configured.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

DEFAULT_MODEL = os.environ.get("TRADING_ADVISOR_RESEARCH_MODEL", "claude-opus-5")

SYSTEM_PROMPT = (
    "You write concise long-term-hold research notes for a personal, informational-only "
    "portfolio tool. You are not a licensed financial advisor and must not give direct buy/sell "
    "instructions or price targets. Given a ticker and its current technical snapshot, use web "
    "search to ground your note in recent, real information (news, filings, analyst commentary), "
    "then write a short note with these sections: Thesis (why someone might hold this long-term), "
    "Recent developments (what's actually happened lately, from your search), Key risks, and What "
    "would change the picture (concrete triggers to reassess). Keep it under 300 words total. "
    "Plain text, no markdown headers -- use short paragraph labels like 'Thesis:' instead."
)


@dataclass(frozen=True)
class ResearchResult:
    ticker: str
    text: str | None
    model: str
    generated_at: str
    error: str | None = None


def _client():
    import anthropic

    return anthropic.Anthropic()


def generate_long_term_note(ticker: str, snapshot_summary: str, *, client=None) -> ResearchResult:
    generated_at = datetime.now(timezone.utc).isoformat()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return ResearchResult(
            ticker=ticker,
            text=None,
            model=DEFAULT_MODEL,
            generated_at=generated_at,
            error="ANTHROPIC_API_KEY is not set -- long-term research skipped.",
        )

    import anthropic

    try:
        active_client = client or _client()
        response = active_client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            output_config={"effort": "medium"},
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 3}],
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Ticker: {ticker}\nCurrent technical snapshot: {snapshot_summary}\n\n"
                        "Research this as a long-term hold candidate."
                    ),
                }
            ],
        )
    except anthropic.AuthenticationError:
        return ResearchResult(ticker, None, DEFAULT_MODEL, generated_at, "Invalid Anthropic API key.")
    except anthropic.PermissionDeniedError:
        return ResearchResult(ticker, None, DEFAULT_MODEL, generated_at, "API key lacks permission for this model.")
    except anthropic.RateLimitError:
        return ResearchResult(ticker, None, DEFAULT_MODEL, generated_at, "Rate limited by the Anthropic API -- try again later.")
    except anthropic.APIConnectionError:
        return ResearchResult(ticker, None, DEFAULT_MODEL, generated_at, "Network error reaching the Anthropic API.")
    except anthropic.APIStatusError as exc:
        return ResearchResult(ticker, None, DEFAULT_MODEL, generated_at, f"API error: {exc.message}")

    if response.stop_reason == "refusal":
        return ResearchResult(ticker, None, DEFAULT_MODEL, generated_at, "Research request was declined.")

    text = "\n".join(block.text for block in response.content if block.type == "text").strip()
    if not text:
        return ResearchResult(ticker, None, DEFAULT_MODEL, generated_at, "No research text returned.")

    return ResearchResult(ticker, text, DEFAULT_MODEL, generated_at, None)
