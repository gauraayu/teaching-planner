"""Operations Manager: timing records, delay rules, permissions and the final verification step."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core import clock
from app.models import ClassSession, Lecture, LectureProgress, LectureSchedule, TeachingPlan


@pytest.fixture()
def unrecorded(db):
    """A past, published class with a full slot and no timing record yet (DSA Section B, scheduled 11:15-12:15)."""
    def pick():
        return db.scalar(
            select(Lecture).join(LectureSchedule).join(TeachingPlan, Lecture.teaching_plan_id == TeachingPlan.id)
            .outerjoin(ClassSession, ClassSession.lecture_id == Lecture.id)
            .outerjoin(LectureProgress, LectureProgress.lecture_id == Lecture.id)
            .where(TeachingPlan.name.like("Data Structures%Section B"), LectureSchedule.planned_date < clock.today(),
                   ClassSession.id.is_(None), LectureProgress.id.is_(None))
            .order_by(LectureSchedule.planned_date))
    return pick


def test_om_login_and_permissions(client, tokens):
    me = client.get("/api/me", headers=tokens["OM"]).json()
    assert me["role"] == "OM"
    assert {"operations.record", "verify.om"} <= set(me["permissions"])
    assert "plans.manage" not in me["permissions"] and "verify.ch" not in me["permissions"]
    # OM cannot manage plans or act as a professor.
    assert client.post("/api/teaching-plans", json={}, headers=tokens["OM"]).status_code in (403, 422)
    assert client.get("/api/professor/dashboard", headers=tokens["OM"]).status_code == 403
    assert client.get("/api/imports/fields", headers=tokens["OM"]).status_code == 403


def test_only_om_can_record_timings(client, tokens, unrecorded):
    lec = unrecorded()
    for role in ("PROFESSOR", "CL_CH", "ADMIN"):
        r = client.post(f"/api/om/classes/{lec.id}/entry", json={"time": "10:00"}, headers=tokens[role])
        assert r.status_code == 403, role
    # Admin may read operations; professors and CL/CH may not.
    assert client.get("/api/om/dashboard", headers=tokens["ADMIN"]).status_code == 200
    assert client.get("/api/om/dashboard", headers=tokens["PROFESSOR"]).status_code == 403
    assert client.get("/api/om/records", headers=tokens["CL_CH"]).status_code == 403


def test_dashboard_metrics_are_consistent(client, tokens):
    d = client.get("/api/om/dashboard", headers=tokens["OM"]).json()
    m = d["metrics"]
    assert m["total"] == len(d["classes"])
    assert m["running"] + m["entry_due"] + m["yet_to_start"] + m["completed"] + m["not_recorded"] + m["exit_missing"] == m["total"]
    assert d["tolerance_minutes"] == 5
    for row in d["classes"]:
        assert set(row["verification"]["levels"]) == {"CL_CH", "OM"}
    # The seed leaves CL/CH-verified work waiting for the OM.
    assert m["awaiting_final_verification"] > 0


def test_entry_within_tolerance_is_on_time(client, tokens, unrecorded):
    lec = unrecorded()
    r = client.post(f"/api/om/classes/{lec.id}/entry", json={"time": "11:20"}, headers=tokens["OM"])
    assert r.status_code == 200, r.text
    row = r.json()
    assert row["entry_time"] == "11:20" and row["delay_minutes"] == 5
    assert row["timing_status"] == "ON_TIME" and row["delay_reason"] is None
    assert row["state"] == "EXIT_MISSING"  # entry on an earlier day with no exit is flagged, not shown as "in class"


def test_delayed_entry_needs_reason_then_exit_closes_the_class(client, tokens, unrecorded, db):
    lec = unrecorded()
    O = tokens["OM"]
    # Exit before entry is refused.
    r = client.post(f"/api/om/classes/{lec.id}/exit", json={"time": "12:15"}, headers=O)
    assert r.status_code == 422 and r.json()["error"]["code"] == "ENTRY_NOT_RECORDED"

    # 7 minutes late: the backend decides it is a delay and asks for the reason.
    r = client.post(f"/api/om/classes/{lec.id}/entry", json={"time": "11:22"}, headers=O)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "DELAY_REASON_REQUIRED" and err["details"] == {"delay_minutes": 7, "tolerance_minutes": 5}
    assert db.scalar(select(ClassSession.id).where(ClassSession.lecture_id == lec.id)) is None  # nothing was stored

    r = client.post(f"/api/om/classes/{lec.id}/entry", json={"time": "11:22", "delay_reason": "OTHER"}, headers=O)
    assert r.status_code == 422 and r.json()["error"]["code"] == "DELAY_REMARKS_REQUIRED"
    r = client.post(f"/api/om/classes/{lec.id}/entry", json={"time": "11:22", "delay_reason": "NOT_A_REASON"}, headers=O)
    assert r.status_code == 422

    r = client.post(f"/api/om/classes/{lec.id}/entry", json={"time": "11:22", "delay_reason": "PREVIOUS_CLASS_OVERRUN"}, headers=O)
    assert r.status_code == 200, r.text
    row = r.json()
    assert row["timing_status"] == "DELAYED" and row["delay_minutes"] == 7
    assert row["delay_reason_label"] == "Previous class overrun" and row["exit_time"] is None

    r = client.post(f"/api/om/classes/{lec.id}/exit", json={"time": "11:20"}, headers=O)
    assert r.status_code == 422 and r.json()["error"]["code"] == "EXIT_BEFORE_ENTRY"
    r = client.post(f"/api/om/classes/{lec.id}/exit", json={"time": "12:17"}, headers=O)
    assert r.status_code == 200
    row = r.json()
    assert row["exit_time"] == "12:17" and row["duration_minutes"] == 55 and row["state"] == "COMPLETED"

    # Once the exit is in, the entry time is frozen.
    r = client.post(f"/api/om/classes/{lec.id}/entry", json={"time": "10:00"}, headers=O)
    assert r.status_code == 409 and r.json()["error"]["code"] == "CLASS_CLOSED"

    # It shows up in the records and is audited.
    recs = client.get("/api/om/records", params={"timing": "DELAYED", "date_from": row["date"], "date_to": row["date"]}, headers=O).json()
    assert str(lec.id) in {x["lecture_id"] for x in recs["items"]}
    audit = client.get("/api/audit", params={"entity_type": "class_session"}, headers=tokens["ADMIN"]).json()["items"]
    assert {"operations.entry_recorded", "operations.exit_recorded"} <= {a["action"] for a in audit}


def test_future_class_and_future_time_rejected(client, tokens, db):
    O = tokens["OM"]
    future = db.scalar(select(Lecture).join(LectureSchedule).join(TeachingPlan, Lecture.teaching_plan_id == TeachingPlan.id)
                       .where(TeachingPlan.status == "PUBLISHED", LectureSchedule.planned_date > clock.today() + timedelta(days=1)))
    r = client.post(f"/api/om/classes/{future.id}/entry", json={"time": "10:00"}, headers=O)
    assert r.status_code == 422 and r.json()["error"]["code"] == "CLASS_IN_FUTURE"
    assert client.post(f"/api/om/classes/{future.id}/entry", json={"time": "25:00"}, headers=O).status_code == 422


def test_final_verified_timing_is_locked(client, tokens, db):
    lec_id = db.scalar(select(LectureProgress.lecture_id).join(ClassSession, ClassSession.lecture_id == LectureProgress.lecture_id)
                       .where(LectureProgress.submission_status == "FINAL_VERIFIED"))
    r = client.post(f"/api/om/classes/{lec_id}/exit", json={"time": "23:00"}, headers=tokens["OM"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "TIMING_LOCKED"


def test_om_queue_shows_timing_and_report_adds_up(client, tokens):
    O = tokens["OM"]
    items = client.get("/api/verifications/queue/pending", headers=O).json()["items"]
    assert items and all(x["level"] == "OM" for x in items)
    assert any(x["class_session"] for x in items) and any(x["class_session"] is None for x in items)
    detail = client.get(f"/api/verifications/{items[0]['id']}", headers=O).json()
    assert detail["can_act"] and detail["acting_level"] == "OM"

    rep = client.get("/api/om/reports/summary", params={"date_from": (clock.today() - timedelta(days=90)).isoformat()}, headers=O).json()
    s = rep["summary"]
    assert s["on_time"] + s["delayed"] == s["recorded"] > 0
    assert sum(r["count"] for r in rep["reasons"]) == s["delayed"]
    assert sum(d["recorded"] for d in rep["daily"]) == s["recorded"]
    assert sum(f["recorded"] for f in rep["faculty"]) == s["recorded"]
