"""Weekly sprint revisions, carry-forward, the professor's live class and alerts."""
import base64
import uuid
from datetime import timedelta

from sqlalchemy import func, select

from app.core import clock
from app.core.security import issue_token
from app.models import AuditLog, Lecture, LectureSchedule, Notification, RoleModel, TeachingPlan, User

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def auth(user_id) -> dict:
    """A session for any seeded user (the token is bound to the account's current password)."""
    from app.db.session import SessionLocal
    with SessionLocal() as s:
        return {"Authorization": f"Bearer {issue_token(user_id, s.get(User, user_id).password_hash)[0]}"}


def next_monday():
    t = clock.today()
    return t - timedelta(days=t.weekday()) + timedelta(days=7)


def dsa_lectures(db, start):
    """Demo professor's DSA Section A lectures in the week starting `start`."""
    return list(db.scalars(select(Lecture).join(LectureSchedule).join(TeachingPlan, Lecture.teaching_plan_id == TeachingPlan.id)
                           .where(TeachingPlan.name.like("Data Structures%Section A"),
                                  LectureSchedule.planned_date.between(start, start + timedelta(days=6)))
                           .order_by(LectureSchedule.planned_date)))


def find(week, lecture_id):
    return next((r for d in week["days"] for r in d["lectures"] if r["lecture_id"] == str(lecture_id)), None)


def sprint_notes(db, user_id):
    return db.scalar(select(func.count(Notification.id)).where(Notification.user_id == user_id, Notification.kind == "sprint.updated"))


def test_draft_is_invisible_then_publish_creates_versions(client, tokens, db):
    A, P = tokens["ADMIN"], tokens["PROFESSOR"]
    week = next_monday()
    ws = week.isoformat()
    lec_a, lec_b, lec_c = dsa_lectures(db, week)[:3]
    prof_id = lec_a.teaching_plan.professor_id
    meera = db.scalar(select(User).where(User.full_name == "Dr. Meera Iyer"))

    before = client.get("/api/admin/sprint-plan/week", params={"week_start": ws}, headers=A).json()
    assert before["version"] == 1 and before["draft"] is None and find(before, lec_a.id)["revised"] is None
    original = find(before, lec_a.id)

    # Only an admin can run the meeting.
    assert client.post("/api/admin/sprint-plan/revisions", json={"week_start": ws}, headers=P).status_code == 403
    assert client.get("/api/admin/sprint-plan/week", headers=tokens["CL_CH"]).status_code == 403

    draft = client.post("/api/admin/sprint-plan/revisions", json={"week_start": ws, "meeting_notes": "Weekly sprint meeting"}, headers=A).json()
    rid = draft["draft"]["id"]
    # Starting again returns the same draft (one meeting per week).
    assert client.post("/api/admin/sprint-plan/revisions", json={"week_start": ws}, headers=A).json()["draft"]["id"] == rid

    url = f"/api/admin/sprint-plan/revisions/{rid}"
    r = client.patch(f"{url}/lectures/{lec_a.id}", json={"planned_start_time": "16:00", "planned_end_time": "17:00", "room": "A-305",
                                                         "reason": "OTHER"}, headers=A)
    assert r.status_code == 422 and r.json()["error"]["code"] == "REMARK_REQUIRED"
    r = client.patch(f"{url}/lectures/{lec_a.id}", json={"planned_start_time": "16:00", "planned_end_time": "15:00", "reason": "ROOM_CHANGE"}, headers=A)
    assert r.status_code == 422 and r.json()["error"]["code"] == "TIMES_ORDERED"
    r = client.patch(f"{url}/lectures/{lec_a.id}", json={"planned_start_time": "16:00", "planned_end_time": "17:00", "room": "A-305",
                                                         "reason": "ROOM_CHANGE"}, headers=A)
    assert r.status_code == 200, r.text
    row = find(r.json(), lec_a.id)
    assert row["start"] == "16:00" and row["room"] == "A-305" and row["draft"]["change_type"] == "UPDATE"
    assert row["draft"]["old"]["planned_start_time"] == original["start"]

    r = client.patch(f"{url}/lectures/{lec_b.id}", json={"professor_id": str(meera.id), "reason": "FACULTY_AVAILABILITY"}, headers=A)
    assert r.status_code == 200 and find(r.json(), lec_b.id)["professor"]["full_name"] == "Dr. Meera Iyer"

    # ---- nothing has reached the professor yet
    notes_before = sprint_notes(db, prof_id)
    mine = client.get("/api/professor/sprint-plan", params={"week_start": ws}, headers=P).json()
    assert find(mine, lec_a.id)["start"] == original["start"] and find(mine, lec_a.id)["room"] == original["room"]
    assert find(mine, lec_a.id)["revised"] is None and find(mine, lec_b.id) is not None and mine["version"] == 1
    assert client.get(f"/api/professor/sprint-plan/{rid}/changes", headers=P).status_code == 404  # drafts are never served

    review = client.get(f"{url}/changes", headers=A).json()
    assert len(review["changes"]) == 2 and {c["reason"] for c in review["changes"]} == {"ROOM_CHANGE", "FACULTY_AVAILABILITY"}

    r = client.post(f"{url}/publish", json={"meeting_notes": "Room and faculty adjustments"}, headers=A)
    assert r.status_code == 200, r.text
    assert r.json()["revision"]["revision_number"] == 2 and r.json()["revision"]["status"] == "PUBLISHED"

    # ---- now the professor's effective schedule is master plan + revision v2
    mine = client.get("/api/professor/sprint-plan", params={"week_start": ws}, headers=P).json()
    row = find(mine, lec_a.id)
    assert mine["version"] == 2 and row["start"] == "16:00" and row["room"] == "A-305"
    assert row["revised"]["revision_number"] == 2 and row["revised"]["old"]["room"] == original["room"]
    assert find(mine, lec_b.id) is None  # handed to the substitute
    theirs = client.get("/api/professor/sprint-plan", params={"week_start": ws}, headers=auth(meera.id)).json()
    assert find(theirs, lec_b.id) is not None
    # The substitute can open it; the original professor no longer can update it.
    assert client.get(f"/api/lectures/{lec_b.id}", headers=auth(meera.id)).status_code == 200
    assert client.put(f"/api/lectures/{lec_b.id}/progress", json={"execution_status": "IN_PROGRESS"}, headers=P).status_code == 403

    # One consolidated notification per affected professor.
    db.expire_all()
    assert sprint_notes(db, prof_id) == notes_before + 1 and sprint_notes(db, meera.id) == 1
    changes = client.get(f"/api/professor/sprint-plan/{rid}/changes", headers=P).json()
    assert len(changes["changes"]) == 2

    # A published revision is frozen.
    r = client.patch(f"{url}/lectures/{lec_a.id}", json={"room": "B-1", "reason": "ROOM_CHANGE"}, headers=A)
    assert r.status_code == 409 and r.json()["error"]["code"] == "REVISION_CLOSED"

    # ---- a second meeting for the same week -> v3; v2 and the master values stay on record
    rid2 = client.post("/api/admin/sprint-plan/revisions", json={"week_start": ws}, headers=A).json()["draft"]["id"]
    assert rid2 != rid
    r = client.post(f"/api/admin/sprint-plan/revisions/{rid2}/lectures/{lec_c.id}/cancel", json={"reason": "HOLIDAY_ADJUSTMENT"}, headers=A)
    assert r.status_code == 200
    assert find(client.get("/api/professor/sprint-plan", params={"week_start": ws}, headers=P).json(), lec_c.id) is not None
    assert client.post(f"/api/admin/sprint-plan/revisions/{rid2}/publish", json={}, headers=A).json()["revision"]["revision_number"] == 3
    assert find(client.get("/api/professor/sprint-plan", params={"week_start": ws}, headers=P).json(), lec_c.id) is None

    after = client.get("/api/admin/sprint-plan/week", params={"week_start": ws}, headers=A).json()
    assert after["version"] == 3 and find(after, lec_a.id)["master"]["planned_start_time"] == original["start"]
    hist = client.get("/api/admin/sprint-plan/history", headers=A).json()["items"]
    assert [h["revision_number"] for h in hist if h["week_start"] == ws] == [3, 2]

    db.expire_all()
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "sprint.lecture_changed", AuditLog.entity_id == lec_a.id))
    assert entry.old_values["room"] == original["room"] and entry.new_values["room"] == "A-305" and "v2" in entry.new_values["revision"]
    # Cancelled lectures stop counting in reports and cannot be recorded.
    assert client.put(f"/api/lectures/{lec_c.id}/progress", json={"execution_status": "IN_PROGRESS"}, headers=P).status_code == 409


def test_discard_and_locked_lectures(client, tokens, db):
    A = tokens["ADMIN"]
    week = next_monday() + timedelta(days=7)
    lec = dsa_lectures(db, week)[0]
    rid = client.post("/api/admin/sprint-plan/revisions", json={"week_start": week.isoformat()}, headers=A).json()["draft"]["id"]
    client.patch(f"/api/admin/sprint-plan/revisions/{rid}/lectures/{lec.id}", json={"room": "Z-9", "reason": "ROOM_CHANGE"}, headers=A)
    out = client.delete(f"/api/admin/sprint-plan/revisions/{rid}", headers=A).json()
    assert out["draft"] is None and find(out, lec.id)["room"] != "Z-9" and out["version"] == 1
    # A past week cannot be revised, and a delivered lecture cannot be edited.
    past = clock.today() - timedelta(days=21)
    r = client.post("/api/admin/sprint-plan/revisions", json={"week_start": past.isoformat()}, headers=A)
    assert r.status_code == 422 and r.json()["error"]["code"] == "WEEK_OVER"


def test_carry_forward_is_suggested_and_placed_by_admin(client, tokens, db):
    A, P = tokens["ADMIN"], tokens["PROFESSOR"]
    today = clock.today()
    ws = (today - timedelta(days=today.weekday())).isoformat()
    week = client.get("/api/admin/sprint-plan/week", params={"week_start": ws}, headers=A).json()
    partials = [c for c in week["carry_forward"] if c["kind"] == "PARTIAL" and c["remaining"] and c["professor"]["full_name"] == "Dr. Ananya Sharma"]
    assert len(partials) >= 2, "the seed leaves partially completed lectures"
    item, other = partials[0], partials[1]
    assert 0 < item["covered"] < item["total"] and len(item["remaining"]) == item["total"] - item["covered"]
    before_count = len(find_all(client.get("/api/professor/sprint-plan", params={"week_start": ws}, headers=P).json()))

    rid = client.post("/api/admin/sprint-plan/revisions", json={"week_start": ws}, headers=A).json()["draft"]["id"]
    body = {"teaching_plan_id": item["plan_id"], "content_topic": f"{item['topic']} (remaining)", "subtopics": item["remaining"],
            "planned_date": today.isoformat(), "planned_start_time": "17:00", "planned_end_time": "17:45",
            "reason": "PREVIOUS_TOPIC_INCOMPLETE", "carry_forward_lecture_id": item["lecture_id"]}
    r = client.post(f"/api/admin/sprint-plan/revisions/{rid}/lectures", json=body, headers=A)
    assert r.status_code == 200, r.text
    placed = next(c for c in r.json()["carry_forward"] if c["lecture_id"] == item["lecture_id"])
    assert placed["draft_item_id"]  # still listed, marked as placed in the draft
    assert client.post(f"/api/admin/sprint-plan/revisions/{rid}/lectures", json=body, headers=A).status_code == 409
    # Nothing was scheduled automatically: the professor's week is unchanged until the admin publishes.
    assert len(find_all(client.get("/api/professor/sprint-plan", params={"week_start": ws}, headers=P).json())) == before_count

    assert client.post(f"/api/admin/sprint-plan/revisions/{rid}/publish", json={}, headers=A).status_code == 200
    mine = client.get("/api/professor/sprint-plan", params={"week_start": ws}, headers=P).json()
    new = next(r for r in find_all(mine) if r["origin"] == "CARRY_FORWARD")
    assert new["subtopics"] == item["remaining"] and new["date"] == today.isoformat() and new["revised"]["change_type"] == "ADD"
    after = client.get("/api/admin/sprint-plan/week", params={"week_start": ws}, headers=A).json()
    assert item["lecture_id"] not in {c["lecture_id"] for c in after["carry_forward"]}

    # "Reschedule later" keeps it on the list; "Mark resolved" removes it.
    assert client.post(f"/api/admin/sprint-plan/carry-forward/{other['lecture_id']}", json={"status": "DEFERRED", "note": "After mid-term"}, headers=A).status_code == 200
    listed = client.get("/api/admin/sprint-plan/week", params={"week_start": ws}, headers=A).json()["carry_forward"]
    assert next(c for c in listed if c["lecture_id"] == other["lecture_id"])["status"] == "DEFERRED"
    client.post(f"/api/admin/sprint-plan/carry-forward/{other['lecture_id']}", json={"status": "RESOLVED"}, headers=A)
    listed = client.get("/api/admin/sprint-plan/week", params={"week_start": ws}, headers=A).json()["carry_forward"]
    assert other["lecture_id"] not in {c["lecture_id"] for c in listed}
    assert client.post(f"/api/admin/sprint-plan/carry-forward/{other['lecture_id']}", json={"status": "DEFERRED"}, headers=P).status_code == 403


def find_all(week):
    return [r for d in week["days"] for r in d["lectures"]]


def test_live_class_start_end_evidence_and_alerts(client, tokens, db):
    A, P, O = tokens["ADMIN"], tokens["PROFESSOR"], tokens["OM"]
    today = clock.today()
    ws = (today - timedelta(days=today.weekday())).isoformat()
    plan = db.scalar(select(TeachingPlan).where(TeachingPlan.name.like("Data Structures%Section A")))
    # The admin adds a class for today through a published sprint revision.
    rid = client.post("/api/admin/sprint-plan/revisions", json={"week_start": ws}, headers=A).json()["draft"]["id"]
    r = client.post(f"/api/admin/sprint-plan/revisions/{rid}/lectures", headers=A, json={
        "teaching_plan_id": str(plan.id), "content_topic": "Doubt clearing session", "subtopics": ["Recap", "Practice problems"],
        "planned_date": today.isoformat(), "planned_start_time": "00:01", "planned_end_time": "00:31", "room": "C-204",
        "reason": "ACADEMIC_REQUIREMENT"})
    assert r.status_code == 200, r.text
    client.post(f"/api/admin/sprint-plan/revisions/{rid}/publish", json={}, headers=A)
    lecture_id = next(r["lecture_id"] for r in find_all(client.get("/api/professor/sprint-plan", params={"week_start": ws}, headers=P).json())
                      if r["topic"] == "Doubt clearing session")

    # A class on another day cannot be started.
    future = next(l for wk in (14, 7, 0) for l in dsa_lectures(db, next_monday() + timedelta(days=wk)))  # any class on a later day
    r = client.post(f"/api/lectures/{future.id}/start", json={}, headers=P)
    assert r.status_code == 422 and r.json()["error"]["code"] == "NOT_TODAY"

    d = client.get(f"/api/lectures/{lecture_id}", headers=P).json()
    assert d["can_start"] and not d["can_end"] and d["execution"] is None
    assert client.post(f"/api/lectures/{lecture_id}/end", headers=P).status_code == 422  # not started
    assert client.post(f"/api/lectures/{lecture_id}/start", json={"checkin": "TIME"}, headers=tokens["CL_CH"]).status_code == 403
    d = client.post(f"/api/lectures/{lecture_id}/start", json={"checkin": "TIME"}, headers=P).json()
    assert d["execution"]["professor_started_at"] and d["execution"]["execution_status"] == "IN_PROGRESS" and d["can_end"] and not d["can_start"]
    assert client.post(f"/api/lectures/{lecture_id}/start", json={}, headers=P).status_code == 409

    # Optional evidence: real image accepted, anything else refused, other users refused.
    up = f"/api/lectures/{lecture_id}/evidence"
    r = client.post(up, files={"file": ("notes.png", b"this is not an image", "image/png")}, headers=P)
    assert r.status_code == 400 and r.json()["error"]["code"] == "UNSUPPORTED_FILE"
    assert client.post(up, files={"file": ("../../etc/passwd.png", PNG, "image/png")}, headers=tokens["CL_CH"]).status_code == 403
    r = client.post(up, files={"file": ("../../etc/passwd.png", PNG, "image/png")}, data={"caption": "Board after class"}, headers=P)
    assert r.status_code == 200, r.text
    ev = r.json()["execution"]["evidence"]
    assert len(ev) == 1 and ev[0]["caption"] == "Board after class" and ev[0]["content_type"] == "image/png"
    assert ev[0]["file_url"].startswith("/api/uploads/class-evidence/") and "passwd" not in ev[0]["file_url"]  # server-made key
    assert client.get(ev[0]["file_url"]).content == PNG

    d = client.post(f"/api/lectures/{lecture_id}/end", headers=P).json()
    assert d["execution"]["professor_ended_at"] and not d["can_end"]
    r = client.put(f"/api/lectures/{lecture_id}/progress", json={"execution_status": "NOT_CONDUCTED"}, headers=P)
    assert r.status_code == 422 and r.json()["error"]["code"] == "REMARKS_REQUIRED"
    d = client.delete(f"/api/lecture-evidence/{ev[0]['id']}", headers=P).json()
    assert d["execution"]["evidence"] == [] and client.get(ev[0]["file_url"]).status_code == 404

    # Today's feed drives the 5-minute alert for the professor and the OM; storing the alert is idempotent.
    feed = client.get("/api/schedule/today", headers=P).json()
    mine = next(c for c in feed["classes"] if c["lecture_id"] == lecture_id)
    assert feed["lead_minutes"] == 5 and feed["timezone"] == "Asia/Kolkata" and mine["started"] and mine["start"] == "00:01"
    om_feed = client.get("/api/schedule/today", headers=O).json()
    assert lecture_id in {c["lecture_id"] for c in om_feed["classes"]} and len(om_feed["classes"]) >= len(feed["classes"])
    assert client.get("/api/schedule/today", headers=A).json()["classes"] == []
    assert client.post(f"/api/schedule/alerts/{lecture_id}", headers=O).json() == {"created": True}
    assert client.post(f"/api/schedule/alerts/{lecture_id}", headers=O).json() == {"created": False}

    # OM's official times stay separate from the professor's start / end; an early exit needs a reason.
    r = client.post(f"/api/om/classes/{lecture_id}/entry", json={"time": "00:02"}, headers=O)
    assert r.status_code == 200 and r.json()["entry_time"] == "00:02" and r.json()["professor_started_at"] != "00:02"
    r = client.post(f"/api/om/classes/{lecture_id}/exit", json={"time": "00:10"}, headers=O)
    assert r.status_code == 422 and r.json()["error"]["code"] == "EARLY_EXIT_REASON_REQUIRED"
    assert r.json()["error"]["details"] == {"early_minutes": 21, "tolerance_minutes": 10}
    r = client.post(f"/api/om/classes/{lecture_id}/exit", json={"time": "00:10", "early_exit_reason": "Fire drill"}, headers=O)
    assert r.status_code == 200 and r.json()["early_exit_minutes"] == 21 and r.json()["early_exit_reason"] == "Fire drill"
    # Once the OM has recorded the class, a sprint meeting can no longer move it.
    rid = client.post("/api/admin/sprint-plan/revisions", json={"week_start": ws}, headers=A).json()["draft"]["id"]
    r = client.patch(f"/api/admin/sprint-plan/revisions/{rid}/lectures/{lecture_id}", json={"room": "X", "reason": "ROOM_CHANGE"}, headers=A)
    assert r.status_code == 409 and r.json()["error"]["code"] == "LECTURE_LOCKED"
    client.delete(f"/api/admin/sprint-plan/revisions/{rid}", headers=A)


def test_empty_states_for_a_professor_with_no_classes(client, db):
    role = db.scalar(select(RoleModel).where(RoleModel.code == "PROFESSOR"))
    user = User(email=f"new-{uuid.uuid4().hex[:6]}@institute.edu", full_name="Dr. New Joiner", role_id=role.id)
    db.add(user)
    db.commit()
    H = auth(user.id)
    dash = client.get("/api/professor/dashboard", headers=H).json()
    assert dash["counts"]["today"] == 0 and dash["counts"]["course_progress_pct"] == 0 and dash["counts"]["verified"] == 0
    assert dash["schedule_today"] == [] and dash["action_items"] == [] and dash["pipeline"] is None and dash["syllabus"] == []
    week = client.get("/api/professor/sprint-plan", headers=H).json()
    assert week["metrics"] == {"total": 0, "completed": 0, "delivered": 0, "today_open": 0, "upcoming": 0, "pending_action": 0, "verified": 0, "pace_pct": 0}
    assert all(d["lectures"] == [] for d in week["days"]) and len(week["days"]) == 6 and week["courses"] == []
    assert client.get("/api/professor/sprint-plan/history", headers=H).json()["items"] == []
    assert client.get("/api/schedule/today", headers=H).json()["classes"] == []


def test_dashboard_numbers_come_from_records(client, tokens):
    dash = client.get("/api/professor/dashboard", headers=tokens["PROFESSOR"]).json()
    c = dash["counts"]
    assert c["today"] == len(dash["schedule_today"]) and c["pending_updates"] == len(dash["action_items"])
    assert c["completed"] + c["partial"] <= c["total"] and c["verified"] <= c["completed"] + c["partial"]
    assert all(a["kind"] in {"CORRECTION", "PENDING_LOG", "MISSING_ASSET", "NOT_SUBMITTED"} for a in dash["action_items"])
    assert any(a["kind"] == "CORRECTION" for a in dash["action_items"])  # the seed leaves corrections open
    assert dash["pipeline"]["chain"] == ["CL_CH", "OM"]
    for course in dash["syllabus"]:
        assert sum(u["total"] for u in course["units"]) == course["total"]
