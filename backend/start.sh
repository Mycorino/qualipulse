#!/usr/bin/env bash
set -euo pipefail

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

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}"
