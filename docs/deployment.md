# Deployment: Vercel + Neon + Cloud Run + Cloud Scheduler

Frontend on Vercel, database on Neon, backend API on Cloud Run, scheduled jobs (trade pass,
screening, research, reconciliation) as Cloud Run Jobs triggered by Cloud Scheduler — chosen over
Render for being the platform to keep using long-term, not just the fastest to stand up (see the
hosting discussion this repo's history records). This doc is the manual/one-time steps; day-to-day
deploys after this are just `git push` (backend: GitHub Actions; frontend: Vercel's own git
integration).

**Fastest path through this**: `./scripts/deploy-wizard.sh` from the repo root walks through
every stage below interactively — opens each dashboard, tells you what to click/copy, and writes
the values where they belong (`backend/.env`, GCP Secret Manager, GitHub Actions secrets). Safe
to stop and re-run; it remembers what you've already entered. The rest of this doc is the
reference for what it's doing and why, and how to do any of it by hand if you'd rather.

A T212 account issues one API key+secret pair total, not one per demo/live — it authenticates
identically against either base URL. That means, unlike an earlier assumption in this repo's
history, there's no separate "live" credential to simply withhold as a safety net: the moment
`T212_API_KEY`/`T212_API_SECRET` are configured at all, they're capable of a live order. The
**only** thing standing between that key and a real trade is the "Live trading gate" (CONTEXT.md)
defaulting off — treat flipping it on as the one deliberate, real step into Phase 2, not a
formality.

## 1. Neon (database)

1. Create a project at neon.tech, note the connection string (`postgresql://...`).
2. Loom's `DATABASE_URL` setting expects the `psycopg` driver scheme: rewrite it to
   `postgresql+psycopg://...` (same string, just the scheme prefix).
3. Nothing else to configure — Loom creates its schema via Alembic migrations (step 3 below), not
   by hand.

## 2. GCP (backend API + scheduled jobs)

Prerequisites: a GCP project with billing enabled, `gcloud` installed and authenticated
(`gcloud auth login`, `gcloud config set project <PROJECT_ID>`).

Run the provisioning script once:

```bash
PROJECT_ID=<your-project-id> REGION=europe-west2 ./infra/gcp/setup.sh
```

This creates: an Artifact Registry repo, two service accounts (`loom-runtime` for the app,
`loom-scheduler` scoped to only trigger Cloud Run Jobs), five Secret Manager secrets (empty —
fill them next), the Cloud Run Service (the always-on API), four Cloud Run Jobs mirroring the
existing `loom trade-pass` / `screen-insights` / `research-insights` / `reconcile` CLI commands
(ADR-0002: this was already designed as "invoked either manually (CLI) or by a scheduler" — Cloud
Run Jobs run the exact same image and command, nothing new to build), and Cloud Scheduler entries
that trigger each Job on a starting cadence (weekdays; adjust with `gcloud scheduler jobs update`
— v1's strategies are patient/low-frequency by design, not intraday, so don't default to
anything aggressive).

Fill the secrets the script creates empty:

```bash
echo -n "postgresql+psycopg://..." | gcloud secrets versions add loom-database-url --data-file=-
echo -n "<your T212 API key>" | gcloud secrets versions add loom-t212-api-key --data-file=-
echo -n "<your T212 API secret>" | gcloud secrets versions add loom-t212-api-secret --data-file=-
echo -n "<your Anthropic key>" | gcloud secrets versions add loom-anthropic-api-key --data-file=-
echo -n "<your Google (Gemini) key, or leave blank>" | gcloud secrets versions add loom-google-api-key --data-file=-
```

T212 key + secret: generate together from "New API key" in the T212 app — the secret is shown
once at creation, save it then. There's only one pair per account; it works against both
`demo.trading212.com` and `live.trading212.com` — Loom picks the URL per `Environment`, the
credential itself doesn't distinguish them. This is exactly why the Live trading gate matters:
nothing about the credential stops it from placing a live order once the gate is on.

Re-run `gcloud run services update loom-api --region "$REGION"` (or just redeploy) after changing
a secret's value for it to pick up the new version.

## 3. Database migrations

Run once against the real Neon database, **before** the Cloud Run Service ever serves its first
request (also runs automatically on every deploy via GitHub Actions — see step 5, in the correct
order):

```bash
cd backend
DATABASE_URL="postgresql+psycopg://..." alembic upgrade head
```

`loom.db.init_db()` only auto-creates the schema (`Base.metadata.create_all()`) for sqlite —
against a real Postgres database, Alembic is the sole source of schema truth, on purpose: an
earlier version of this ran unconditionally, so the very first request to a freshly deployed
Cloud Run service created the whole schema directly from the models before `alembic upgrade head`
ever got a chance to run, and Alembic's own migration then failed with `DuplicateObject` trying to
create objects that already existed. If you ever hit that error against a database you're sure is
otherwise correct (schema matches current models, just never went through Alembic — e.g. it was
provisioned by an old build before this fix), the recovery is `alembic stamp head`, which records
the migration history as up to date without re-running any DDL — not `alembic upgrade head`.

## 4. Vercel (frontend)

1. Import the repo at vercel.com, root directory `frontend`. Next.js needs no other config.
2. Set one environment variable: `NEXT_PUBLIC_API_BASE_URL` = the Cloud Run Service URL printed
   at the end of `infra/gcp/setup.sh` (looks like `https://loom-api-xxxxx-ew.a.run.app`).
3. Every push to the connected branch redeploys automatically — nothing else to wire up.

## 5. GitHub Actions (backend CI/CD)

`.github/workflows/deploy-backend.yml` runs the backend test suite, then builds/pushes the image,
runs migrations, and redeploys the Cloud Run Service + all four Jobs — on every push to `main`
that touches `backend/**`. Add these repository secrets (Settings → Secrets and variables →
Actions):

| Secret | Value |
|---|---|
| `GCP_PROJECT_ID` | your GCP project id |
| `GCP_DEPLOY_SA_KEY` | a JSON key for a service account with `roles/run.admin`, `roles/artifactregistry.writer`, and `roles/iam.serviceAccountUser` — create with `gcloud iam service-accounts keys create` |
| `DATABASE_URL` | the same Neon connection string, `postgresql+psycopg://...` scheme |

`DATABASE_URL` deliberately lives in two places — this GitHub secret (used to run migrations from
CI) and the `loom-database-url` Secret Manager secret (used by the running Service/Jobs) — nothing
keeps them in sync automatically. If you ever rotate the Neon connection string, update **both**;
a mismatch means migrations run against a different database than the app actually serves from.

The deploy service account is deliberately separate from `loom-runtime` (which only needs
Secret Manager read access) and `loom-scheduler` (which only needs to trigger Job runs) — CI's
identity needs to *manage* Cloud Run, the app's own identity doesn't.

## Known gap: no API authentication (accepted for Phase 1)

The FastAPI app has no auth layer and CORS is wide open (`allow_origins=["*"]`) — anyone with the
Cloud Run URL can hit any endpoint, including approving/rejecting signals or triggering a trading
pass. This is a real gap, deliberately not papered over with a shared-secret header baked into
the frontend's client-side JS, since that wouldn't actually be secret in a browser — a proper fix
needs real session auth (a login), which is out of scope for a single-user Phase 1 launch.

Be honest about what actually protects you here. The live-trading gate defaults off, but its own
toggle endpoint (`POST /settings/live-trading-gate/enable`) is just as unauthenticated as
everything else — anyone who finds the Cloud Run URL could flip it on themselves, then approve a
signal in the `live` environment. T212 issuing one key for both environments (no separate,
withheld live credential) means there's nothing else standing behind the gate either. So the gate
protects you from your *own* accidental clicks, not from an outside actor who has the URL. What's
actually doing the work right now is that the URL itself is unguessable (Cloud Run assigns a
random hostname like `loom-api-<hash>-<region>.a.run.app`, never linked anywhere public or
indexed) — weak, but real, and the reason this is an acceptable Phase 1 posture rather than an
active incident. Do not point a custom domain at this service, and do not treat "add live
credentials" and "fix API auth" as separable tasks — build real auth (Cloud Run IAM + an
authenticated proxy, or session auth) *before* a live key ever goes into Secret Manager, not after.

## Day-to-day

- **Backend**: `git push` to `main` → GitHub Actions tests, builds, deploys. Nothing manual.
- **Frontend**: `git push` → Vercel deploys automatically.
- **Scheduled jobs**: run on their own via Cloud Scheduler; check `gcloud run jobs executions list
  --job=<job-name> --region=<region>` if one seems to have stopped firing.
- **Turning on live trading (Phase 2)**: the same `T212_API_KEY`/`T212_API_SECRET` already
  configured for demo already work against live — there's no separate credential to add. Fix the
  API-auth gap above *first*, then flip the Live trading gate on in Settings as the final,
  deliberate step.
