"""Confirmed live: an unhandled exception in a route (a broken Gemini model ID, in this case)
bypassed CORSMiddleware entirely and the browser reported it as "Failed to fetch" — a real
backend failure disguised as a network problem, with no way to tell the two apart from the
frontend. main.py's global exception handler (registered via @app.exception_handler(Exception))
fixes this: Starlette only skips CORSMiddleware for exceptions that escape *without* a registered
handler, so registering one turns the 500 back into a normal, CORS-friendly response."""

import pytest
from fastapi.testclient import TestClient

from loom import db
from loom.api.deps import get_insight_generator


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/unhandled_exception_test.db")
    from loom.api.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    db._engine = None
    db._SessionLocal = None


def test_an_unhandled_exception_still_carries_cors_headers(client):
    def _broken_generator():
        raise RuntimeError("simulated provider failure (e.g. an invalid model id)")

    client.app.dependency_overrides[get_insight_generator] = _broken_generator

    response = client.post(
        "/insights/ask", json={"question": "test"}, headers={"origin": "https://example.com"}
    )

    assert response.status_code == 500
    assert response.headers.get("access-control-allow-origin") == "*"
