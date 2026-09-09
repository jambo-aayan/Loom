"""Insight generation (ADR-0009, ADR-0011, ADR-0013). Structurally incapable of becoming an
order — advisory only (story 53). A cheap screening pass runs on every signal candidate (#30);
a deeper research pass (#48) is style-gated to `investment`-style strategies only, with two
providers behind it — a free automatic pass (Gemini) and a manual-only, paid pass (Claude
Sonnet) — see `loom.insight.research` for the eligibility gate and job/endpoint wiring, this
module only knows how to generate text. Position commentary (#44) generates advisory text about
any held position — including `Manual` and other strategies' Books — with no Signal involved at
all (story 37). The LLM is one of the four external boundaries faked in tests (Testing
Decisions, issue #1)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from loom.models import Signal


def _research_prompt(signal: Signal) -> str:
    strategy_name = signal.strategy.name if signal.strategy else "Strategy"
    return (
        f"Write a short investment thesis for a '{signal.action}' signal on {signal.instrument} "
        f"from {strategy_name}, given confidence {signal.confidence:.2f} and exit plan "
        f"{signal.exit_plan}. Use web search for company-level context (recent news, why the "
        f"price may be where it is, whether this looks like a genuine opportunity or a value "
        f"trap). Structure the answer as a short thesis paragraph, then a line starting 'Key "
        f"risks:'. Factual and advisory only — never recommend a specific trade or action."
    )


class InsightGenerator(ABC):
    @abstractmethod
    def generate_screening(self, signal: Signal) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_research(self, signal: Signal) -> str:
        """The deeper research pass (#48) — multi-source synthesis, a short thesis plus key
        risks. Callers gate eligibility (investment-style strategies only) before calling this;
        the generator itself has no opinion on which signals it's appropriate for."""
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

    def generate_research(self, signal: Signal) -> str:
        strategy_name = signal.strategy.name if signal.strategy else "Strategy"
        return (
            f"Thesis: {strategy_name}'s '{signal.action}' signal on {signal.instrument} reflects "
            f"a long-hold, conviction-based read at confidence {signal.confidence:.2f} — no real "
            f"web search performed (fake generator). Key risks: none identified (fake generator)."
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

    def generate_research(self, signal: Signal) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": _research_prompt(signal)}],
        )
        return "".join(block.text for block in response.content if hasattr(block, "text"))

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


class GeminiInsightGenerator(InsightGenerator):
    """The free-tier provider behind the automatic research pass (ADR-0013) — Gemini Flash's
    free tier is cheap enough to run unattended on every eligible signal. Implements the full
    `InsightGenerator` interface like any other provider, even though `loom.api.deps` only ever
    wires this one in for the research tier today."""

    # Deliberately not the newest Flash release: Google tightens free-tier daily quotas hard on
    # brand-new models (as of Sep 2026, the newest one's free tier was reported at ~20
    # requests/day vs. ~1,500/day on established models like this one) — headroom for an
    # unattended job that runs indefinitely matters more here than frontier capability this task
    # doesn't need. Re-check current quotas before bumping this rather than assuming newest=best.
    #
    # "gemini-3-flash" (no minor version) was never a real model ID — confirmed live: every call
    # through it failed, and the resulting unhandled exception surfaced client-side as an opaque
    # "Failed to fetch" (see main.py's exception handler) rather than a clear model-not-found
    # error. gemini-3.5-flash is the real, currently-established model this comment describes.
    def __init__(self, api_key: str, model: str = "gemini-3.5-flash"):
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model

    def _complete(self, prompt: str, use_search: bool = False) -> str:
        from google.genai import types

        config = (
            types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
            if use_search
            else None
        )
        response = self._client.models.generate_content(model=self._model, contents=prompt, config=config)
        return response.text or ""

    def generate_screening(self, signal: Signal) -> str:
        prompt = (
            f"In two sentences, explain why a '{signal.action}' signal on {signal.instrument} "
            f"fired for a systematic trading strategy, given confidence {signal.confidence:.2f} "
            f"and exit plan {signal.exit_plan}. Be factual and concise, no advice to act."
        )
        return self._complete(prompt)

    def generate_research(self, signal: Signal) -> str:
        return self._complete(_research_prompt(signal), use_search=True)

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
        return self._complete(prompt, use_search=True)
