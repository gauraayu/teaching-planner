"""Database access.

MongoDB Atlas holds the data (see `mongo_store`). The application works on a private relational working copy
that is loaded from Atlas when the process starts and written through to Atlas on every commit.
"""
import atexit
import logging
import os
import tempfile
import time as _time
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401  (registers every entity on Base.metadata)
from app.core.config import get_settings
from app.db.base import Base
from app.db.mongo_store import store

log = logging.getLogger("app.db")
settings = get_settings()

_dir = Path(tempfile.gettempdir())
for stale in _dir.glob("teaching-portal-work-*.sqlite*"):  # working copies of processes that are gone
    try:
        stale.unlink()
    except OSError:
        pass  # still in use by another running process
WORK_FILE = _dir / f"teaching-portal-work-{os.getpid()}.sqlite"

engine = create_engine(f"sqlite+pysqlite:///{WORK_FILE.as_posix()}", connect_args={"check_same_thread": False, "timeout": 60})


@event.listens_for(engine, "connect")
def _on_connect(dbapi_connection, _record):
    cur = dbapi_connection.cursor()
    cur.execute("PRAGMA journal_mode=WAL")     # readers never wait for the writer
    cur.execute("PRAGMA synchronous=OFF")      # the working copy is disposable; Atlas is the durable store
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=60000")   # a second writer waits for the first instead of failing
    cur.close()


def _build() -> None:
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        # Change log filled by triggers, so nothing is missed: ORM writes, bulk statements and cascaded deletes alike.
        conn.execute(text("CREATE TABLE IF NOT EXISTS _changes (seq INTEGER PRIMARY KEY AUTOINCREMENT, tbl TEXT NOT NULL, id TEXT NOT NULL, op TEXT NOT NULL)"))
        for t in Base.metadata.sorted_tables:
            n = t.name
            conn.execute(text(f"CREATE TRIGGER IF NOT EXISTS _ch_i_{n} AFTER INSERT ON {n} BEGIN INSERT INTO _changes(tbl, id, op) VALUES ('{n}', NEW.id, 'U'); END"))
            conn.execute(text(f"CREATE TRIGGER IF NOT EXISTS _ch_u_{n} AFTER UPDATE ON {n} BEGIN INSERT INTO _changes(tbl, id, op) VALUES ('{n}', NEW.id, 'U'); END"))
            conn.execute(text(f"CREATE TRIGGER IF NOT EXISTS _ch_d_{n} AFTER DELETE ON {n} BEGIN INSERT INTO _changes(tbl, id, op) VALUES ('{n}', OLD.id, 'D'); END"))


def _start() -> None:
    if not settings.mongodb_uri:
        raise SystemExit("MONGODB_URI is not set. Put your MongoDB Atlas connection string in backend/.env "
                         "(see .env.example), e.g. MONGODB_URI=mongodb+srv://user:password@cluster0.xxxxx.mongodb.net/")
    _build()
    began = _time.monotonic()
    store.connect(settings.mongodb_uri, settings.mongodb_db)
    count = store.load(engine)
    engine.dispose()  # reopen connections with foreign keys on
    print(f"MongoDB: loaded {count} records from database '{settings.mongodb_db}' in {_time.monotonic() - began:.1f}s", flush=True)


def _cleanup() -> None:
    engine.dispose()
    for suffix in ("", "-wal", "-shm"):
        try:
            Path(str(WORK_FILE) + suffix).unlink()
        except OSError:
            pass


_start()
atexit.register(_cleanup)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(SessionLocal, "before_commit")
def _write_through(session: Session) -> None:
    """Atlas first, then the local commit. If Atlas refuses, the exception rolls the local transaction back."""
    session.flush()
    store.push(session.connection())


def get_db() -> Iterator[Session]:
    """Request-scoped session. Services commit explicitly; anything left open is rolled back."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
