#!/usr/bin/env bash
# ── Stripe Production Setup ─────────────────────────────────────────
# One-command setup: creates products, prices, webhook, GCP secrets,
# and updates Cloud Run with all Stripe env vars.
#
# Usage:
#   1. Go to https://dashboard.stripe.com/apikeys (toggle to LIVE mode)
#   2. Copy your Secret key (sk_live_...)
#   3. Run:
#      STRIPE_LIVE_KEY=sk_live_xxx ./deploy/stripe-prod-setup.sh
#
# Prerequisites: stripe CLI installed, gcloud authenticated to qualipulse-prod
set -euo pipefail

# ── Config ──────────────────────────────────────────────────────────
GCP_PROJECT="qualipulse-prod"
GCP_REGION="europe-west1"
SERVICE_NAME="auto-interview-api"
WEBHOOK_URL="https://api.qualipulse.com/billing/webhook"
CURRENCY="eur"

# ── Validate inputs ─────────────────────────────────────────────────
if [[ -z "${STRIPE_LIVE_KEY:-}" ]]; then
  echo "Missing STRIPE_LIVE_KEY"
  echo ""
  echo "Get it from: https://dashboard.stripe.com/apikeys (switch to Live mode)"
  echo "Then run:    STRIPE_LIVE_KEY=sk_live_xxx $0"
  exit 1
fi

if [[ "$STRIPE_LIVE_KEY" != sk_live_* ]]; then
  echo "Key must start with sk_live_ (you passed a test key or invalid key)"
  exit 1
fi

echo "Stripe Production Setup"
echo "   Project:  $GCP_PROJECT"
echo "   Region:   $GCP_REGION"
echo "   Webhook:  $WEBHOOK_URL"
echo ""

# ── Helper: create product + prices ─────────────────────────────────
create_product_with_prices() {
  local name="$1" desc="$2"
  local monthly_cents="$3" annual_cents="$4"
  local monthly_var="$5" annual_var="$6"

  echo "  Creating product: $name"
  local prod_id
  prod_id=$(stripe products create \
    --api-key="$STRIPE_LIVE_KEY" \
    -d "name=$name" \
    -d "description=$desc" \
    2>&1 | grep '"id"' | head -1 | sed 's/.*"id": "//;s/".*//')

  if [[ -z "$prod_id" ]]; then
    echo "    Failed to create product $name"
    return 1
  fi
  echo "    Product: $prod_id"

  # Monthly price
  local monthly_price
  monthly_price=$(stripe prices create \
    --api-key="$STRIPE_LIVE_KEY" \
    -d "product=$prod_id" \
    -d "unit_amount=$monthly_cents" \
    -d "currency=$CURRENCY" \
    -d "recurring[interval]=month" \
    2>&1 | grep '"id"' | head -1 | sed 's/.*"id": "//;s/".*//')
  echo "    Monthly: $monthly_price ($((monthly_cents / 100))/mo)"
  eval "$monthly_var=$monthly_price"

  # Annual price
  local annual_price
  annual_price=$(stripe prices create \
    --api-key="$STRIPE_LIVE_KEY" \
    -d "product=$prod_id" \
    -d "unit_amount=$annual_cents" \
    -d "currency=$CURRENCY" \
    -d "recurring[interval]=year" \
    2>&1 | grep '"id"' | head -1 | sed 's/.*"id": "//;s/".*//')
  echo "    Annual:  $annual_price ($((annual_cents / 100))/yr)"
  eval "$annual_var=$annual_price"
}

create_one_time_product() {
  local name="$1" desc="$2" cents="$3" var="$4"

  echo "  Creating product: $name"
  local prod_id
  prod_id=$(stripe products create \
    --api-key="$STRIPE_LIVE_KEY" \
    -d "name=$name" \
    -d "description=$desc" \
    2>&1 | grep '"id"' | head -1 | sed 's/.*"id": "//;s/".*//')

  local price_id
  price_id=$(stripe prices create \
    --api-key="$STRIPE_LIVE_KEY" \
    -d "product=$prod_id" \
    -d "unit_amount=$cents" \
    -d "currency=$CURRENCY" \
    2>&1 | grep '"id"' | head -1 | sed 's/.*"id": "//;s/".*//')
  echo "    Price:   $price_id ($((cents / 100)))"
  eval "$var=$price_id"
}

# ── Step 1: Create products & prices ────────────────────────────────
echo "Step 1/4: Creating Stripe products & prices"
echo ""

create_product_with_prices \
  "Exploration" "For solo researchers running a few studies a month." \
  8900 89000 \
  PRICE_EXPLORATION_MONTHLY PRICE_EXPLORATION_ANNUAL

create_product_with_prices \
  "Team" "For research teams running studies in parallel." \
  29900 299000 \
  PRICE_TEAM_MONTHLY PRICE_TEAM_ANNUAL

create_product_with_prices \
  "Agency" "For agencies running research for multiple clients." \
  79900 799000 \
  PRICE_AGENCY_MONTHLY PRICE_AGENCY_ANNUAL

create_one_time_product \
  "Credit Pack - 25 credits" "Top-up: 25 interview credits." \
  15000 PRICE_PACK_25

create_one_time_product \
  "Credit Pack - 50 credits" "Top-up: 50 interview credits." \
  30000 PRICE_PACK_50

create_one_time_product \
  "Credit Pack - 100 credits" "Top-up: 100 interview credits." \
  50000 PRICE_PACK_100

echo ""
echo "All 9 prices created"
echo ""

# ── Step 2: Create webhook endpoint ─────────────────────────────────
echo "Step 2/4: Creating webhook endpoint"
echo ""

WEBHOOK_RESULT=$(stripe webhook_endpoints create \
  --api-key="$STRIPE_LIVE_KEY" \
  -d "url=$WEBHOOK_URL" \
  -d "enabled_events[]=customer.subscription.created" \
  -d "enabled_events[]=customer.subscription.updated" \
  -d "enabled_events[]=customer.subscription.deleted" \
  -d "enabled_events[]=invoice.payment_succeeded" \
  -d "enabled_events[]=checkout.session.completed" \
  2>&1)

WEBHOOK_SECRET=$(echo "$WEBHOOK_RESULT" | grep '"secret"' | head -1 | sed 's/.*"secret": "//;s/".*//')
WEBHOOK_ID=$(echo "$WEBHOOK_RESULT" | grep '"id"' | head -1 | sed 's/.*"id": "//;s/".*//')

if [[ -z "$WEBHOOK_SECRET" ]]; then
  echo "  Failed to create webhook endpoint"
  echo "  You may need to create it manually in the Stripe Dashboard:"
  echo "  URL: $WEBHOOK_URL"
  echo "  Events: customer.subscription.created, customer.subscription.updated,"
  echo "          customer.subscription.deleted, invoice.payment_succeeded,"
  echo "          checkout.session.completed"
  WEBHOOK_SECRET="MANUAL_SETUP_NEEDED"
else
  echo "  Webhook endpoint: $WEBHOOK_ID"
  echo "  Signing secret:   whsec_...${WEBHOOK_SECRET: -8}"
fi
echo ""

# ── Step 3: Create GCP secrets ──────────────────────────────────────
echo "Step 3/4: Creating GCP Secret Manager secrets"
echo ""

create_or_update_secret() {
  local name="$1" value="$2"
  if gcloud secrets describe "$name" --project="$GCP_PROJECT" &>/dev/null; then
    echo -n "$value" | gcloud secrets versions add "$name" \
      --data-file=- --project="$GCP_PROJECT" 2>/dev/null
    echo "  Updated: $name"
  else
    echo -n "$value" | gcloud secrets create "$name" \
      --data-file=- --project="$GCP_PROJECT" \
      --replication-policy=automatic 2>/dev/null
    echo "  Created: $name"
  fi
}

create_or_update_secret "stripe-secret-key" "$STRIPE_LIVE_KEY"
create_or_update_secret "stripe-webhook-secret" "$WEBHOOK_SECRET"

echo ""
echo "Secrets stored in Secret Manager"
echo ""

# ── Step 4: Update Cloud Run service ────────────────────────────────
echo "Step 4/4: Updating Cloud Run service"
echo ""

# Build the env vars string for price IDs (not secrets - plain env vars)
PRICE_ENV="STRIPE_PRICE_EXPLORATION_MONTHLY=${PRICE_EXPLORATION_MONTHLY}"
PRICE_ENV="${PRICE_ENV},STRIPE_PRICE_EXPLORATION_ANNUAL=${PRICE_EXPLORATION_ANNUAL}"
PRICE_ENV="${PRICE_ENV},STRIPE_PRICE_TEAM_MONTHLY=${PRICE_TEAM_MONTHLY}"
PRICE_ENV="${PRICE_ENV},STRIPE_PRICE_TEAM_ANNUAL=${PRICE_TEAM_ANNUAL}"
PRICE_ENV="${PRICE_ENV},STRIPE_PRICE_AGENCY_MONTHLY=${PRICE_AGENCY_MONTHLY}"
PRICE_ENV="${PRICE_ENV},STRIPE_PRICE_AGENCY_ANNUAL=${PRICE_AGENCY_ANNUAL}"
PRICE_ENV="${PRICE_ENV},STRIPE_PRICE_PACK_25=${PRICE_PACK_25}"
PRICE_ENV="${PRICE_ENV},STRIPE_PRICE_PACK_50=${PRICE_PACK_50}"
PRICE_ENV="${PRICE_ENV},STRIPE_PRICE_PACK_100=${PRICE_PACK_100}"
PRICE_ENV="${PRICE_ENV},STRIPE_PRICE_STARTER="
PRICE_ENV="${PRICE_ENV},STRIPE_PRICE_PRO="

# Update the service with secrets + env vars
gcloud run services update "$SERVICE_NAME" \
  --region="$GCP_REGION" \
  --project="$GCP_PROJECT" \
  --update-secrets="STRIPE_SECRET_KEY=stripe-secret-key:latest,STRIPE_WEBHOOK_SECRET=stripe-webhook-secret:latest" \
  --update-env-vars="$PRICE_ENV"

echo ""
echo "Cloud Run updated"
echo ""

# ── Summary ─────────────────────────────────────────────────────────
echo "=================================================="
echo "Stripe is live!"
echo "=================================================="
echo ""
echo "Products & Prices (live):"
echo "  Exploration Monthly: $PRICE_EXPLORATION_MONTHLY"
echo "  Exploration Annual:  $PRICE_EXPLORATION_ANNUAL"
echo "  Team Monthly:        $PRICE_TEAM_MONTHLY"
echo "  Team Annual:         $PRICE_TEAM_ANNUAL"
echo "  Agency Monthly:      $PRICE_AGENCY_MONTHLY"
echo "  Agency Annual:       $PRICE_AGENCY_ANNUAL"
echo "  Pack 25:             $PRICE_PACK_25"
echo "  Pack 50:             $PRICE_PACK_50"
echo "  Pack 100:            $PRICE_PACK_100"
echo ""
echo "Webhook: $WEBHOOK_URL ($WEBHOOK_ID)"
echo ""
echo "Secrets in GCP:"
echo "  stripe-secret-key      -> sk_live_...${STRIPE_LIVE_KEY: -8}"
echo "  stripe-webhook-secret  -> whsec_...${WEBHOOK_SECRET: -8}"
echo ""
echo "Cloud Run: $SERVICE_NAME updated with all Stripe config"
echo ""
echo "Next: push the requirements.txt change (stripe==11.4.1) to main"
echo "      to trigger a new deploy via Cloud Build."
