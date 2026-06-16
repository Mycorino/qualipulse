from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

connect_args = {}
engine_kwargs: dict = {}

if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False
else:
    # Neon (and most serverless Postgres providers) aggressively close idle
    # connections. Without pool_pre_ping, SQLAlchemy will hand out dead
    # sockets from the pool and the next query fails with
    # `psycopg2.OperationalError: SSL connection has been closed unexpectedly`.
    # pool_pre_ping issues a cheap `SELECT 1` before each checkout and
    # transparently reconnects if the connection is dead.
    engine_kwargs["pool_pre_ping"] = True
    # Recycle connections older than 5 minutes to stay under Neon's idle
    # timeout window proactively rather than reactively.
    engine_kwargs["pool_recycle"] = 300

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    **engine_kwargs,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Session for background threads / daemon tasks.

    FastAPI's ``get_db`` only covers request scope; threads spawned with
    ``threading.Thread`` must manage their own session. This guarantees a
    rollback if the body raises (so a crash can't leave a half-open
    transaction) and always closes the connection back to the pool.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
