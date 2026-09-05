# Tech stack: FastAPI + Next.js + Neon Postgres

We chose FastAPI (Python) for the backend/trading core, Next.js (TypeScript/React) for the dashboard, and Postgres via Neon for storage — over a simpler single-language option (e.g. FastAPI + server-rendered HTMX pages, SQLite for storage). The simpler option was the initial recommendation, but was explicitly overridden: this project is expected to move fast, evolve rapidly (multiple strategies, an LLM insight layer, a possible future product), and the user was willing to accept more moving parts up front in exchange for a foundation that scales without a rework later. Neon's branching is also a genuine fit for a fast-moving project (cheap per-feature/per-test database branches).

## Consequences

Two languages (Python + TypeScript) instead of one; an external DB dependency (Neon) from day one instead of a local SQLite file. Accepted deliberately in exchange for not having to migrate off SQLite or rewrite a server-rendered UI into a real frontend later.
