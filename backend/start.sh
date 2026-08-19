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
    # 0061 — screener answer snapshot. The 2026-08-19 deploy rolled this
    # migration back: alembic_version.version_num was VARCHAR(32) and the
    # 34-char revision id '0061_participant_screening_answers' failed the
    # version-table UPDATE, so transactional DDL dropped the column again
    # and the create_all fallback stamped head without it.
    ('participants', 'screening_answers',
     # no IF NOT EXISTS: the column-presence check below already guards
     # re-runs, and plain ADD COLUMN also works on SQLite
     'ALTER TABLE participants ADD COLUMN screening_answers TEXT NULL'),
]

inspector = inspect(engine)
existing_tables = set(inspector.get_table_names())

is_postgres = engine.dialect.name == 'postgresql'

with engine.begin() as conn:
    # Widen alembic_version.version_num (default VARCHAR(32)) so long
    # revision ids can be recorded. Must run before alembic itself.
    if is_postgres and 'alembic_version' in existing_tables:
        length = conn.execute(text(
            \"SELECT character_maximum_length FROM information_schema.columns \"
            \"WHERE table_name = 'alembic_version' AND column_name = 'version_num'\"
        )).scalar()
        if length is not None and length < 255:
            conn.execute(text(
                'ALTER TABLE alembic_version '
                'ALTER COLUMN version_num TYPE VARCHAR(255)'
            ))
            print('✓ Widened alembic_version.version_num to VARCHAR(255)')

    # Repair the stamp left by the 2026-08-19 fallback: the DB was stamped
    # at one of the two parallel 0062 heads while create_all had already
    # built both 0062 tables. Re-point it at the 0063 merge revision so
    # 'alembic upgrade head' doesn't try to re-create existing tables.
    if 'alembic_version' in existing_tables and \
            'participant_email_log' in existing_tables and \
            'study_invites' in existing_tables:
        stale = conn.execute(text(
            \"SELECT version_num FROM alembic_version WHERE version_num IN \"
            \"('0062_participant_email_log', '0062_study_invites')\"
        )).scalars().all()
        if stale:
            conn.execute(text(
                \"DELETE FROM alembic_version WHERE version_num IN \"
                \"('0062_participant_email_log', '0062_study_invites')\"
            ))
            existing = conn.execute(text(
                \"SELECT 1 FROM alembic_version \"
                \"WHERE version_num = '0063_merge_0062_heads'\"
            )).first()
            if existing is None:
                conn.execute(text(
                    \"INSERT INTO alembic_version (version_num) \"
                    \"VALUES ('0063_merge_0062_heads')\"
                ))
            print(f'✓ Re-stamped alembic_version {stale} -> 0063_merge_0062_heads')

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
