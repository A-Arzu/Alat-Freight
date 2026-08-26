#!/usr/bin/env bash
# Gmail delivery setup for the deployed service - run in Cloud Shell:
#
#   bash deploy/email_setup.sh
#
# Prerequisite: a Gmail account with 2-Step Verification and an App Password
# (create one at https://myaccount.google.com/apppasswords - takes 1 minute).
#
# The password is read with hidden input and goes ONLY to Secret Manager;
# it never appears in shell history, logs, or the service env vars.
set -euo pipefail

PROJECT_ID="${1:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-dispatch-agent}"
[[ -n "$PROJECT_ID" ]] || { echo "usage: bash deploy/email_setup.sh PROJECT_ID" >&2; exit 1; }
gcloud config set project "$PROJECT_ID" --quiet >/dev/null

read -rp  "Gmail address that SENDS the plan (SMTP_USER): " SMTP_USER
read -rp  "Recipient inbox for dispatch plans (EMAIL_TO): " EMAIL_TO
read -rsp "Gmail App Password (input hidden; spaces are OK): " APP_PASS; echo
APP_PASS="${APP_PASS// /}"   # Google displays app passwords with spaces - strip them
[[ -n "$APP_PASS" && -n "$SMTP_USER" && -n "$EMAIL_TO" ]] || { echo "missing input" >&2; exit 1; }

if gcloud secrets describe smtp-pass >/dev/null 2>&1; then
  printf '%s' "$APP_PASS" | gcloud secrets versions add smtp-pass --data-file=- >/dev/null
  echo "secret smtp-pass: new version added"
else
  printf '%s' "$APP_PASS" | gcloud secrets create smtp-pass --data-file=- >/dev/null
  echo "secret smtp-pass: created"
fi
unset APP_PASS

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
gcloud secrets add-iam-policy-binding smtp-pass \
  --member="serviceAccount:${SA}" --role=roles/secretmanager.secretAccessor --quiet >/dev/null
echo "granted secretAccessor to ${SA}"

gcloud run services update "$SERVICE" --region "$REGION" \
  --set-secrets "SMTP_PASS=smtp-pass:latest" \
  --update-env-vars "SMTP_HOST=smtp.gmail.com,SMTP_PORT=465,SMTP_USER=${SMTP_USER},EMAIL_TO=${EMAIL_TO}" \
  --quiet
URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"

cat <<EOF

Email delivery configured.
Test it (uses your saved run token):
  curl -sS -X POST "${URL}/optimize?sync=true" -H "X-Run-Token: YOUR_TOKEN" -d ''
Then check ${EMAIL_TO} - the first email may land in spam; mark it "not spam"
before recording the demo. The dashboard's Dispatcher Delivery panel will now
show "email sent" instead of "rendered".
EOF
