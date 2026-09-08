#!/usr/bin/env bash
# One-time GCP provisioning for Loom's backend: Cloud Run (API service) + Cloud Run Jobs
# (scheduled CLI commands) + Cloud Scheduler (triggers the Jobs) + Artifact Registry + Secret
# Manager. Run this once per environment (it's idempotent — safe to re-run after edits).
#
# Prerequisites: `gcloud auth login`, a GCP project with billing enabled, and
# `gcloud config set project <PROJECT_ID>` already done. See docs/deployment.md for the full
# walkthrough (this script covers the GCP side only; Vercel and Neon are separate, manual steps).
#
# Usage:
#   PROJECT_ID=my-project REGION=europe-west2 ./infra/gcp/setup.sh
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID, e.g. PROJECT_ID=loom-prod ./setup.sh}"
REGION="${REGION:-europe-west2}"
REPO="loom"
SERVICE="loom-api"
RUNTIME_SA="loom-runtime@${PROJECT_ID}.iam.gserviceaccount.com"
SCHEDULER_SA="loom-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/api:latest"

echo "==> Enabling required APIs"
gcloud services enable \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  iam.googleapis.com \
  --project "$PROJECT_ID"

echo "==> Artifact Registry repo"
gcloud artifacts repositories describe "$REPO" --location "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1 || \
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker \
  --location="$REGION" \
  --project "$PROJECT_ID"

echo "==> Service accounts"
# Runtime SA: what the Cloud Run Service and Jobs run as. Only needs Secret Manager access —
# it does not need to deploy or manage Cloud Run itself (that's the CI/CD identity, separate).
gcloud iam service-accounts describe "$RUNTIME_SA" --project "$PROJECT_ID" >/dev/null 2>&1 || \
gcloud iam service-accounts create loom-runtime \
  --display-name="Loom Cloud Run runtime" \
  --project "$PROJECT_ID"

# Scheduler SA: what Cloud Scheduler authenticates as when it calls the Cloud Run Admin API to
# start a Job execution. That only needs the `run.jobs.run` permission, but there's no predefined
# role scoped that narrowly — `roles/run.developer` (granted below) is broader than strictly
# necessary (it can also create/update/delete Jobs and Services, not just run them). Narrow this
# with a custom IAM role restricted to `run.jobs.run` + `run.jobs.get` if you want tighter scoping;
# not done here to avoid depending on custom-role support being enabled in a fresh project.
gcloud iam service-accounts describe "$SCHEDULER_SA" --project "$PROJECT_ID" >/dev/null 2>&1 || \
gcloud iam service-accounts create loom-scheduler \
  --display-name="Loom Cloud Scheduler invoker" \
  --project "$PROJECT_ID"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/secretmanager.secretAccessor" \
  --condition=None >/dev/null

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SCHEDULER_SA}" \
  --role="roles/run.developer" \
  --condition=None >/dev/null

echo "==> Secret Manager stubs (fill real values with: gcloud secrets versions add SECRET --data-file=-)"
# A T212 account issues one key+secret pair total — not one per demo/live — so there is
# deliberately only one loom-t212-api-key/loom-t212-api-secret pair here, used with both base
# URLs (settings.py already picks the URL per Environment); the "Live trading gate" in Settings,
# not a separate credential, is what actually stands between this key and a real order.
for SECRET in loom-database-url loom-t212-api-key loom-t212-api-secret loom-anthropic-api-key loom-google-api-key; do
  gcloud secrets describe "$SECRET" --project "$PROJECT_ID" >/dev/null 2>&1 || \
  gcloud secrets create "$SECRET" --replication-policy="automatic" --project "$PROJECT_ID"
done

cat <<'NOTE'
==> Secrets created empty. Fill each one now, e.g.:
      echo -n "postgresql+psycopg://..." | gcloud secrets versions add loom-database-url --data-file=-
    Repeat for loom-t212-api-key, loom-t212-api-secret, loom-anthropic-api-key,
    loom-google-api-key. Leave a secret's value blank (empty string version) for anything you're
    not using yet (e.g. GOOGLE_API_KEY in early dev) — Loom's settings all default to "" meaning
    "use the fake/no-op implementation" (ADR-0004).
NOTE

echo "==> Build and push the image once (subsequent pushes happen via CI — see .github/workflows/deploy-backend.yml)"
gcloud builds submit ./backend --tag "$IMAGE" --project "$PROJECT_ID"

SECRET_FLAGS="--set-secrets=DATABASE_URL=loom-database-url:latest,T212_API_KEY=loom-t212-api-key:latest,T212_API_SECRET=loom-t212-api-secret:latest,ANTHROPIC_API_KEY=loom-anthropic-api-key:latest,GOOGLE_API_KEY=loom-google-api-key:latest"

echo "==> Deploying Cloud Run Service (the always-on API)"
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --service-account "$RUNTIME_SA" \
  --allow-unauthenticated \
  --min-instances=0 \
  --max-instances=2 \
  $SECRET_FLAGS

SERVICE_URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)')
echo "==> Service deployed at: ${SERVICE_URL}"
echo "    Set this as NEXT_PUBLIC_API_BASE_URL in your Vercel project's env vars."

echo "==> Creating Cloud Run Jobs (same image, command overridden per job — ADR-0002)"
declare -A JOB_COMMANDS=(
  [loom-trade-pass]="loom,trade-pass,--environment,demo"
  [loom-screen-insights]="loom,screen-insights,--environment,demo"
  [loom-research-insights]="loom,research-insights,--environment,demo"
  [loom-reconcile]="loom,reconcile,--environment,demo"
)

for JOB in "${!JOB_COMMANDS[@]}"; do
  IFS=',' read -ra CMD <<< "${JOB_COMMANDS[$JOB]}"
  if gcloud run jobs describe "$JOB" --region "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1; then
    gcloud run jobs update "$JOB" \
      --image "$IMAGE" \
      --region "$REGION" \
      --project "$PROJECT_ID" \
      --service-account "$RUNTIME_SA" \
      --command="${CMD[0]}" \
      --args="$(IFS=,; echo "${CMD[*]:1}")" \
      $SECRET_FLAGS
  else
    gcloud run jobs create "$JOB" \
      --image "$IMAGE" \
      --region "$REGION" \
      --project "$PROJECT_ID" \
      --service-account "$RUNTIME_SA" \
      --command="${CMD[0]}" \
      --args="$(IFS=,; echo "${CMD[*]:1}")" \
      --max-retries=1 \
      $SECRET_FLAGS
  fi
done

echo "==> Creating Cloud Scheduler jobs to trigger each Cloud Run Job"
# Cadence is a starting point, not gospel — v1's strategies are patient/low-frequency (ADR-0002),
# not intraday. Adjust with: gcloud scheduler jobs update http <name> --schedule="..."
declare -A SCHEDULES=(
  [loom-trade-pass]="0 8 * * 1-5"          # weekdays, 08:00 UTC (after markets open)
  [loom-screen-insights]="15 8 * * 1-5"    # 15 min after trade-pass, so new signals exist
  [loom-research-insights]="30 8 * * 1-5"  # 15 min after screening
  [loom-reconcile]="0 18 * * 1-5"          # end of day
)

for JOB in "${!SCHEDULES[@]}"; do
  SCHEDULER_URI="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB}:run"
  if gcloud scheduler jobs describe "$JOB" --location "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1; then
    gcloud scheduler jobs update http "$JOB" \
      --location "$REGION" \
      --project "$PROJECT_ID" \
      --schedule="${SCHEDULES[$JOB]}" \
      --uri="$SCHEDULER_URI" \
      --http-method=POST \
      --oauth-service-account-email="$SCHEDULER_SA"
  else
    gcloud scheduler jobs create http "$JOB" \
      --location "$REGION" \
      --project "$PROJECT_ID" \
      --schedule="${SCHEDULES[$JOB]}" \
      --uri="$SCHEDULER_URI" \
      --http-method=POST \
      --oauth-service-account-email="$SCHEDULER_SA"
  fi
done

echo "==> Done. Next: run alembic migrations against the Neon DB (see docs/deployment.md), then set NEXT_PUBLIC_API_BASE_URL=${SERVICE_URL} in Vercel."
