#!/usr/bin/env bash
set -euo pipefail

# Drift hotfix — idempotently add columns that prod is missing because
# an earlier create_all+stamp-head deploy bypassed migrations 0034 and
# 0035, and the migration graph between them is broken (mismatched
# revision id vs down_revision). Runs BEFORE alembic so the model
# layer can SELECT these columns even when alembic believes head is
# already applied. Safe to re-run.
python -c "
from sqlalchemy import inspect, text
from app.database import engine

ALTERS = [
    # 0034 — V4 paywall sticky flag + free-preview email timestamp
    ('companies', 'has_ever_paid',
     'ALTER TABLE companies ADD COLUMN IF NOT EXISTS has_ever_paid '
     'BOOLEAN NOT NULL DEFAULT FALSE'),
    ('companies', 'free_preview_full_email_sent_at',
     'ALTER TABLE companies ADD COLUMN IF NOT EXISTS '
     'free_preview_full_email_sent_at TIMESTAMP NULL'),
    # 0035 — copilot_conversations optimistic-concurrency version column
    ('copilot_conversations', 'version',
     'ALTER TABLE copilot_conversations ADD COLUMN IF NOT EXISTS '
     'version INTEGER NOT NULL DEFAULT 0'),
]

inspector = inspect(engine)
existing_tables = set(inspector.get_table_names())

with engine.begin() as conn:
    for table, column, sql in ALTERS:
        if table not in existing_tables:
            print(f'⏭  {table}.{column} — table not present yet, skipping')
            continue
        cols = {c['name'] for c in inspector.get_columns(table)}
        if column in cols:
            continue
        conn.execute(text(sql))
        print(f'✓ Added missing column {table}.{column}')

    # Backfill has_ever_paid for accounts that have ever billed. Idempotent
    # — re-running is a no-op once flags are set.
    if 'companies' in existing_tables:
        result = conn.execute(text(
            \"UPDATE companies SET has_ever_paid = TRUE \"
            \"WHERE has_ever_paid = FALSE \"
            \"AND subscription_status IN ('active', 'canceled', 'past_due')\"
        ))
        if result.rowcount:
            print(f'✓ Backfilled has_ever_paid for {result.rowcount} companies')
print('✓ Drift hotfix complete')
"

# Try running Alembic migrations.
# If they fail (e.g., fresh database without base tables), fall back to
# create_all() which builds all tables from SQLAlchemy models, then stamp
# the Alembic version so future migrations work correctly.

if alembic upgrade head 2>&1; then
  echo "✓ Alembic migrations applied successfully"
else
  echo "⚠ Alembic migrations failed — initialising schema via create_all()"
  python -c "
from app.database import Base, engine
import app.models  # register all models
Base.metadata.create_all(bind=engine)
print('✓ Tables created via create_all()')
"
  # Stamp the current Alembic head so future migrations know where we are
  alembic stamp head
  echo "✓ Alembic version stamped at head"
fi

# --proxy-headers makes uvicorn rewrite request.client from X-Forwarded-For,
# so SlowAPI rate limits key on the real client IP instead of the Cloud Run /
# nginx proxy IP (without it, every user shares one rate-limit bucket).
# Trusting "*" is safe on Cloud Run: only Google's front end can reach the
# container, so the header can't be spoofed by direct connections.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}" \
  --proxy-headers --forwarded-allow-ips "*"
