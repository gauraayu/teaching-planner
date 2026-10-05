"""Timing templates, the master timetable and the weekly sprint plan built on it.

Runs last (zz): it publishes a timetable and plans weeks, which earlier test modules do not expect.
The classes used here are created for this module (their own section, subjects and professors).
"""
from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy import select

from app.core import clock
from app.core.config import get_settings
from app.models import (
    AcademicYear, Branch, Lecture, LectureProgress, LectureSchedule, LectureSubtopic, LectureSubtopicProgress, Section, Semester,
    Subject, TeachingPlan, User,
)

PASSWORD, OWN = "Temp@12345", "Own#Pass2026"


def bearer(client, identifier):
    r = client.post("/api/auth/login", json={"identifier": identifier, "password": PASSWORD})
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": OWN}, headers=h)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def monday(offset_weeks=0):
    t = clock.today()
    return t - timedelta(days=t.weekday()) + timedelta(days=7 * offset_weeks)


def rows(week):
    return [r for d in week["days"] for r in d["lectures"]]


def kinds(view):
    return sorted({c["kind"] for c in view["conflicts"]})


@pytest.fixture(scope="module")
def world(client, tokens, db_engine):
    """A first-year class and two senior classes of one section, taught by two new professors."""
    from app.db.session import SessionLocal
    A = tokens["ADMIN"]
    db = SessionLocal()
    ay = db.scalar(select(AcademicYear).where(AcademicYear.is_current.is_(True)))
    sem5 = db.scalar(select(Semester).where(Semester.number == 5))
    branch = db.scalar(select(Branch).where(Branch.code == "CSE"))
    sem1 = Semester(academic_year_id=ay.id, number=1, name="Semester I", start_date=sem5.start_date, end_date=sem5.end_date)
    db.add(sem1)
    db.flush()
    sec1 = Section(branch_id=branch.id, semester_id=sem1.id, name="T", student_count=60)
    sec5 = Section(branch_id=branch.id, semester_id=sem5.id, name="T", student_count=60)
    subjects = [Subject(code="TT101", name="Timetable Basics", short_name="TTB", branch_id=branch.id, semester_number=1, credits=3),
                Subject(code="TT501", name="Timetable Theory", short_name="TTT", branch_id=branch.id, semester_number=5, credits=3),
                Subject(code="TT502", name="Timetable Practice", short_name="TTP", branch_id=branch.id, semester_number=5, credits=3)]
    db.add_all([sec1, sec5, *subjects])
    db.commit()
    profs = []
    for n, name in enumerate(("Ankit Singh", "Vikram Kumar"), start=1):
        r = client.post("/api/admin/users", headers=A, json={"full_name": f"Prof. {name}", "employee_id": f"TT{n:03d}", "role": "PROFESSOR",
                                                             "email": f"tt{n}@college.edu", "password": PASSWORD})
        assert r.status_code == 201, r.text
        profs.append({"id": r.json()["id"], "headers": bearer(client, f"TT{n:03d}")})
    plans = {}
    spec = (("first", subjects[0], sem1, sec1, profs[0], 3, 0), ("theory", subjects[1], sem5, sec5, profs[1], 3, 0),
            ("practice", subjects[2], sem5, sec5, profs[0], 2, 1))
    for key, sub, sem, sec, prof, classes, labs in spec:
        r = client.post("/api/teaching-plans", headers=A, json={
            "academic_year_id": str(ay.id), "semester_id": str(sem.id), "department_id": str(branch.department_id), "branch_id": str(branch.id),
            "section_id": str(sec.id), "subject_id": str(sub.id), "professor_id": prof["id"], "room": f"T-{key}",
            "classes_per_week": classes, "labs_per_week": labs, "lab_room": "T-Lab" if labs else None})
        assert r.status_code == 201, r.text
        assert r.json()["classes_per_week"] == classes and r.json()["labs_per_week"] == labs
        plan = db.get(TeachingPlan, r.json()["id"])
        for i in range(1, 9):
            lec = Lecture(teaching_plan_id=plan.id, sequence=i, serial_no=i, lecture_no=i, lecture_type="THEORY", unit_no=1,
                          content_topic=f"{sub.short_name} topic {i}")
            lec.subtopics = [LectureSubtopic(position=1, title=f"{sub.short_name} {i}.1"), LectureSubtopic(position=2, title=f"{sub.short_name} {i}.2")]
            lec.schedule = LectureSchedule()
            db.add(lec)
        plan.status = "PUBLISHED"
        plans[key] = str(plan.id)
    for name, kind in (("T-first", "CLASSROOM"), ("T-theory", "CLASSROOM"), ("T-practice", "CLASSROOM"), ("T-Lab", "LAB")):
        assert client.post("/api/rooms", json={"name": name, "room_type": kind}, headers=A).status_code == 201
    db.commit()
    db.close()
    return {"plans": plans, "profs": profs}


def entry(plan_id, weekday, start, end, **over):
    return {"teaching_plan_id": plan_id, "weekday": weekday, "start_time": start, "end_time": end} | over


# ---------------------------------------------------------------- timing templates

def test_two_templates_each_with_its_own_lunch(client, tokens):
    items = {t["code"]: t for t in client.get("/api/timing-templates", headers=tokens["PROFESSOR"]).json()["items"]}
    first, senior = items["FIRST_YEAR"], items["SECOND_TO_FOURTH_YEAR"]
    assert first["semester_numbers"] == [1, 2] and senior["semester_numbers"] == [3, 4, 5, 6, 7, 8]
    lunch = lambda t: [(s["start"], s["end"]) for s in t["slots"] if s["slot_type"] == "LUNCH"]  # noqa: E731
    assert lunch(first) == [("12:40", "13:20")] and lunch(senior) == [("11:50", "12:30")]
    # Lecture numbers are local to a template: 10:10 is Lecture 1 for first year and Lecture 3 for the seniors.
    number_at = lambda t, start: next(s["lecture_number"] for s in t["slots"] if s["start"] == start)  # noqa: E731
    assert number_at(first, "10:10") == 1 and number_at(senior, "10:10") == 3
    assert [s["lecture_number"] for s in first["slots"] if s["is_teaching_slot"]] == [1, 2, 3, 4, 5, 6, 7]
    assert [s["lecture_number"] for s in senior["slots"] if s["is_teaching_slot"]] == [1, 2, 3, 4, 5, 6, 7, 8, 9]


def test_semester_mapping_is_configurable_but_a_semester_follows_one_template(client, tokens):
    A = tokens["ADMIN"]
    items = {t["code"]: t for t in client.get("/api/timing-templates", headers=A).json()["items"]}
    senior = items["SECOND_TO_FOURTH_YEAR"]
    body = {"name": senior["name"], "short_name": senior["short_name"], "description": senior["description"],
            "slots": [{"slot_type": s["slot_type"], "start_time": s["start"], "end_time": s["end"]} for s in senior["slots"]]}
    r = client.put(f"/api/timing-templates/{senior['id']}", json=body | {"semester_numbers": [1, 3, 4, 5, 6, 7, 8]}, headers=A)
    assert r.status_code == 409 and r.json()["error"]["code"] == "SEMESTER_ALREADY_MAPPED"
    r = client.put(f"/api/timing-templates/{senior['id']}", json=body | {"semester_numbers": [3, 4, 5, 6, 7, 8, 9]}, headers=A)
    assert r.status_code == 200 and r.json()["semester_numbers"] == [3, 4, 5, 6, 7, 8, 9]
    assert [s["lecture_number"] for s in r.json()["slots"] if s["is_teaching_slot"]] == list(range(1, 10))
    assert client.put(f"/api/timing-templates/{senior['id']}", json=body | {"semester_numbers": [3]}, headers=tokens["PROFESSOR"]).status_code == 403
    client.put(f"/api/timing-templates/{senior['id']}", json=body | {"semester_numbers": [3, 4, 5, 6, 7, 8]}, headers=A)


# ---------------------------------------------------------------- conflicts on real intervals

def test_lunch_blocks_only_its_own_year_group(client, tokens, world):
    A, p = tokens["ADMIN"], world["plans"]
    assert client.post("/api/timetable/entries", json=entry(p["first"], 0, "11:50", "12:40"), headers=A).status_code == 409  # no draft yet
    client.post("/api/timetable/draft", headers=A)
    # First year teaches 11:50-12:40, straight through the seniors' lunch. Seniors teach 12:30-13:20, through first year's lunch.
    v = client.post("/api/timetable/entries", json=entry(p["first"], 0, "11:50", "12:40"), headers=A).json()
    v = client.post("/api/timetable/entries", json=entry(p["theory"], 0, "12:30", "13:20"), headers=A).json()
    assert v["conflicts"] == [] and v["can_publish"] and len(v["entries"]) == 2
    assert {e["template"]: e["lecture_numbers"] for e in v["entries"]} == {"FIRST_YEAR": [3], "SECOND_TO_FOURTH_YEAR": [5]}
    # Each group is stopped by its own lunch.
    v = client.post("/api/timetable/entries", json=entry(p["theory"], 1, "11:00", "12:10"), headers=A).json()
    v = client.post("/api/timetable/entries", json=entry(p["first"], 2, "12:40", "13:20"), headers=A).json()
    lunch = [c for c in v["conflicts"] if c["kind"] == "LUNCH"]
    assert len(lunch) == 2 and kinds(v) == ["LUNCH"] and not v["can_publish"]
    assert any("Second to Fourth Year lunch (11:50–12:30)" in c["message"] for c in lunch)
    assert any("First Year lunch (12:40–13:20)" in c["message"] for c in lunch)
    r = client.post("/api/timetable/publish", json={}, headers=A)
    assert r.status_code == 409 and r.json()["error"]["code"] == "SCHEDULE_CONFLICT"
    for e in v["entries"]:
        if e["weekday"] in (1, 2):
            v = client.delete(f"/api/timetable/entries/{e['id']}", headers=A).json()
    assert v["conflicts"] == []


def test_professor_section_and_room_clashes_across_year_groups(client, tokens, world):
    A, p = tokens["ADMIN"], world["plans"]
    # Prof. Ankit Singh: first year 11:50-12:40 and a senior class 12:30-13:20 overlap by ten minutes.
    v = client.post("/api/timetable/entries", json=entry(p["practice"], 0, "12:30", "13:20", room="T-x"), headers=A).json()
    prof = next(c for c in v["conflicts"] if c["kind"] == "PROFESSOR")
    assert "Prof. Ankit Singh has overlapping classes" in prof["message"] and "Overlap: 12:30–12:40" in prof["message"]
    assert "First Year" in prof["message"] and "Second to Fourth Year" in prof["message"] and len(prof["keys"]) == 2
    # The same section (Sem V-T) is also in two classes at once: theory and practice both 12:30-13:20.
    assert "SECTION" in kinds(v)
    bad = next(e for e in v["entries"] if e["plan_id"] == p["practice"])
    v = client.put(f"/api/timetable/entries/{bad['id']}", json=entry(p["practice"], 3, "10:10", "11:00", room="T-first"), headers=A).json()
    assert v["conflicts"] == []
    # A room is one room for the whole institution: first year in T-first at 10:10 while the seniors are in it.
    v = client.post("/api/timetable/entries", json=entry(p["first"], 3, "10:10", "11:00", room="t-first"), headers=A).json()
    room = [c for c in v["conflicts"] if c["kind"] == "ROOM"]
    assert kinds(v) == ["PROFESSOR", "ROOM"] and "Room T-first is double-booked" in room[0]["message"]
    r = client.post("/api/timetable/entries", json=entry(p["first"], 3, "11:00", "10:10"), headers=A)
    assert r.status_code == 422
    assert client.delete("/api/timetable/draft", headers=A).json()["draft"] is None


# ---------------------------------------------------------------- generate, publish, role views

def shape(view):
    return sorted((e["plan_id"], e["weekday"], e["start"], e["end"], e["room"], e["class_type"]) for e in view["entries"])


def test_generate_is_deterministic_conflict_free_and_only_a_draft(client, tokens, world):
    A, p = tokens["ADMIN"], world["plans"]
    one = client.post("/api/timetable/generate", json={}, headers=A).json()
    two = client.post("/api/timetable/generate", json={}, headers=A).json()
    assert shape(one) == shape(two) and one["showing"] == "DRAFT" and one["published"] is None
    assert one["generation"]["unplaced"] == [] and one["generation"]["placed"] == 9 and one["conflicts"] == [] and one["can_publish"]
    per_plan = {key: [e for e in one["entries"] if e["plan_id"] == pid] for key, pid in p.items()}
    assert [len(per_plan[k]) for k in ("first", "theory", "practice")] == [3, 3, 3]
    lab = next(e for e in per_plan["practice"] if e["class_type"] == "LAB")
    assert lab["room"] == "T-Lab" and len(lab["lecture_numbers"]) == 2      # two consecutive periods, never across lunch
    assert all(e["start"] >= "10:10" for e in per_plan["first"])             # first year starts at 10:10
    assert all(not ("11:50" <= e["start"] < "12:30") for e in per_plan["theory"] + per_plan["practice"])
    # Nobody else sees a draft.
    for h in (world["profs"][0]["headers"], tokens["OM"], tokens["CL_CH"]):
        v = client.get("/api/timetable", params={"draft": True}, headers=h).json()
        assert v["entries"] == [] and v["draft"] is None and v["showing"] is None
    assert client.post("/api/timetable/generate", json={}, headers=tokens["OM"]).status_code == 403


def test_publish_versions_and_each_role_sees_its_part(client, tokens, world):
    A, p = tokens["ADMIN"], world["plans"]
    v = client.post("/api/timetable/publish", json={"note": "Term timetable"}, headers=A).json()
    assert v["published"]["version_number"] == 1 and v["draft"] is None and len(v["entries"]) == 9
    mine = client.get("/api/timetable", headers=world["profs"][0]["headers"]).json()
    assert {e["plan_id"] for e in mine["entries"]} == {p["first"], p["practice"]} and len(mine["entries"]) == 6
    assert mine["conflicts"] == [] and {t["code"] for t in mine["templates"]} == {"FIRST_YEAR", "SECOND_TO_FOURTH_YEAR"}
    assert len(client.get("/api/timetable", headers=tokens["OM"]).json()["entries"]) == 9   # the demo OM covers every class
    assert client.get("/api/timetable", headers=tokens["PROFESSOR"]).json()["entries"] == []  # not this professor's classes
    # Edit Schedule works on a copy; the published timetable changes only on Publish, and the old version is kept.
    d = client.post("/api/timetable/draft", headers=A).json()
    assert d["showing"] == "DRAFT" and shape(d) == shape(v)
    moved = next(e for e in d["entries"] if e["plan_id"] == p["theory"])
    client.put(f"/api/timetable/entries/{moved['id']}", json=entry(p["theory"], 4, "15:45", "16:30"), headers=A)
    assert shape(client.get("/api/timetable", headers=tokens["OM"]).json()) == shape(v)
    v2 = client.post("/api/timetable/publish", json={}, headers=A).json()
    assert v2["published"]["version_number"] == 2 and shape(v2) != shape(v)
    history = client.get("/api/timetable/history", headers=A).json()["items"]
    assert [h["status"] for h in history] == ["PUBLISHED", "ARCHIVED"] and history[1]["entry_count"] == 9


# ---------------------------------------------------------------- make weekly sprint plan

def test_make_weekly_sprint_plan_maps_topics_onto_timetable_slots(client, tokens, world, db):
    A, p = tokens["ADMIN"], world["plans"]
    week = monday(2)
    slots = [e for e in client.get("/api/timetable", headers=A).json()["entries"]]
    # An unfinished class from last week: its remaining subtopic must come first next time.
    plan = db.get(TeachingPlan, p["first"])
    old = db.scalar(select(Lecture).where(Lecture.teaching_plan_id == plan.id, Lecture.lecture_no == 1))
    old.schedule.planned_date, old.schedule.planned_start_time, old.schedule.planned_end_time = monday(-1), time(10, 10), time(11, 0)
    pr = LectureProgress(lecture_id=old.id, professor_id=plan.professor_id, execution_status="PARTIALLY_COMPLETED",
                         actual_completion_date=monday(-1), submission_status="DRAFT")
    pr.subtopic_progress = [LectureSubtopicProgress(subtopic_id=s.id, is_covered=s.position == 1) for s in old.subtopics]
    db.add(pr)
    db.commit()
    holiday = week + timedelta(days=next(e["weekday"] for e in slots if e["plan_id"] == p["theory"]))
    hid = client.post("/api/holidays", json={"date": holiday.isoformat(), "name": "Test Holiday"}, headers=A).json()["id"]
    on_holiday = sum(1 for e in slots if week + timedelta(days=e["weekday"]) == holiday)

    w = client.post("/api/admin/sprint-plan/generate", json={"week_start": week.isoformat()}, headers=A).json()
    g = w["generation"]
    assert w["draft"]["status"] == "DRAFT" and g["holiday_slots"] == on_holiday and g["carry_forward"] == 1
    mine = [r for r in rows(w) if r["plan_id"] in p.values()]
    assert len(mine) == 9 - on_holiday and all(r["date"] != holiday.isoformat() for r in mine) and w["conflicts"] == []
    # Every class sits exactly on a timetable slot of its own plan.
    grid = {(e["plan_id"], e["weekday"], e["start"], e["end"]) for e in slots}
    assert all((r["plan_id"], date.fromisoformat(r["date"]).weekday(), r["start"], r["end"]) in grid for r in mine)
    first = sorted((r for r in mine if r["plan_id"] == p["first"]), key=lambda r: (r["date"], r["start"]))
    assert first[0]["origin"] == "CARRY_FORWARD" and first[0]["subtopics"] == ["TTB 1.2"]            # remaining work first
    assert [r["topic"] for r in first[1:]] == ["TTB topic 2", "TTB topic 3"][:len(first) - 1]         # then the next pending topics
    theory = sorted((r for r in mine if r["plan_id"] == p["theory"]), key=lambda r: (r["date"], r["start"]))
    assert [r["lecture_no"] for r in theory] == list(range(1, len(theory) + 1))
    # A draft: the professor sees nothing of it.
    P1 = world["profs"][0]["headers"]
    assert rows(client.get("/api/professor/sprint-plan", params={"week_start": week.isoformat()}, headers=P1).json()) == []
    r = client.post("/api/admin/sprint-plan/generate", json={"week_start": week.isoformat()}, headers=A)
    assert r.status_code == 409 and r.json()["error"]["code"] == "DRAFT_HAS_CHANGES"
    again = client.post("/api/admin/sprint-plan/generate", json={"week_start": week.isoformat(), "replace": True}, headers=A).json()
    key = lambda week_: sorted((r["plan_id"], r["date"], r["start"], r["topic"]) for r in rows(week_))  # noqa: E731
    assert key(again) == key(w)

    # The admin can still adjust a planned class; a move into the group's own lunch or onto a holiday is refused.
    rid = again["draft"]["id"]
    target = theory[0]
    r = client.patch(f"/api/admin/sprint-plan/revisions/{rid}/lectures/{target['lecture_id']}", headers=A, json={
        "planned_start_time": "11:50", "planned_end_time": "12:30", "reason": "ROOM_CHANGE"})
    assert r.status_code == 200, r.text
    assert any(c["kind"] == "LUNCH" and c["level"] == "ERROR" for c in r.json()["conflicts"])
    assert client.post(f"/api/admin/sprint-plan/revisions/{rid}/publish", json={}, headers=A).json()["error"]["code"] == "SCHEDULE_CONFLICT"
    r = client.patch(f"/api/admin/sprint-plan/revisions/{rid}/lectures/{target['lecture_id']}", headers=A, json={
        "planned_date": holiday.isoformat(), "planned_start_time": target["start"], "planned_end_time": target["end"], "reason": "ROOM_CHANGE"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "HOLIDAY"
    r = client.patch(f"/api/admin/sprint-plan/revisions/{rid}/lectures/{target['lecture_id']}", headers=A, json={
        "planned_date": target["date"], "planned_start_time": target["start"], "planned_end_time": target["end"], "reason": "ROOM_CHANGE"})
    assert r.status_code == 200 and r.json()["conflicts"] == []

    r = client.post(f"/api/admin/sprint-plan/revisions/{rid}/publish", json={}, headers=A)
    assert r.status_code == 200, r.text
    seen = rows(client.get("/api/professor/sprint-plan", params={"week_start": week.isoformat()}, headers=P1).json())
    assert len(seen) == len([r for r in mine if r["plan_id"] in (p["first"], p["practice"])])
    assert seen[0]["topic"] and seen[0]["start"] and seen[0]["room"]
    # The following week continues with the next topics, and the holiday no longer applies.
    client.delete(f"/api/holidays/{hid}", headers=A)
    nxt = client.post("/api/admin/sprint-plan/generate", json={"week_start": (week + timedelta(days=7)).isoformat()}, headers=A).json()
    theory2 = sorted((r for r in rows(nxt) if r["plan_id"] == p["theory"]), key=lambda r: (r["date"], r["start"]))
    assert [r["lecture_no"] for r in theory2] == list(range(len(theory) + 1, len(theory) + 4))
    assert nxt["generation"]["carry_forward"] == 0


def test_sprint_plan_needs_a_published_timetable_and_stays_inside_the_semester(client, tokens):
    A = tokens["ADMIN"]
    r = client.post("/api/admin/sprint-plan/generate", json={"week_start": "2030-01-07"}, headers=A).json()
    assert rows(r) == [] and r["generation"]["slots"] == 0 and r["generation"]["outside_semester"] == 9
    client.delete(f"/api/admin/sprint-plan/revisions/{r['draft']['id']}", headers=A)
    assert client.post("/api/admin/sprint-plan/generate", json={"week_start": monday(-2).isoformat()}, headers=A).json()["error"]["code"] == "WEEK_OVER"


# ---------------------------------------------------------------- execution and OM additions

def test_clock_in_uses_server_time_and_professor_adds_a_recording_link(client, tokens, world):
    A, O, P1, p = tokens["ADMIN"], tokens["OM"], world["profs"][0]["headers"], world["plans"]
    today = clock.today()
    rid = client.post("/api/admin/sprint-plan/revisions", json={"week_start": monday().isoformat()}, headers=A).json()["draft"]["id"]
    r = client.post(f"/api/admin/sprint-plan/revisions/{rid}/lectures", headers=A, json={
        "teaching_plan_id": p["practice"], "content_topic": "Extra practice", "subtopics": ["Warm up"], "planned_date": today.isoformat(),
        "planned_start_time": "00:02", "planned_end_time": "00:32", "room": "T-practice", "reason": "ACADEMIC_REQUIREMENT"})
    assert r.status_code == 200, r.text
    assert client.post(f"/api/admin/sprint-plan/revisions/{rid}/publish", json={}, headers=A).status_code == 200
    week = client.get("/api/professor/sprint-plan", params={"week_start": monday().isoformat()}, headers=P1).json()
    lecture_id = next(r["lecture_id"] for r in rows(week) if r["topic"] == "Extra practice")

    reasons = {i["value"] for i in client.get("/api/om/delay-reasons", headers=O).json()["items"]}
    assert "PROFESSOR_ARRIVED_LATE" in reasons
    # Clock In sends no time at all: the server decides, and it sees that the class started long ago.
    r = client.post(f"/api/om/classes/{lecture_id}/entry", json={}, headers=O)
    assert r.status_code == 422 and r.json()["error"]["code"] == "DELAY_REASON_REQUIRED"
    before = datetime.now(get_settings().tz)
    r = client.post(f"/api/om/classes/{lecture_id}/entry", json={"delay_reason": "PROFESSOR_ARRIVED_LATE"}, headers=O)
    assert r.status_code == 200, r.text
    after = datetime.now(get_settings().tz)
    assert r.json()["entry_time"] in {before.strftime("%H:%M"), after.strftime("%H:%M")} and r.json()["timing_status"] == "DELAYED"
    assert r.json()["delay_reason_label"] == "Professor arrived late"
    assert client.post(f"/api/om/classes/{lecture_id}/entry", json={"delay_reason": "OTHER"}, headers=O).json()["error"]["code"] == "DELAY_REMARKS_REQUIRED"

    # The professor's own record: recording link and anything taught beyond the plan. OM fields are not accepted here.
    body = {"execution_status": "IN_PROGRESS", "recording_url": "https://meet.example.edu/rec/abc", "additional_topics": "Solved two exam questions"}
    r = client.put(f"/api/lectures/{lecture_id}/progress", json=body, headers=P1)
    assert r.status_code == 200, r.text
    ex = client.get(f"/api/lectures/{lecture_id}", headers=P1).json()["execution"]
    assert ex["recording_url"] == "https://meet.example.edu/rec/abc" and ex["additional_topics"] == "Solved two exam questions"
    assert client.put(f"/api/lectures/{lecture_id}/progress", json=body | {"recording_url": "not a link"}, headers=P1).status_code == 422
    assert client.put(f"/api/lectures/{lecture_id}/progress", json=body | {"entry_time": "09:00"}, headers=P1).status_code == 422
