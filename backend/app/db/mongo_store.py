"""MongoDB Atlas is the database. Every record lives there, one collection per entity.

How the application uses it:

  * On start the whole database is read from Atlas into a local working copy (a private SQLite file in the
    temp folder). All the relational work the portal needs - joins across plan / lecture / progress /
    verification, uniqueness rules, clash checks - runs on that copy, so pages stay fast even though the
    database is in the cloud.
  * Every change is written to Atlas BEFORE it is committed locally: if Atlas cannot be reached the request
    fails and nothing is kept. There is no moment where the working copy holds something Atlas does not.
  * The working copy is thrown away when the process stops. Nothing is ever stored only on the server's disk.

Consequences worth knowing: run ONE backend process (the working copy is per process), and restart the backend
after changing data directly in Atlas or after running the seed script.

Document shape: `_id` is the record's UUID as a string, references are UUID strings, moments are BSON dates
(UTC), calendar dates are "YYYY-MM-DD", times "HH:MM:SS", lists and objects are native.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal

from sqlalchemy import Date, Numeric, Table, Time, Uuid, insert, select, text
from sqlalchemy.engine import Connection, Engine

from app.core.errors import AppError
from app.db.base import JSONB, Base, UTCDateTime

log = logging.getLogger("app.mongo")
CHUNK = 500


class StoreUnavailable(AppError):
    status_code = 503
    code = "DATABASE_UNAVAILABLE"


# ------------------------------------------------------------------ value conversion

def _to_bson(col, v):
    if v is None:
        return None
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, time):
        return v.strftime("%H:%M:%S")
    if isinstance(v, Decimal):
        return float(v)
    return v


def _from_bson(col, v):
    if v is None:
        return None
    t = col.type
    if isinstance(t, Uuid):
        return v if isinstance(v, uuid.UUID) else uuid.UUID(str(v))
    if isinstance(t, UTCDateTime):
        if isinstance(v, str):
            v = datetime.fromisoformat(v)
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(t, Date):
        return v if isinstance(v, date) and not isinstance(v, datetime) else date.fromisoformat(str(v)[:10])
    if isinstance(t, Time):
        return v if isinstance(v, time) else time.fromisoformat(str(v))
    if isinstance(t, Numeric):
        return Decimal(str(v))
    return v


def _missing(col):
    """Value for a field an older document does not have yet (the entity gained a field since it was written)."""
    d = col.default
    if d is not None:
        if d.is_scalar:
            return d.arg
        if d.is_callable:
            return d.arg(None)
    sd = getattr(col.server_default, "arg", None)
    if sd is not None and not col.nullable:
        s = str(sd).strip("'")
        if isinstance(col.type, JSONB):
            import json
            return json.loads(s)
        return {"true": True, "false": False}.get(s, int(s) if s.lstrip("-").isdigit() else s)
    return None


def to_doc(table: Table, row) -> dict:
    doc = {c.name: _to_bson(c, row[c.name]) for c in table.columns if c.name != "id"}
    doc["_id"] = str(row["id"])
    return doc


def from_doc(table: Table, doc: dict) -> dict:
    out = {}
    for c in table.columns:
        key = "_id" if c.name == "id" else c.name
        out[c.name] = _from_bson(c, doc[key]) if key in doc else _missing(c)
    return out


# ------------------------------------------------------------------ the store

class MongoStore:
    def __init__(self) -> None:
        self.db = None
        self.one_by_one = False  # the test stand-in has no bulk_write for current drivers
        self.deferred = False  # bulk mode (seed): changes are uploaded once at the end with push_all()

    @property
    def enabled(self) -> bool:
        return self.db is not None

    def connect(self, uri: str, name: str) -> None:
        if uri.startswith("mongomock://"):  # automated tests: an in-process stand-in for MongoDB
            import mongomock
            client = mongomock.MongoClient(tz_aware=True)
            self.one_by_one = True
        else:
            import certifi
            from pymongo import MongoClient
            kwargs = {"tz_aware": True, "serverSelectionTimeoutMS": 20000, "appname": "teaching-portal"}
            if uri.startswith("mongodb+srv://") or "tls=true" in uri.lower():
                kwargs["tlsCAFile"] = certifi.where()  # Windows / macOS Python often has no usable system CA store
            client = MongoClient(uri, **kwargs)
        self.db = client[name]
        try:
            self.db.command("ping")
        except Exception as e:  # noqa: BLE001
            raise SystemExit(
                "Cannot reach MongoDB. Check MONGODB_URI in backend/.env (username, password, cluster address), and in "
                f"Atlas → Network Access allow your IP address.\nDetails: {type(e).__name__}: {str(e)[:300]}") from None

    # ---- Atlas -> working copy (once, at start)
    def load(self, engine: Engine) -> int:
        total = 0
        raw = engine.raw_connection()
        try:
            raw.execute("PRAGMA foreign_keys=OFF")  # rows arrive collection by collection
            raw.commit()
        finally:
            raw.close()
        with engine.begin() as conn:
            for table in Base.metadata.sorted_tables:
                rows = [from_doc(table, d) for d in self.db[table.name].find({})]
                for i in range(0, len(rows), CHUNK):
                    conn.execute(insert(table), rows[i:i + CHUNK])
                total += len(rows)
            conn.execute(text("DELETE FROM _changes"))
        return total

    # ---- working copy -> Atlas (every commit)
    def push(self, conn: Connection) -> None:
        """Write this transaction's changes to Atlas. Called just before the local commit; raising here aborts it."""
        changes = conn.execute(text("SELECT tbl, id, op FROM _changes ORDER BY seq")).all()
        if not changes:
            return
        conn.execute(text("DELETE FROM _changes"))
        if self.deferred or not self.enabled:
            return
        last: dict[tuple[str, str], str] = {}
        for tbl, rid, op in changes:
            last[(tbl, rid)] = op
        tables = Base.metadata.tables
        try:
            for name in {t for t, _ in last}:
                table = tables[name]
                upserts = [uuid.UUID(r) for (t, r), op in last.items() if t == name and op == "U"]
                deletes = [str(uuid.UUID(r)) for (t, r), op in last.items() if t == name and op == "D"]
                docs = []
                for i in range(0, len(upserts), CHUNK):
                    docs += [to_doc(table, row) for row in conn.execute(select(table).where(table.c.id.in_(upserts[i:i + CHUNK]))).mappings()]
                coll = self.db[name]
                if self.one_by_one:
                    for d in docs:
                        coll.replace_one({"_id": d["_id"]}, d, upsert=True)
                    if deletes:
                        coll.delete_many({"_id": {"$in": deletes}})
                elif docs or deletes:
                    from pymongo import DeleteMany, ReplaceOne
                    ops = [ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in docs]
                    if deletes:
                        ops.append(DeleteMany({"_id": {"$in": deletes}}))
                    coll.bulk_write(ops, ordered=True)
        except Exception as e:  # noqa: BLE001
            log.error("MongoDB write failed: %s", e)
            raise StoreUnavailable("The database (MongoDB Atlas) could not be reached, so nothing was saved. "
                                   "Check the internet connection and try again.") from e

    def push_all(self, engine: Engine) -> int:
        """Replace every collection with the working copy. Used by the seed script after building the data locally."""
        total = 0
        with engine.connect() as conn:
            for table in Base.metadata.sorted_tables:
                docs = [to_doc(table, r) for r in conn.execute(select(table)).mappings()]
                coll = self.db[table.name]
                coll.delete_many({})
                for i in range(0, len(docs), CHUNK * 2):
                    coll.insert_many(docs[i:i + CHUNK * 2], ordered=False)
                total += len(docs)
        return total


store = MongoStore()
