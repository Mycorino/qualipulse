#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════════════════════
# Manual deploy — build locally and push to Cloud Run
# Faster for first deploy or hotfixes. CI/CD via cloudbuild.yaml for production.
#
# Usage:
#   ./deploy/deploy.sh <project-id> [region]
#
# Example:
#   ./deploy/deploy.sh qualipulse-prod europe-west1
# ═══════════════════════════════════════════════════════════════════════════════

PROJECT_ID="${1:?Usage: $0 <project-id> [region]}"
REGION="${2:-europe-west1}"
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/auto-interview"
TAG=$(git rev-parse --short HEAD 2>/dev/null || echo "latest")

echo "Deploying commit ${TAG} to ${PROJECT_ID} (${REGION})"
echo ""

# ── Configure Docker for Artifact Registry ─────────────────────────────────────
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet 2>/dev/null

# ── Build and push backend ─────────────────────────────────────────────────────
echo "→ Building backend..."
docker build -t "${REGISTRY}/auto-interview-backend:${TAG}" ./backend
docker push "${REGISTRY}/auto-interview-backend:${TAG}"

# ── Build and push frontend ────────────────────────────────────────────────────
echo "→ Building frontend..."
docker build -t "${REGISTRY}/auto-interview-frontend:${TAG}" ./frontend
docker push "${REGISTRY}/auto-interview-frontend:${TAG}"

# ── Deploy backend ─────────────────────────────────────────────────────────────
echo "→ Deploying backend to Cloud Run..."
gcloud run deploy auto-interview-api \
  --image="${REGISTRY}/auto-interview-backend:${TAG}" \
  --region="${REGION}" \
  --platform=managed \
  --allow-unauthenticated \
  --port=8080 \
  --cpu=1 \
  --memory=1Gi \
  --min-instances=0 \
  --max-instances=15 \
  --timeout=300s \
  --concurrency=16 \
  --no-cpu-throttling \
  --cpu-boost \
  --set-secrets="SECRET_KEY=secret-key:latest,ANTHROPIC_API_KEY=anthropic-api-key:latest,OPENAI_API_KEY=openai-api-key:latest,DATABASE_URL=database-url:latest,SENDGRID_API_KEY=sendgrid-api-key:latest" \
  --set-env-vars="ENVIRONMENT=production,UPLOAD_DIR=/tmp/uploads,ALLOWED_ORIGINS=*" \
  --quiet

BACKEND_URL=$(gcloud run services describe auto-interview-api \
  --region="${REGION}" --format='value(status.url)')
BACKEND_HOST=$(echo "${BACKEND_URL}" | sed 's|https://||')

echo "  ✓ Backend: ${BACKEND_URL}"

# ── Deploy frontend ────────────────────────────────────────────────────────────
echo "→ Deploying frontend to Cloud Run..."
gcloud run deploy auto-interview-web \
  --image="${REGISTRY}/auto-interview-frontend:${TAG}" \
  --region="${REGION}" \
  --platform=managed \
  --allow-unauthenticated \
  --port=8080 \
  --cpu=1 \
  --memory=256Mi \
  --min-instances=0 \
  --max-instances=5 \
  --concurrency=200 \
  --set-env-vars="BACKEND_URL=${BACKEND_URL},BACKEND_HOST=${BACKEND_HOST}" \
  --quiet

FRONTEND_URL=$(gcloud run services describe auto-interview-web \
  --region="${REGION}" --format='value(status.url)')

echo ""
echo "╔═══════════════════════════════════════════════════════╗"
echo "║  Deploy complete!                                    ║"
echo "╠═══════════════════════════════════════════════════════╣"
echo "║  Backend:  ${BACKEND_URL}"
echo "║  Frontend: ${FRONTEND_URL}"
echo "╠═══════════════════════════════════════════════════════╣"
echo "║  Update ALLOWED_ORIGINS to lock down CORS:           ║"
echo "║  gcloud run services update auto-interview-api \\     ║"
echo "║    --set-env-vars=ALLOWED_ORIGINS=${FRONTEND_URL} \\  ║"
echo "║    --region=${REGION}                                 ║"
echo "╚═══════════════════════════════════════════════════════╝"
