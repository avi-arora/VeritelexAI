#!/usr/bin/env bash
# VeriteLex AI — idempotent GCP foundation setup (no application deployment).
#
# Creates everything the backend needs to run locally against real GCP
# services *and* later on Cloud Run: APIs, Firestore, buckets, Cloud Tasks
# queue, Artifact Registry, least-privilege service accounts and IAM.
#
# Re-running is safe: every step checks for existing resources first.
#
# Usage:  PROJECT_ID=veritelex-ai-0pnts ./infra/setup.sh
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-us-central1}"
BILLING_ACCOUNT="${BILLING_ACCOUNT:-01D97A-287906-2651D3}"
LOCAL_ORIGINS="${LOCAL_ORIGINS:-http://localhost:3000,http://127.0.0.1:3000}"
DEV_USER="${DEV_USER:-$(gcloud config get-value account 2>/dev/null)}"

CASE_BUCKET="${PROJECT_ID}-case-files"
ARTIFACT_BUCKET="${PROJECT_ID}-artifacts"
QUEUE="agent-steps"
AR_REPO="veritelex"

SA_API="vtx-api"
SA_WORKER="vtx-worker"
SA_WEB="vtx-web"
sa_email() { echo "$1@${PROJECT_ID}.iam.gserviceaccount.com"; }

g() { gcloud --project="${PROJECT_ID}" --quiet "$@"; }
log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

log "Linking billing account ${BILLING_ACCOUNT}"
gcloud billing projects link "${PROJECT_ID}" --billing-account="${BILLING_ACCOUNT}" --quiet >/dev/null

log "Enabling APIs"
g services enable \
  run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  firestore.googleapis.com storage.googleapis.com cloudtasks.googleapis.com \
  aiplatform.googleapis.com iam.googleapis.com iamcredentials.googleapis.com \
  logging.googleapis.com monitoring.googleapis.com cloudtrace.googleapis.com \
  serviceusage.googleapis.com cloudresourcemanager.googleapis.com

log "Firestore (Native) in ${REGION}"
if ! g firestore databases describe --database="(default)" >/dev/null 2>&1; then
  g firestore databases create --database="(default)" --location="${REGION}" --type=firestore-native \
    --delete-protection
fi

log "Firestore composite indexes"
# cases ordered by recency, filtered by 'past' scope.
g firestore indexes composite create --collection-group=cases \
  --field-config=field-path=past,order=ascending --field-config=field-path=updated_at,order=descending \
  >/dev/null 2>&1 || true

log "Buckets (private, uniform access, public-access prevention)"
for b in "${CASE_BUCKET}" "${ARTIFACT_BUCKET}"; do
  if ! g storage buckets describe "gs://${b}" >/dev/null 2>&1; then
    g storage buckets create "gs://${b}" --location="${REGION}" \
      --uniform-bucket-level-access --public-access-prevention --soft-delete-duration=7d
  fi
done
# Browser uploads go straight to the case-files bucket via V4 signed URLs.
# shellcheck source=cors.sh
source "$(dirname "${BASH_SOURCE[0]}")/cors.sh"
apply_upload_cors "${CASE_BUCKET}" ${LOCAL_ORIGINS//,/ }
# Court papers are evidence: keep prior object versions if a file is overwritten.
g storage buckets update "gs://${CASE_BUCKET}" --versioning >/dev/null

log "Cloud Tasks queue ${QUEUE}"
QUEUE_FLAGS=(--location="${REGION}" --max-concurrent-dispatches=20 --max-dispatches-per-second=5
  --max-attempts=8 --min-backoff=5s --max-backoff=300s --max-doublings=5)
if g tasks queues describe "${QUEUE}" --location="${REGION}" >/dev/null 2>&1; then
  g tasks queues update "${QUEUE}" "${QUEUE_FLAGS[@]}" >/dev/null
else
  g tasks queues create "${QUEUE}" "${QUEUE_FLAGS[@]}"
fi

log "Artifact Registry ${AR_REPO}"
if ! g artifacts repositories describe "${AR_REPO}" --location="${REGION}" >/dev/null 2>&1; then
  g artifacts repositories create "${AR_REPO}" --repository-format=docker --location="${REGION}" \
    --description="VeriteLex AI images"
fi

log "Service accounts"
for sa in "${SA_API}:VeriteLex API" "${SA_WORKER}:VeriteLex agent worker" "${SA_WEB}:VeriteLex web frontend"; do
  id="${sa%%:*}"; name="${sa#*:}"
  if ! g iam service-accounts describe "$(sa_email "$id")" >/dev/null 2>&1; then
    g iam service-accounts create "$id" --display-name="$name"
  fi
done
sleep 5  # IAM propagation for newly created service accounts

proj_role() { g projects add-iam-policy-binding "${PROJECT_ID}" --member="$1" --role="$2" --condition=None >/dev/null; }
bucket_role() { g storage buckets add-iam-policy-binding "gs://$1" --member="$2" --role="$3" >/dev/null; }
sa_role() { g iam service-accounts add-iam-policy-binding "$(sa_email "$1")" --member="$2" --role="$3" >/dev/null; }

API="serviceAccount:$(sa_email ${SA_API})"
WORKER="serviceAccount:$(sa_email ${SA_WORKER})"

log "IAM: API service account"
proj_role "${API}" roles/datastore.user
proj_role "${API}" roles/cloudtasks.enqueuer
proj_role "${API}" roles/logging.logWriter
proj_role "${API}" roles/aiplatform.user        # council availability checks (GET /council/models pings each model)
bucket_role "${CASE_BUCKET}" "${API}" roles/storage.objectAdmin
bucket_role "${ARTIFACT_BUCKET}" "${API}" roles/storage.objectViewer
sa_role "${SA_API}" "${API}" roles/iam.serviceAccountTokenCreator   # signBlob for V4 signed URLs
sa_role "${SA_WORKER}" "${API}" roles/iam.serviceAccountUser         # mint OIDC tokens for tasks

log "IAM: worker service account"
proj_role "${WORKER}" roles/datastore.user
proj_role "${WORKER}" roles/cloudtasks.enqueuer
proj_role "${WORKER}" roles/aiplatform.user
proj_role "${WORKER}" roles/logging.logWriter
proj_role "${WORKER}" roles/cloudtrace.agent
bucket_role "${CASE_BUCKET}" "${WORKER}" roles/storage.objectViewer
bucket_role "${ARTIFACT_BUCKET}" "${WORKER}" roles/storage.objectAdmin
sa_role "${SA_WORKER}" "${WORKER}" roles/iam.serviceAccountUser

log "IAM: local developer ${DEV_USER} (signed URLs when running locally)"
if [[ -n "${DEV_USER}" ]]; then
  sa_role "${SA_API}" "user:${DEV_USER}" roles/iam.serviceAccountTokenCreator
fi

log "Done. Resources:"
cat <<EOF
  Project          ${PROJECT_ID}  (${REGION})
  Firestore        (default)
  Buckets          gs://${CASE_BUCKET}  gs://${ARTIFACT_BUCKET}
  Tasks queue      projects/${PROJECT_ID}/locations/${REGION}/queues/${QUEUE}
  Artifact Reg.    ${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}
  Service accounts $(sa_email ${SA_API}), $(sa_email ${SA_WORKER}), $(sa_email ${SA_WEB})
EOF
