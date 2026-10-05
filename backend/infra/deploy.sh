#!/usr/bin/env bash
# VeriteLex AI — build and deploy to Cloud Run (us-central1).
#
#   PROJECT_ID=veritelex-ai-0pnts ./backend/infra/deploy.sh            # build + deploy all
#   PROJECT_ID=veritelex-ai-0pnts SKIP_BUILD=1 ./backend/infra/deploy.sh  # redeploy existing images
#
# Prerequisite: ./backend/infra/setup.sh has been run (APIs, Firestore, buckets,
# queue, Artifact Registry, service accounts, IAM).
#
# Topology (all private by default, least privilege):
#   vtx-web    (Next.js)  --ID token-->  vtx-api (FastAPI, role=api)
#   vtx-api    --Cloud Tasks (OIDC as vtx-worker)-->  vtx-worker (FastAPI, role=worker)
#   vtx-worker --Cloud Tasks-->  vtx-worker   (agent DAG fan-out)
#
# Images are built remotely with Cloud Build (no local Docker needed) and tagged
# with the git SHA so every revision is traceable and rollbacks are one command.
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-us-central1}"
AR_REPO="veritelex"
REG="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TAG="${TAG:-$(git -C "${ROOT}" rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)}"
if [[ -n "$(git -C "${ROOT}" status --porcelain 2>/dev/null)" ]]; then TAG="${TAG}-dirty-$(date +%H%M%S)"; fi
# Web ingress. "public" (allUsers invoker) may be blocked by the Argolis
# domain-restricted-sharing org policy; "private" keeps IAM auth on the web service
# (open via `gcloud run services proxy vtx-web --region us-central1`).
WEB_ACCESS="${WEB_ACCESS:-public}"

CASE_BUCKET="${PROJECT_ID}-case-files"
ARTIFACT_BUCKET="${PROJECT_ID}-artifacts"
sa_email() { echo "$1@${PROJECT_ID}.iam.gserviceaccount.com"; }
SA_API="$(sa_email vtx-api)"; SA_WORKER="$(sa_email vtx-worker)"; SA_WEB="$(sa_email vtx-web)"

g() { gcloud --project="${PROJECT_ID}" --quiet "$@"; }
log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
url_of() { g run services describe "$1" --region="${REGION}" --format='value(status.url)'; }
invoker() { g run services add-iam-policy-binding "$1" --region="${REGION}" --member="$2" --role=roles/run.invoker >/dev/null; }

BACKEND_IMG="${REG}/backend:${TAG}"
WEB_IMG="${REG}/web:${TAG}"

PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"

if [[ -z "${SKIP_BUILD:-}" ]]; then
  # New Argolis projects don't auto-grant roles to default service accounts, and Cloud Build
  # runs as the Compute default SA — give it only what a container build needs.
  log "Cloud Build permissions"
  BUILD_SA="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
  for role in roles/artifactregistry.writer roles/logging.logWriter roles/storage.objectViewer; do
    g projects add-iam-policy-binding "${PROJECT_ID}" --member="${BUILD_SA}" --role="${role}" --condition=None >/dev/null
  done

  log "Building images with Cloud Build (tag ${TAG})"
  g builds submit "${ROOT}/backend" --region="${REGION}" --tag="${BACKEND_IMG}"
  g builds submit "${ROOT}" --region="${REGION}" --tag="${WEB_IMG}"
fi

COMMON_ENV="VTX_ENV=prod,VTX_PROJECT_ID=${PROJECT_ID},VTX_REGION=${REGION},VTX_CASE_BUCKET=${CASE_BUCKET},VTX_ARTIFACT_BUCKET=${ARTIFACT_BUCKET},VTX_DISPATCHER=cloud_tasks,VTX_TASKS_INVOKER_SA=${SA_WORKER}"
RUN_FLAGS=(--region="${REGION}" --no-allow-unauthenticated --execution-environment=gen2 --cpu-boost)

# Deterministic Cloud Run URLs (known before the first deploy). WORKER_URL is both the
# Cloud Tasks target and the OIDC audience the worker verifies.
WORKER_URL="https://vtx-worker-${PROJECT_NUMBER}.${REGION}.run.app"
WEB_URL="https://vtx-web-${PROJECT_NUMBER}.${REGION}.run.app"

log "Deploying vtx-worker (agent steps)"
# Ingest streams each source file to scratch, and Cloud Run's filesystem is in-memory: a 500 MB
# bundle costs 500 MB of RAM while it is parsed (the parser itself stays small). 4 GiB covers a few
# large bundles ingesting at once on one instance plus the bounded OCR batches.
g run deploy vtx-worker --image="${BACKEND_IMG}" "${RUN_FLAGS[@]}" \
  --service-account="${SA_WORKER}" --ingress=all \
  --cpu=2 --memory=4Gi --concurrency=8 --timeout=1800 --min-instances=0 --max-instances=10 \
  --set-env-vars="${COMMON_ENV},VTX_ROLE=worker,VTX_WORKER_URL=${WORKER_URL}"
# Cloud Tasks presents an OIDC token minted for vtx-worker; only that identity may invoke.
invoker vtx-worker "serviceAccount:${SA_WORKER}"

log "Deploying vtx-api"
g run deploy vtx-api --image="${BACKEND_IMG}" "${RUN_FLAGS[@]}" \
  --service-account="${SA_API}" --ingress=all \
  --cpu=1 --memory=1Gi --concurrency=40 --timeout=300 --min-instances=0 --max-instances=5 \
  --set-env-vars="${COMMON_ENV},VTX_ROLE=api,VTX_WORKER_URL=${WORKER_URL},VTX_SIGNING_SA_EMAIL=${SA_API}"
API_URL="$(url_of vtx-api)"
# The web BFF calls the API with its own ID token (audience = API_URL).
invoker vtx-api "serviceAccount:${SA_WEB}"

log "Deploying vtx-web"
WEB_FLAGS=(--region="${REGION}" --execution-environment=gen2 --cpu-boost)
if [[ "${WEB_ACCESS}" == "public" ]]; then WEB_FLAGS+=(--allow-unauthenticated); else WEB_FLAGS+=(--no-allow-unauthenticated); fi
g run deploy vtx-web --image="${WEB_IMG}" "${WEB_FLAGS[@]}" \
  --service-account="${SA_WEB}" --ingress=all \
  --cpu=1 --memory=512Mi --concurrency=80 --timeout=300 --min-instances=0 --max-instances=5 \
  --set-env-vars="BACKEND_URL=${API_URL}" || {
    echo "Web deploy failed. If it was the allUsers binding (domain-restricted sharing), re-run with WEB_ACCESS=private SKIP_BUILD=1 TAG=${TAG}." >&2
    exit 1
  }

# Browsers PUT files straight to GCS with V4 signed URLs, so the bucket must allow the web origin.
# Cloud Run serves the same service on two URLs; allow both, plus local development.
WEB_ORIGINS=("${WEB_URL}")
LEGACY_WEB_URL="$(url_of vtx-web)"
if [[ -n "${LEGACY_WEB_URL}" && "${LEGACY_WEB_URL}" != "${WEB_URL}" ]]; then WEB_ORIGINS+=("${LEGACY_WEB_URL}"); fi
log "Allowing browser uploads from ${WEB_ORIGINS[*]}"
# shellcheck source=cors.sh
source "$(dirname "${BASH_SOURCE[0]}")/cors.sh"
apply_upload_cors "${CASE_BUCKET}" "${WEB_ORIGINS[@]}" http://localhost:3000 http://127.0.0.1:3000

log "Deployed (${TAG})"
cat <<EOF
  Web     ${WEB_URL}   (${WEB_ACCESS})
  API     ${API_URL}   (private: vtx-web only)
  Worker  ${WORKER_URL}   (private: Cloud Tasks as vtx-worker only)
  Rollback: gcloud run services update-traffic <service> --region ${REGION} --to-revisions <rev>=100
EOF
