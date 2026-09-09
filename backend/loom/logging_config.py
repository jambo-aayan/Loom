"""Configures Python's logging so module-level loggers (loom.t212, uvicorn's own, etc.) actually
emit somewhere — without this, a bare `logging.getLogger("loom.t212").info(...)` call is silently
dropped: Python attaches a "last resort" handler only when nothing else is configured, and that
handler only surfaces WARNING and above. Confirmed live: `t212_client.py`'s request/response
logging (its own docstring: "logs every request/response") never once appeared in Cloud Run logs
across an entire debugging session, because nothing had called this. Call `configure()` once, as
early as possible, from every process entrypoint (the API's `main.py`, the CLI's `main.py`) — not
importable-module side effects, since this is an application concern, not a library one."""

from __future__ import annotations

import logging


def configure(level: int = logging.INFO) -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(name)s %(levelname)s %(message)s")
