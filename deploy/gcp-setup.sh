#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════════════════════
# Auto-Interview — GCP Infrastructure Setup
#
# Prerequisites:
#   1. Install gcloud CLI: https://cloud.google.com/sdk/docs/install
#   2. Run: gcloud auth login
#   3. Create a GCP project: gcloud projects create YOUR-PROJECT-ID
#   4. Enable billing on the project
#
# Usage:
#   ./deploy/gcp-setup.sh <project-id> <region>
#
# Example:
#   ./deploy/gcp-setup.sh qualipulse-prod europe-west1
# ═══════════════════════════════════════════════════════════════════════════════

PROJECT_ID="${1:?Usage: $0 <project-id> <region>}"
REGION="${2:-europe-west1}"

echo "╔═══════════════════════════════════════════════════════╗"
echo "║  Auto-Interview — GCP Setup                          ║"
echo "║  Project: ${PROJECT_ID}"
echo "║  Region:  ${REGION}"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""

# ── Set active project ─────────────────────────────────────────────────────────
gcloud config set project "${PROJECT_ID}"

# ── Enable required APIs ───────────────────────────────────────────────────────
echo "→ Enabling GCP APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  sqladmin.googleapis.com \
  --quiet

# ── Create Artifact Registry repository ────────────────────────────────────────
echo "→ Creating Artifact Registry..."
gcloud artifacts repositories create auto-interview \
  --repository-format=docker \
  --location="${REGION}" \
  --description="Auto-Interview container images" \
  --quiet 2>/dev/null || echo "  (already exists)"

# ── Create secrets in Secret Manager ───────────────────────────────────────────
echo ""
echo "→ Creating secrets in Secret Manager..."
echo "  You'll be prompted to enter values for each secret."
echo ""

create_secret() {
  local name="$1"
  local description="$2"

  if gcloud secrets describe "${name}" --quiet 2>/dev/null; then
    echo "  ✓ ${name} (already exists)"
    return
  fi

  echo "  Enter value for ${name} (${description}):"
  read -rs SECRET_VALUE
  echo ""

  echo -n "${SECRET_VALUE}" | gcloud secrets create "${name}" \
    --data-file=- \
    --replication-policy=automatic \
    --quiet

  echo "  ✓ ${name} created"
}

create_secret "secret-key" "JWT signing key (random 32+ chars)"
create_secret "database-url" "PostgreSQL connection string"
create_secret "anthropic-api-key" "Anthropic API key for Claude"
create_secret "openai-api-key" "OpenAI API key for Whisper + TTS"
create_secret "sendgrid-api-key" "SendGrid API key (or press Enter to skip)"

# ── Grant Cloud Run access to secrets ──────────────────────────────────────────
echo ""
echo "→ Granting Cloud Run access to secrets..."
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

for secret in secret-key database-url anthropic-api-key openai-api-key sendgrid-api-key; do
  gcloud secrets add-iam-policy-binding "${secret}" \
    --member="serviceAccount:${COMPUTE_SA}" \
    --role="roles/secretmanager.secretAccessor" \
    --quiet 2>/dev/null
done
echo "  ✓ Secrets accessible by Cloud Run"

# ── Grant Cloud Build permissions ──────────────────────────────────────────────
echo ""
echo "→ Granting Cloud Build deploy permissions..."
CLOUDBUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${CLOUDBUILD_SA}" \
  --role="roles/run.admin" \
  --quiet 2>/dev/null

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${CLOUDBUILD_SA}" \
  --role="roles/iam.serviceAccountUser" \
  --quiet 2>/dev/null

echo "  ✓ Cloud Build can deploy to Cloud Run"

# ── Set up Cloud Build trigger ─────────────────────────────────────────────────
echo ""
echo "→ Cloud Build trigger setup:"
echo "  Connect your GitHub repo in the GCP Console:"
echo "  https://console.cloud.google.com/cloud-build/triggers?project=${PROJECT_ID}"
echo ""
echo "  Trigger settings:"
echo "    Source:        GitHub → your-org/auto-interview"
echo "    Branch:        ^main$"
echo "    Config:        /cloudbuild.yaml"
echo "    Substitution:  _REGION = ${REGION}"

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo "╔═══════════════════════════════════════════════════════╗"
echo "║  Setup complete!                                     ║"
echo "╠═══════════════════════════════════════════════════════╣"
echo "║                                                      ║"
echo "║  Next steps:                                         ║"
echo "║  1. Set up a PostgreSQL database:                    ║"
echo "║     • Neon (neon.tech) — free, serverless            ║"
echo "║     • OR Cloud SQL (GCP Console)                     ║"
echo "║                                                      ║"
echo "║  2. Update the database-url secret:                  ║"
echo "║     echo 'postgresql://...' | \\                      ║"
echo "║       gcloud secrets versions add database-url \\     ║"
echo "║       --data-file=-                                  ║"
echo "║                                                      ║"
echo "║  3. Connect GitHub and create build trigger:         ║"
echo "║     https://console.cloud.google.com/cloud-build/    ║"
echo "║                                                      ║"
echo "║  4. Push to main → auto-deploys to Cloud Run         ║"
echo "║                                                      ║"
echo "║  5. Map custom domain:                               ║"
echo "║     gcloud run domain-mappings create \\              ║"
echo "║       --service=auto-interview-web \\                 ║"
echo "║       --domain=app.qualipulse.com \\                  ║"
echo "║       --region=${REGION}                              ║"
echo "║                                                      ║"
echo "╚═══════════════════════════════════════════════════════╝"
