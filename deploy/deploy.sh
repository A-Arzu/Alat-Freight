#!/usr/bin/env bash
# One-shot Google Cloud deployment for the Port Operations Dispatch Agent.
#
# Run from Cloud Shell (recommended - gcloud preinstalled) or any machine
# with the gcloud SDK, from anywhere inside the repo:
#
#   bash deploy/deploy.sh YOUR_PROJECT_ID
#
# Idempotent: safe to re-run; re-deploys the service and updates the job.
# Optional env overrides: REGION SERVICE RUN_TOKEN GEMINI_MODEL SCHEDULE_TZ
set -euo pipefail

PROJECT_ID="${1:-${PROJECT_ID:-}}"
if [[ -z "$PROJECT_ID" ]]; then
  echo "usage: bash deploy/deploy.sh YOUR_PROJECT_ID" >&2
  exit 1
fi
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-dispatch-agent}"
# gemini-3.5-flash is the GA Gemini 3.5 model (3.5 Pro is not public yet);
# GENAI_LOCATION=global routes model calls via the global endpoint, which
# serves GA Gemini models regardless of regional rollout.
GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.5-flash}"
GENAI_LOCATION="${GENAI_LOCATION:-global}"
SCHEDULE_TZ="${SCHEDULE_TZ:-Asia/Baku}"
RUN_TOKEN="${RUN_TOKEN:-$(openssl rand -hex 12 2>/dev/null || echo demo-$RANDOM$RANDOM)}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

step() { echo; echo "==== $* ===="; }

step "1/6 Project + APIs"
gcloud config set project "$PROJECT_ID" --quiet
gcloud services enable run.googleapis.com firestore.googleapis.com \
  aiplatform.googleapis.com cloudscheduler.googleapis.com \
  secretmanager.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com --quiet

step "2/6 Firestore (native mode)"
if gcloud firestore databases describe --database='(default)' >/dev/null 2>&1; then
  echo "Firestore database already exists - keeping it."
else
  gcloud firestore databases create --location=nam5 --quiet
fi

step "3/6 Deploy Cloud Run service (builds Dockerfile via Cloud Build)"
# --no-cpu-throttling: background agent runs keep CPU between requests
gcloud run deploy "$SERVICE" \
  --source "$ROOT" \
  --region "$REGION" \
  --allow-unauthenticated \
  --memory 1Gi --cpu 1 \
  --no-cpu-throttling \
  --max-instances 3 \
  --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${GENAI_LOCATION},STORE=firestore,PLANNER=gemini,GEMINI_MODEL=${GEMINI_MODEL},RUN_TOKEN=${RUN_TOKEN},TRACE_DELAY_MS=250" \
  --quiet
URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"

step "4/6 IAM for the service account (Vertex AI + Firestore)"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA}" --role=roles/aiplatform.user --quiet >/dev/null
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA}" --role=roles/datastore.user --quiet >/dev/null
echo "granted aiplatform.user + datastore.user to ${SA}"

step "5/6 Cloud Scheduler - daily 06:00 dispatch run"
if gcloud scheduler jobs describe daily-dispatch --location "$REGION" >/dev/null 2>&1; then
  gcloud scheduler jobs update http daily-dispatch --location "$REGION" \
    --schedule="0 6 * * *" --time-zone="$SCHEDULE_TZ" --http-method=POST \
    --uri="${URL}/optimize?sync=true" \
    --update-headers "X-Run-Token=${RUN_TOKEN}" \
    --attempt-deadline=300s --quiet
else
  gcloud scheduler jobs create http daily-dispatch --location "$REGION" \
    --schedule="0 6 * * *" --time-zone="$SCHEDULE_TZ" --http-method=POST \
    --uri="${URL}/optimize?sync=true" \
    --headers "X-Run-Token=${RUN_TOKEN}" \
    --attempt-deadline=300s --quiet
fi

step "6/6 Done"
cat <<EOF

  Service URL:   ${URL}
  Run token:     ${RUN_TOKEN}          (save this!)
  Scheduler:     daily-dispatch @ 06:00 ${SCHEDULE_TZ}

Next:
  bash deploy/verify.sh "${URL}" "${RUN_TOKEN}"     # end-to-end cloud test (proves Gemini ran)
  open ${URL}                                        # the dashboard

Demo-recording tips:
  gcloud run services update ${SERVICE} --region ${REGION} --min-instances 1   # no cold starts on camera
  gcloud run services update ${SERVICE} --region ${REGION} --min-instances 0   # back to scale-to-zero after
  gcloud scheduler jobs pause daily-dispatch --location ${REGION}              # after submission

Optional email delivery (Gmail app password):
  echo -n "APP_PASSWORD" | gcloud secrets create smtp-pass --data-file=-
  gcloud secrets add-iam-policy-binding smtp-pass --member="serviceAccount:${SA}" --role=roles/secretmanager.secretAccessor
  gcloud run services update ${SERVICE} --region ${REGION} \\
    --set-secrets SMTP_PASS=smtp-pass:latest \\
    --set-env-vars SMTP_HOST=smtp.gmail.com,SMTP_PORT=465,SMTP_USER=you@gmail.com,EMAIL_TO=dispatcher@example.com
EOF
