"""Insight generation (ADR-0009, ADR-0011). Structurally incapable of becoming an order —
advisory only (story 53). A cheap screening pass runs on every signal candidate (#30); a deeper
research pass is a near-term fast-follow, not built in v1 (BACKLOG.md); position commentary
(#44) generates advisory text about any held position — including `Manual` and other strategies'
Books — with no Signal involved at all (story 37). The LLM is one of the four external boundaries
faked in tests (Testing Decisions, issue #1)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from loom.models import Signal


class InsightGenerator(ABC):
    @abstractmethod
    def generate_screening(self, signal: Signal) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_position_commentary(
        self, instrument: str, book_name: str, quantity: float, average_price: float
    ) -> str:
        """Advisory commentary about a held position, not tied to any Signal (story 37) — works
        for a `Manual` holding or another strategy's Book just as well as the bot's own."""
        raise NotImplementedError

    @abstractmethod
    def answer_question(self, question: str, instrument: str | None = None) -> str:
        """On-demand "ask about this stock / this macro topic" research (story 51) — free-form,
        not tied to any Signal or position. Never returns anything actionable (story 53)."""
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

    def generate_position_commentary(
        self, instrument: str, book_name: str, quantity: float, average_price: float
    ) -> str:
        return (
            f"{book_name} holds {quantity:g} {instrument} at an average price of "
            f"{average_price:.2f}. No strategy signal is currently attached to this position."
        )

    def answer_question(self, question: str, instrument: str | None = None) -> str:
        scope = f" about {instrument}" if instrument else ""
        return f"(fake research{scope}) You asked: {question!r}. No web search performed."


class AnthropicInsightGenerator(InsightGenerator):
    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def _complete(self, prompt: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if hasattr(block, "text"))

    def generate_screening(self, signal: Signal) -> str:
        prompt = (
            f"In two sentences, explain why a '{signal.action}' signal on {signal.instrument} "
            f"fired for a systematic trading strategy, given confidence {signal.confidence:.2f} "
            f"and exit plan {signal.exit_plan}. Be factual and concise, no advice to act."
        )
        return self._complete(prompt)

    def generate_position_commentary(
        self, instrument: str, book_name: str, quantity: float, average_price: float
    ) -> str:
        prompt = (
            f"In two sentences, give factual, advisory-only commentary about a held position: "
            f"{quantity:g} shares of {instrument} at an average price of {average_price:.2f}, "
            f"in the '{book_name}' book. No advice to act, no price target."
        )
        return self._complete(prompt)

    def answer_question(self, question: str, instrument: str | None = None) -> str:
        scope = f" The question concerns {instrument}." if instrument else ""
        prompt = (
            f"Research this question using web search where useful, then answer factually and "
            f"concisely (a short paragraph).{scope} Advisory only — never recommend a specific "
            f"trade or action. Question: {question}"
        )
        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if hasattr(block, "text"))
