#!/usr/bin/env bash
#
# Route the funnel-event log stream into BigQuery.
#
# NOT NEEDED AT CURRENT SCALE, and intentionally not run yet. The
# retention problem it solves (Cloud Logging drops these lines after 30
# days) is already solved for the marketing funnel by the `web_events`
# table, which Postgres keeps forever and the admin Traffic tab reads.
#
# Reach for this when either becomes true:
#   * event volume makes web_events uncomfortable in the app database, or
#   * you want to join funnel events against something else in a
#     warehouse rather than through the admin API.
#
# Idempotent: safe to re-run. Creates the dataset, the sink, the IAM
# binding the sink's writer identity needs, and a parsed SQL view over
# the raw log table.
#
# Usage: ./deploy/setup-analytics-sink.sh [PROJECT_ID] [LOCATION]

set -euo pipefail

PROJECT="${1:-qualipulse-prod}"
LOCATION="${2:-europe-west1}"
DATASET="analytics"
SINK="analytics-events"
SERVICE="auto-interview-api"

# Only the funnel stream, not the whole application log. Keeps the table
# small, the queries cheap, and PII-bearing lines (client errors carry
# stack traces and URLs) out of the warehouse entirely.
FILTER="resource.type=\"cloud_run_revision\"
resource.labels.service_name=\"${SERVICE}\"
jsonPayload.message=~\"^analytics event=\""

echo "==> Project: ${PROJECT} | dataset: ${DATASET} (${LOCATION})"

# 1. Dataset ----------------------------------------------------------
if bq --project_id="${PROJECT}" show --dataset "${DATASET}" >/dev/null 2>&1; then
  echo "    dataset ${DATASET} already exists, leaving it alone"
else
  bq --project_id="${PROJECT}" mk \
    --dataset \
    --location="${LOCATION}" \
    --description="Funnel + marketing-attribution events routed from Cloud Logging" \
    "${DATASET}"
  echo "    created dataset ${DATASET}"
fi

# 2. Sink -------------------------------------------------------------
# --use-partitioned-tables writes one date-partitioned table instead of a
# table per day, so queries can prune by partition instead of scanning
# every shard.
if gcloud logging sinks describe "${SINK}" --project="${PROJECT}" >/dev/null 2>&1; then
  echo "    sink ${SINK} already exists, updating its filter"
  gcloud logging sinks update "${SINK}" \
    --project="${PROJECT}" \
    --log-filter="${FILTER}" >/dev/null
else
  gcloud logging sinks create "${SINK}" \
    "bigquery.googleapis.com/projects/${PROJECT}/datasets/${DATASET}" \
    --project="${PROJECT}" \
    --log-filter="${FILTER}" \
    --use-partitioned-tables >/dev/null
  echo "    created sink ${SINK}"
fi

# 3. IAM --------------------------------------------------------------
# The sink writes as its own service identity, which has no access to the
# dataset until granted. Skipping this is the classic silent failure: the
# sink reports healthy and not a single row ever lands.
WRITER=$(gcloud logging sinks describe "${SINK}" \
  --project="${PROJECT}" --format='value(writerIdentity)')
echo "    writer identity: ${WRITER}"

gcloud projects add-iam-policy-binding "${PROJECT}" \
  --member="${WRITER}" \
  --role="roles/bigquery.dataEditor" \
  --condition=None >/dev/null
echo "    granted roles/bigquery.dataEditor"

# 4. Parsed view ------------------------------------------------------
# The raw table holds the log line as one string. This view pulls it apart
# into columns so the warehouse is actually queryable. Values containing a
# space or "=" are quoted by _fmt in analytics.py, hence the COALESCE of a
# quoted and an unquoted extraction for every field.
TABLE="run_googleapis_com_stdout"

if bq --project_id="${PROJECT}" show "${DATASET}.${TABLE}" >/dev/null 2>&1; then
  bq --project_id="${PROJECT}" query --use_legacy_sql=false --quiet <<SQL
CREATE OR REPLACE VIEW \`${PROJECT}.${DATASET}.events\` AS
WITH raw AS (
  SELECT timestamp, jsonPayload.message AS msg
  FROM \`${PROJECT}.${DATASET}.${TABLE}\`
  WHERE STARTS_WITH(jsonPayload.message, 'analytics event=')
)
SELECT
  timestamp,
  COALESCE(REGEXP_EXTRACT(msg, r'\bevent="([^"]*)"'),        REGEXP_EXTRACT(msg, r'\bevent=(\S+)'))        AS event,
  COALESCE(REGEXP_EXTRACT(msg, r'\bsource="([^"]*)"'),       REGEXP_EXTRACT(msg, r'\bsource=(\S+)'))       AS source,
  COALESCE(REGEXP_EXTRACT(msg, r'\bvisitor="([^"]*)"'),      REGEXP_EXTRACT(msg, r'\bvisitor=(\S+)'))      AS visitor,
  COALESCE(REGEXP_EXTRACT(msg, r'\bcompany_id="([^"]*)"'),   REGEXP_EXTRACT(msg, r'\bcompany_id=(\S+)'))   AS company_id,
  COALESCE(REGEXP_EXTRACT(msg, r'\bpath="([^"]*)"'),         REGEXP_EXTRACT(msg, r'\bpath=(\S+)'))         AS path,
  COALESCE(REGEXP_EXTRACT(msg, r'\blocation="([^"]*)"'),     REGEXP_EXTRACT(msg, r'\blocation=(\S+)'))     AS location,
  COALESCE(REGEXP_EXTRACT(msg, r'\breferrer="([^"]*)"'),     REGEXP_EXTRACT(msg, r'\breferrer=(\S+)'))     AS referrer,
  COALESCE(REGEXP_EXTRACT(msg, r'\butm_source="([^"]*)"'),   REGEXP_EXTRACT(msg, r'\butm_source=(\S+)'))   AS utm_source,
  COALESCE(REGEXP_EXTRACT(msg, r'\butm_medium="([^"]*)"'),   REGEXP_EXTRACT(msg, r'\butm_medium=(\S+)'))   AS utm_medium,
  COALESCE(REGEXP_EXTRACT(msg, r'\butm_campaign="([^"]*)"'), REGEXP_EXTRACT(msg, r'\butm_campaign=(\S+)')) AS utm_campaign,
  COALESCE(REGEXP_EXTRACT(msg, r'\bplan_id="([^"]*)"'),      REGEXP_EXTRACT(msg, r'\bplan_id=(\S+)'))      AS plan_id,
  COALESCE(REGEXP_EXTRACT(msg, r'\bmethod="([^"]*)"'),       REGEXP_EXTRACT(msg, r'\bmethod=(\S+)'))       AS method,
  COALESCE(REGEXP_EXTRACT(msg, r'\blang="([^"]*)"'),         REGEXP_EXTRACT(msg, r'\blang=(\S+)'))         AS lang,
  SAFE_CAST(REGEXP_EXTRACT(msg, r'\bdays_since_signup=(\d+)') AS INT64)                                    AS days_since_signup,
  msg AS raw_message
FROM raw
SQL
  echo "    created/refreshed view ${DATASET}.events"
else
  echo "    NOTE: ${DATASET}.${TABLE} does not exist yet."
  echo "    The log router creates it on the first matching log line."
  echo "    Deploy the analytics branch, hit the site, then re-run this"
  echo "    script to create the parsed view."
fi

echo "==> Done. Query it:"
echo "    bq query --use_legacy_sql=false 'SELECT event, COUNT(*) c FROM \`${PROJECT}.${DATASET}.events\` GROUP BY event ORDER BY c DESC'"
