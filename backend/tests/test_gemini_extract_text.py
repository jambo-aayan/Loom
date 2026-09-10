"""GeminiInsightGenerator itself is a real external boundary (faked in the rest of the test
suite, per generator.py's module docstring), but _extract_text is pure logic worth covering
directly: response.text (the SDK's quick accessor) raises ValueError on a multi-part response —
confirmed live, this broke every search-grounded call (Ask, research) while non-search calls kept
working, since a search-grounded response routinely comes back with citation/executable-code
parts alongside the text part."""

from types import SimpleNamespace

from loom.insight.generator import _extract_text


def _response(parts):
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=parts))])


def test_extracts_text_from_a_single_part_response():
    response = _response([SimpleNamespace(text="hello")])

    assert _extract_text(response) == "hello"


def test_joins_text_across_multiple_parts_skipping_non_text_ones():
    """The exact shape that broke response.text: a search-grounded answer alongside a
    citation/executable-code part that carries no text of its own."""
    response = _response([SimpleNamespace(text="answer part one. "), SimpleNamespace(text=None), SimpleNamespace(text="answer part two.")])

    assert _extract_text(response) == "answer part one. answer part two."


def test_returns_empty_string_when_no_candidates_came_back():
    """Blocked by safety filtering, or cut off before producing anything — a real possibility for
    any external LLM call, not a crash."""
    response = SimpleNamespace(candidates=[])

    assert _extract_text(response) == ""


def test_returns_empty_string_when_a_candidate_has_no_parts():
    response = _response([])

    assert _extract_text(response) == ""
