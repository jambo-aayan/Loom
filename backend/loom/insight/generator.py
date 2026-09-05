"""Insight generation (ADR-0009, ADR-0011). Structurally incapable of becoming an order —
advisory only (story 53). Two tiers: a cheap screening pass on every candidate (this ticket,
#30) and a deeper research pass reserved for M2. The LLM is one of the four external boundaries
faked in tests (Testing Decisions, issue #1)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from loom.models import Signal


class InsightGenerator(ABC):
    @abstractmethod
    def generate_screening(self, signal: Signal) -> str:
        raise NotImplementedError


class FakeInsightGenerator(InsightGenerator):
    """Deterministic canned commentary — the faked LLM boundary used in tests and as a
    zero-dependency default so the screening tier works without an Anthropic API key."""

    def generate_screening(self, signal: Signal) -> str:
        direction = "entering" if signal.action in ("buy", "add") else "exiting"
        return (
            f"{signal.strategy.name if signal.strategy else 'Strategy'} is {direction} "
            f"{signal.instrument} at confidence {signal.confidence:.2f}. Exit plan: "
            f"{signal.exit_plan}."
        )


class AnthropicInsightGenerator(InsightGenerator):
    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def generate_screening(self, signal: Signal) -> str:
        prompt = (
            f"In two sentences, explain why a '{signal.action}' signal on {signal.instrument} "
            f"fired for a systematic trading strategy, given confidence {signal.confidence:.2f} "
            f"and exit plan {signal.exit_plan}. Be factual and concise, no advice to act."
        )
        response = self._client.messages.create(
            model=self._model,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if hasattr(block, "text"))
