from loom.api.deps import get_insight_generator, get_screening_generator
from loom.insight.generator import AnthropicInsightGenerator, FakeInsightGenerator, GeminiInsightGenerator


def _settings(**overrides):
    base = {"anthropic_api_key": "", "google_api_key": ""}
    base.update(overrides)
    return type("S", (), base)()


def test_falls_back_to_fake_generator_with_no_credentials(monkeypatch):
    monkeypatch.setattr("loom.api.deps.get_settings", lambda: _settings())

    assert isinstance(get_insight_generator(), FakeInsightGenerator)


def test_prefers_anthropic_when_both_are_configured(monkeypatch):
    monkeypatch.setattr(
        "loom.api.deps.get_settings",
        lambda: _settings(anthropic_api_key="claude-key", google_api_key="gemini-key"),
    )

    assert isinstance(get_insight_generator(), AnthropicInsightGenerator)


def test_falls_back_to_gemini_when_only_google_is_configured(monkeypatch):
    """ADR-0016: amends ADR-0013's original Anthropic-only design for the screening/ask path —
    confirmed live that only a Google key was ever actually provisioned in practice, leaving Ask
    silently stuck on the fake generator with no real Anthropic key to fall back from."""
    monkeypatch.setattr(
        "loom.api.deps.get_settings", lambda: _settings(google_api_key="gemini-key")
    )

    assert isinstance(get_insight_generator(), GeminiInsightGenerator)


def test_screening_and_ask_use_different_gemini_models(monkeypatch):
    """Confirmed live: Google's free-tier RPD limits are tracked per model, not pooled across
    models within a project. Screening fires on essentially every signal (by far the
    highest-volume Gemini caller) — pointing it at a different model than position
    commentary/"ask" gives each its own daily quota bucket instead of the two competing for one
    shared, easily-exhausted allowance (confirmed live: this is exactly what caused a 429
    RESOURCE_EXHAUSTED on Ask after Screening had already been running for a while)."""
    monkeypatch.setattr(
        "loom.api.deps.get_settings", lambda: _settings(google_api_key="gemini-key")
    )

    screening = get_screening_generator()
    ask = get_insight_generator()

    assert isinstance(screening, GeminiInsightGenerator) and isinstance(ask, GeminiInsightGenerator)
    assert screening._model != ask._model


def test_screening_generator_falls_back_to_fake_with_no_credentials(monkeypatch):
    monkeypatch.setattr("loom.api.deps.get_settings", lambda: _settings())

    assert isinstance(get_screening_generator(), FakeInsightGenerator)
