"""MongoDB is the database: after everything the other test modules did (creates, edits, bulk deletes, cascades),
the documents must match the application's working copy exactly, and a fresh start must rebuild the same state."""
import uuid

from sqlalchemy import create_engine, func, select

from app.db.base import Base
from app.db.mongo_store import from_doc, store, to_doc


def test_every_collection_matches_the_working_copy(db_engine, db):
    total = 0
    for table in Base.metadata.sorted_tables:
        rows = {str(r["id"]): r for r in db.execute(select(table)).mappings()}
        docs = {d["_id"]: d for d in store.db[table.name].find({})}
        assert set(docs) == set(rows), f"{table.name}: {len(docs)} documents vs {len(rows)} records"
        for key, row in rows.items():
            assert docs[key] == to_doc(table, row), f"{table.name} {key} differs"
        total += len(rows)
    assert total > 500 and store.db["lectures"].count_documents({}) > 100
    # documents use natural MongoDB shapes
    plan = store.db["teaching_plans"].find_one({})
    assert isinstance(plan["_id"], str) and uuid.UUID(plan["_id"]) and isinstance(plan["subject_id"], str)
    sched = store.db["lecture_schedules"].find_one({"planned_date": {"$ne": None}})
    assert len(sched["planned_date"]) == 10 and sched["planned_start_time"].count(":") == 2
    scope = store.db["timing_templates"].find_one({"code": "FIRST_YEAR"})
    assert scope["semester_numbers"] == [1, 2]
    assert store.db["users"].find_one({"username": "admin.demo"})["created_at"].tzinfo is not None


def test_a_fresh_start_loads_the_same_data_back(db_engine, db, tmp_path):
    fresh = create_engine(f"sqlite+pysqlite:///{(tmp_path / 'copy.sqlite').as_posix()}")
    Base.metadata.create_all(fresh)
    with fresh.begin() as c:
        c.exec_driver_sql("CREATE TABLE _changes (seq INTEGER PRIMARY KEY AUTOINCREMENT, tbl TEXT, id TEXT, op TEXT)")
    loaded = store.load(fresh)
    with fresh.connect() as c:
        for table in Base.metadata.sorted_tables:
            mine = {r["id"]: dict(r) for r in db.execute(select(table)).mappings()}
            theirs = {r["id"]: dict(r) for r in c.execute(select(table)).mappings()}
            assert mine == theirs, table.name
    assert loaded == sum(db.scalar(select(func.count()).select_from(t)) for t in Base.metadata.sorted_tables)
    fresh.dispose()


def test_an_older_document_without_a_new_field_still_loads():
    table = Base.metadata.tables["teaching_plans"]
    doc = dict(store.db["teaching_plans"].find_one({}))
    for gone in ("classes_per_week", "labs_per_week", "lab_room", "sprint_plan_id"):
        doc.pop(gone)
    row = from_doc(table, doc)
    assert row["classes_per_week"] == 0 and row["labs_per_week"] == 0 and row["lab_room"] is None and row["sprint_plan_id"] is None


def test_nothing_is_saved_when_mongodb_cannot_be_reached(client, tokens, db, monkeypatch):
    before = store.db["rooms"].count_documents({})

    def down(*a, **k):
        raise ConnectionError("network is unreachable")

    monkeypatch.setattr(type(store.db["rooms"]), "replace_one", down)
    r = client.post("/api/rooms", json={"name": "Offline Room", "room_type": "CLASSROOM"}, headers=tokens["ADMIN"])
    assert r.status_code == 503 and r.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    monkeypatch.undo()
    names = [x["name"] for x in client.get("/api/rooms", headers=tokens["ADMIN"]).json()["items"]]
    assert "Offline Room" not in names and store.db["rooms"].count_documents({}) == before
    # and the same request works once the connection is back
    assert client.post("/api/rooms", json={"name": "Offline Room", "room_type": "CLASSROOM"}, headers=tokens["ADMIN"]).status_code == 201
    assert store.db["rooms"].find_one({"name": "Offline Room"}) is not None
    assert client.get("/api/health").json() == {"status": "ok", "database": "mongodb"}
