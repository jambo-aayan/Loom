# Deployment: Vercel + Neon + Cloud Run + Cloud Scheduler

Frontend on Vercel, database on Neon, backend API on Cloud Run, scheduled jobs (trade pass,
screening, research, reconciliation) as Cloud Run Jobs triggered by Cloud Scheduler — chosen over
Render for being the platform to keep using long-term, not just the fastest to stand up (see the
hosting discussion this repo's history records). This doc is the manual/one-time steps; day-to-day
deploys after this are just `git push` (backend: GitHub Actions; frontend: Vercel's own git
integration).

Phase 1 is demo-only (CONTEXT.md's "Live trading gate" defaults off) — nothing here ever sets a
`T212_LIVE_API_KEY`, which stays the strongest safety net regardless of what else is configured.

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
echo -n "<your T212 demo API key>" | gcloud secrets versions add loom-t212-demo-api-key --data-file=-
echo -n "<your T212 demo API secret>" | gcloud secrets versions add loom-t212-demo-api-secret --data-file=-
echo -n "<your Anthropic key>" | gcloud secrets versions add loom-anthropic-api-key --data-file=-
echo -n "<your Google (Gemini) key, or leave blank>" | gcloud secrets versions add loom-google-api-key --data-file=-
```

T212 key + secret: generate together from "New API key" in the T212 app — the secret is shown
once at creation, save it then. This is the **Demo** account's key; nothing here ever touches the
Live one.

Re-run `gcloud run services update loom-api --region "$REGION"` (or just redeploy) after changing
a secret's value for it to pick up the new version.

## 3. Database migrations

Run once against the real Neon database (also runs automatically on every deploy via GitHub
Actions — see step 5):

```bash
cd backend
DATABASE_URL="postgresql+psycopg://..." alembic upgrade head
```

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

The mitigating factor: Phase 1 is demo-only. `T212_LIVE_API_KEY` is never set, the live-trading
gate defaults off and independently blocks the backend from ever placing a live order (CONTEXT.md
"Live trading gate"), and it's a single paper-trading account — the worst an unauthenticated
caller can do during Phase 1 is generate or approve demo trades with fake money. Revisit this
before Phase 2 (turning live trading on): options include Cloud Run IAM (`--no-allow-unauthenticated`
+ a lightweight authenticated proxy the frontend calls through), Vercel's deployment protection
password-gating the whole frontend, or building real session auth.

## Day-to-day

- **Backend**: `git push` to `main` → GitHub Actions tests, builds, deploys. Nothing manual.
- **Frontend**: `git push` → Vercel deploys automatically.
- **Scheduled jobs**: run on their own via Cloud Scheduler; check `gcloud run jobs executions list
  --job=<job-name> --region=<region>` if one seems to have stopped firing.
- **Turning on live trading (Phase 2)**: create `loom-t212-live-api-key` /
  `loom-t212-live-api-secret` secrets, wire them into the Cloud Run Service/Jobs' `--set-secrets`
  as `T212_LIVE_API_KEY` / `T212_LIVE_API_SECRET`, then flip the Live trading gate on in Settings
  — in that order, so the gate is the last, deliberate step, not an afterthought.
