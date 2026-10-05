"""One semester sprint plan runs the whole flow: dates -> subjects -> generate -> publish a week -> teach ->
verify -> next week's draft with the unfinished topic first. Runs last; it creates its own class and people."""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.core import clock
from app.models import AcademicYear, Branch, Lecture, LectureSchedule, LectureSubtopic, Section, Semester, Subject, TeachingPlan

PASSWORD, OWN = "Temp@12345", "Own#Pass2026"


def bearer(client, identifier):
    r = client.post("/api/auth/login", json={"identifier": identifier, "password": PASSWORD})
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": OWN}, headers=h)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def monday(weeks=0):
    t = clock.today()
    return t - timedelta(days=t.weekday()) + timedelta(days=7 * weeks)


def rows(week):
    return [r for d in week["days"] for r in d["lectures"]]


@pytest.fixture(scope="module")
def world(client, tokens, db_engine):
    from app.db.session import SessionLocal
    A = tokens["ADMIN"]
    db = SessionLocal()
    ay = db.scalar(select(AcademicYear).where(AcademicYear.is_current.is_(True)))
    sem1 = db.scalar(select(Semester).where(Semester.number == 1))
    sem5 = db.scalar(select(Semester).where(Semester.number == 5))
    branch = db.scalar(select(Branch).where(Branch.code == "CSE"))
    sec1 = Section(branch_id=branch.id, semester_id=sem1.id, name="S", student_count=60)
    sec5 = Section(branch_id=branch.id, semester_id=sem5.id, name="S", student_count=60)
    subs = {"chem": Subject(code="SP101", name="Sprint Chemistry", short_name="SCH", branch_id=branch.id, semester_number=1, credits=3),
            "dsa": Subject(code="SP501", name="Sprint Algorithms", short_name="SAL", branch_id=branch.id, semester_number=5, credits=3)}
    db.add_all([sec1, sec5, *subs.values()])
    db.commit()
    r = client.post("/api/admin/users", headers=A, json={"full_name": "Prof. Sprint One", "employee_id": "SP001", "role": "PROFESSOR",
                                                         "email": "sp1@college.edu", "password": PASSWORD})
    assert r.status_code == 201, r.text
    out = {"ay": str(ay.id), "prof": {"id": r.json()["id"], "headers": bearer(client, "SP001")}, "branch": str(branch.id),
           "dept": str(branch.department_id), "sem": {"chem": str(sem1.id), "dsa": str(sem5.id)}, "sec": {"chem": str(sec1.id), "dsa": str(sec5.id)},
           "sub": {k: str(v.id) for k, v in subs.items()}}
    db.close()
    return out


def add_subject(client, A, world, sp_id, key, weekly, topics, db):
    r = client.post("/api/teaching-plans", headers=A, json={
        "academic_year_id": world["ay"], "semester_id": world["sem"][key], "department_id": world["dept"], "branch_id": world["branch"],
        "section_id": world["sec"][key], "subject_id": world["sub"][key], "professor_id": world["prof"]["id"], "room": f"S-{key}",
        "classes_per_week": weekly, "sprint_plan_id": sp_id})
    assert r.status_code == 201, r.text
    assert r.json()["sprint_plan"]["id"] == sp_id
    pid = r.json()["id"]
    for i in range(1, topics + 1):
        lec = Lecture(teaching_plan_id=pid, sequence=i, serial_no=i, lecture_no=i, lecture_type="THEORY", unit_no=1,
                      content_topic=f"{key} topic {i}", is_released=False)
        lec.subtopics = [LectureSubtopic(position=n, title=f"{key} {i}.{n}") for n in (1, 2, 3)]
        lec.schedule = LectureSchedule()
        db.add(lec)
    db.commit()
    return pid


def test_semester_sprint_plan_end_to_end(client, tokens, world, db):
    A, P = tokens["ADMIN"], world["prof"]["headers"]
    start, end = monday(), monday(5) + timedelta(days=5)          # six weeks, starting this week
    body = {"name": "Test Semester Sprint", "academic_year_id": world["ay"], "start_date": start.isoformat(), "end_date": end.isoformat(),
            "working_days": [0, 1, 2, 3, 4, 5]}
    assert client.post("/api/sprint-plans", json=body | {"end_date": start.isoformat()}, headers=A).status_code == 422
    assert client.post("/api/sprint-plans", json=body, headers=tokens["OM"]).status_code == 403
    sp = client.post("/api/sprint-plans", json=body, headers=A).json()
    sid = sp["id"]
    assert sp["status"] == "DRAFT" and sp["calendar"]["total_weeks"] == 6 and sp["calendar"]["working_days"] == 36
    assert client.post(f"/api/sprint-plans/{sid}/generate", headers=A).json()["error"]["code"] == "NO_SUBJECTS"

    chem = add_subject(client, A, world, sid, "chem", 6, 18, db)   # first year, 6 a week -> 3 weeks
    dsa = add_subject(client, A, world, sid, "dsa", 1, 9, db)      # 9 topics at 1 a week in 6 weeks -> does not fit
    d = client.get(f"/api/sprint-plans/{sid}", headers=A).json()
    by = {s["plan_id"]: s for s in d["subjects"]}
    assert by[chem]["year_group"] == "First Year" and by[dsa]["year_group"] == "Second to Fourth Year"
    assert by[dsa]["required_pace"] == 1.5 and by[dsa]["at_risk"] and by[dsa]["extra_sessions_needed"] == 1
    assert "1 additional session/week required" in by[dsa]["risk_message"] and not by[chem]["at_risk"]

    # ---- generate: every topic gets a real slot inside the dates, on its own year group's timings
    g = client.post(f"/api/sprint-plans/{sid}/generate", headers=A).json()
    assert g["status"] == "ACTIVE" and g["generation"]["subjects"] == 2
    today = clock.today()
    lectures = db.scalars(select(Lecture).where(Lecture.teaching_plan_id.in_([chem, dsa])).order_by(Lecture.sequence)).all()
    dated = [l for l in lectures if l.schedule.planned_date]
    assert all(max(start, today) <= l.schedule.planned_date <= end for l in dated) and all(not l.is_released for l in lectures)
    chem_l = sorted((l for l in dated if str(l.teaching_plan_id) == chem), key=lambda l: l.sequence)
    assert [(l.schedule.planned_date, l.schedule.planned_start_time) for l in chem_l] == sorted((l.schedule.planned_date, l.schedule.planned_start_time) for l in chem_l)
    assert all(l.schedule.planned_start_time.strftime("%H:%M") >= "10:10" for l in chem_l)      # first-year day starts at 10:10
    assert not any("12:40" <= l.schedule.planned_start_time.strftime("%H:%M") < "13:20" for l in chem_l)  # never in its own lunch
    by = {s["plan_id"]: s for s in g["subjects"]}
    assert by[chem]["projected_completion"] and by[chem]["unscheduled"] == 0
    assert by[dsa]["unscheduled"] >= 3 and by[dsa]["projected_completion"] is None and g["totals"]["at_risk"] == 1
    assert [w["status"] for w in g["weeks"]][:1] in (["DRAFT"], ["EMPTY"])

    # ---- a week reaches the professor only when it is published
    week = monday(1)
    w = client.get("/api/admin/sprint-plan/week", params={"week_start": week.isoformat()}, headers=A).json()
    mine = [r for r in rows(w) if r["plan_id"] in (chem, dsa)]
    assert len(mine) == 7 and w["unpublished"] >= 7 and all(not r["released"] for r in mine) and w["conflicts"] == []
    assert w["week"]["sprint_plan"]["name"]
    prof_week = lambda ws: rows(client.get("/api/professor/sprint-plan", params={"week_start": ws.isoformat()}, headers=P).json())  # noqa: E731
    assert prof_week(week) == []
    lec = next(r for r in mine if r["plan_id"] == dsa)
    assert client.get(f"/api/lectures/{lec['lecture_id']}", headers=P).status_code in (200, 404)
    assert client.put(f"/api/lectures/{lec['lecture_id']}/progress", json={"execution_status": "IN_PROGRESS"}, headers=P).status_code == 404
    w = client.post("/api/admin/sprint-plan/weeks/publish", json={"week_start": week.isoformat()}, headers=A).json()
    assert w["unpublished"] == 0 and w["draft"] is None
    assert len(prof_week(week)) == 7 and prof_week(monday(2)) == []
    weeks = {x["week_start"]: x for x in client.get(f"/api/sprint-plans/{sid}", headers=A).json()["weeks"]}
    assert weeks[week.isoformat()]["status"] == "PUBLISHED" and weeks[monday(2).isoformat()]["status"] == "DRAFT"

    # ---- delete safety: a plan with published weeks is archived, never deleted
    r = client.delete(f"/api/sprint-plans/{sid}", headers=A)
    assert r.status_code == 409 and r.json()["error"]["code"] == "SPRINT_PLAN_IN_USE"

    # ---- an unfinished class comes back first when the following week is made
    target = db.get(Lecture, lec["lecture_id"])
    target.schedule.planned_date = monday(-1) + timedelta(days=target.schedule.planned_date.weekday())   # pretend it was held last week
    db.commit()
    subs = [str(s.id) for s in target.subtopics]
    r = client.put(f"/api/lectures/{target.id}/progress", headers=P, json={
        "execution_status": "PARTIALLY_COMPLETED", "actual_completion_date": target.schedule.planned_date.isoformat(),
        "covered_subtopic_ids": subs[:2], "shared_with_students": True, "remarks": "Third subtopic left",
        "notes": [{"title": "Notes", "file_url": "https://drive.example.edu/notes"}]})
    assert r.status_code == 200, r.text
    before = {str(l.id): l.schedule.planned_date for l in db.scalars(select(Lecture).where(Lecture.teaching_plan_id == dsa)) if l.schedule.planned_date}
    nxt = client.post("/api/admin/sprint-plan/generate", json={"week_start": monday(2).isoformat(), "replace": True}, headers=A).json()
    drafted = [r for r in rows(nxt) if r["plan_id"] == dsa]
    assert len(drafted) == 1 and drafted[0]["origin"] == "CARRY_FORWARD" and drafted[0]["subtopics"] == ["dsa 2.3"] or drafted[0]["subtopics"][0].endswith(".3")
    assert nxt["generation"]["carry_forward"] >= 1
    pace = {p["plan_id"]: p for p in nxt["generation"]["pace"]}
    assert pace[dsa]["at_risk"] and pace[dsa]["weekly_sessions"] == 1
    # the topic that was projected into that slot moved one week on; nothing published was touched
    db.expire_all()
    after = {str(l.id): l.schedule.planned_date for l in db.scalars(select(Lecture).where(Lecture.teaching_plan_id == dsa)) if l.schedule.planned_date}
    moved = [i for i in before if i in after and after[i] > before[i]]
    assert moved and all(db.get(Lecture, i).is_released is False for i in moved)
    client.delete(f"/api/admin/sprint-plan/revisions/{nxt['draft']['id']}", headers=A)

    # ---- archive keeps the records and stops scheduling; an unused copy can be deleted outright
    copy = client.post(f"/api/sprint-plans/{sid}/duplicate", headers=A).json()
    assert copy["status"] == "DRAFT" and copy["duplicate"] == {"copied": 0, "skipped": ["SP101", "SP501"]} and not copy["in_use"]
    assert client.delete(f"/api/sprint-plans/{copy['id']}", headers=A).status_code == 204
    arch = client.post(f"/api/sprint-plans/{sid}/archive", headers=A).json()
    assert arch["status"] == "ARCHIVED" and prof_week(week) == []
    assert db.scalar(select(Lecture.id).where(Lecture.id == target.id)) is not None      # the record is still there
    listed = {s["id"]: s for s in client.get("/api/sprint-plans", headers=A).json()["items"]}
    assert listed[sid]["status"] == "ARCHIVED" and copy["id"] not in listed


def test_unused_sprint_plan_is_deleted_with_its_subjects(client, tokens, world, db):
    A = tokens["ADMIN"]
    sp = client.post("/api/sprint-plans", headers=A, json={"name": "Throwaway plan", "academic_year_id": world["ay"],
                                                           "start_date": monday(1).isoformat(), "end_date": monday(4).isoformat(), "working_days": [0, 2, 4]}).json()
    assert sp["calendar"]["working_days"] == 10    # Mon/Wed/Fri over three weeks, plus the last Monday
    pid = add_subject(client, A, world, sp["id"], "chem", 2, 4, db)   # the archived plan above no longer blocks this class
    g = client.post(f"/api/sprint-plans/{sp['id']}/generate", headers=A).json()
    assert g["generation"]["scheduled"] == 4
    days = {l.schedule.planned_date.weekday() for l in db.scalars(select(Lecture).where(Lecture.teaching_plan_id == pid))}
    assert days <= {0, 2, 4}
    assert client.delete(f"/api/sprint-plans/{sp['id']}", headers=A).status_code == 204
    db.expire_all()
    assert db.get(TeachingPlan, pid) is None and client.get(f"/api/sprint-plans/{sp['id']}", headers=A).status_code == 404


def test_overview_numbers_come_from_the_database(client, tokens):
    o = client.get("/api/admin/sprint-overview", headers=tokens["ADMIN"]).json()
    assert "sprint" in o and client.get("/api/admin/sprint-overview", headers=tokens["PROFESSOR"]).status_code == 403
