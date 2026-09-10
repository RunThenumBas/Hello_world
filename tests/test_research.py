from trading_advisor.research import generate_long_term_note


def test_missing_api_key_fails_soft(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = generate_long_term_note("AAPL", "BUY (score +40), RSI 60, 3-month change +8.0%.")

    assert result.ticker == "AAPL"
    assert result.text is None
    assert result.error is not None
    assert "ANTHROPIC_API_KEY" in result.error


def test_successful_call_returns_text(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")

    class FakeTextBlock:
        type = "text"

        def __init__(self, text):
            self.text = text

    class FakeResponse:
        stop_reason = "end_turn"
        content = [FakeTextBlock("Thesis: looks fine.\nRisks: none noted.")]

    class FakeMessages:
        def create(self, **kwargs):
            assert kwargs["model"] == "claude-opus-5"
            assert any(t["type"] == "web_search_20260209" for t in kwargs["tools"])
            return FakeResponse()

    class FakeClient:
        messages = FakeMessages()

    result = generate_long_term_note("AAPL", "BUY (score +40).", client=FakeClient())

    assert result.error is None
    assert "Thesis" in result.text


def test_refusal_stop_reason_reported_as_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")

    class FakeResponse:
        stop_reason = "refusal"
        content = []

    class FakeMessages:
        def create(self, **kwargs):
            return FakeResponse()

    class FakeClient:
        messages = FakeMessages()

    result = generate_long_term_note("AAPL", "BUY (score +40).", client=FakeClient())

    assert result.text is None
    assert result.error is not None
