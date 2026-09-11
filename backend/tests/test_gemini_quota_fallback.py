"""Confirmed live: Ask/research pair a higher-quality-but-lower-quota model
(gemini-3.5-flash, 20 requests/day) with a fallback to the high-quota Lite model
(gemini-3.5-flash-lite, 500/day) so a genuinely exhausted daily quota degrades to a lower-quality
answer instead of a hard failure for a user waiting on one."""

from types import SimpleNamespace

import pytest
from google.genai.errors import ClientError

from loom.insight.generator import GeminiInsightGenerator, _is_quota_exhausted


def _quota_exhausted_error() -> ClientError:
    return ClientError(429, {"error": {"status": "RESOURCE_EXHAUSTED", "message": "quota"}})


def _response(text: str) -> SimpleNamespace:
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[SimpleNamespace(text=text)]))])


def test_is_quota_exhausted_recognizes_a_real_429_resource_exhausted():
    assert _is_quota_exhausted(_quota_exhausted_error()) is True


def test_is_quota_exhausted_rejects_other_errors():
    """Anything else (bad prompt, invalid model id, auth failure) should keep failing loudly
    rather than silently trying a second model that's no more likely to succeed."""
    not_found = ClientError(404, {"error": {"status": "NOT_FOUND", "message": "model not found"}})
    plain_exception = RuntimeError("something else entirely")

    assert _is_quota_exhausted(not_found) is False
    assert _is_quota_exhausted(plain_exception) is False


def test_falls_back_to_the_fallback_model_when_the_primary_is_quota_exhausted():
    generator = GeminiInsightGenerator(api_key="test-key", model="primary-model", fallback_model="fallback-model")
    calls = []

    def fake_generate_content(model, contents, config):
        calls.append(model)
        if model == "primary-model":
            raise _quota_exhausted_error()
        return _response("answer from the fallback model")

    generator._client.models.generate_content = fake_generate_content

    result = generator._complete("some prompt")

    assert result == "answer from the fallback model"
    assert calls == ["primary-model", "fallback-model"]


def test_does_not_fall_back_when_no_fallback_model_is_configured():
    """Screening's default (fallback_model=None) — already on the high-quota model, so a 429
    there should fail loudly rather than silently trying some other model."""
    generator = GeminiInsightGenerator(api_key="test-key", model="primary-model")

    def fake_generate_content(model, contents, config):
        raise _quota_exhausted_error()

    generator._client.models.generate_content = fake_generate_content

    with pytest.raises(ClientError):
        generator._complete("some prompt")


def test_does_not_fall_back_for_a_non_quota_error():
    generator = GeminiInsightGenerator(api_key="test-key", model="primary-model", fallback_model="fallback-model")
    calls = []

    def fake_generate_content(model, contents, config):
        calls.append(model)
        raise ClientError(404, {"error": {"status": "NOT_FOUND", "message": "model not found"}})

    generator._client.models.generate_content = fake_generate_content

    with pytest.raises(ClientError):
        generator._complete("some prompt")

    assert calls == ["primary-model"]  # never tried the fallback for a non-quota error
