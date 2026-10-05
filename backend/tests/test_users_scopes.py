"""Accounts, scopes and allocation: admin-created users sign in, see only what their role and scope allow,
and a lecture follows the professor it is allocated to."""
from datetime import timedelta

from sqlalchemy import select

from app.core import clock
from app.models import AuditLog, Lecture, LectureSchedule, Section, Subject, TeachingPlan, User, Verification

PASSWORD = "Temp@12345"


def login(client, identifier, password=PASSWORD):
    return client.post("/api/auth/login", json={"identifier": identifier, "password": password})


OWN = "Own#Pass2026"


def bearer(client, identifier, password=PASSWORD):
    """Sign in a freshly created account and replace its temporary password, as the person would."""
    r = login(client, identifier, password)
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    if r.json()["must_change_password"]:
        r = client.post("/api/auth/change-password", json={"current_password": password, "new_password": OWN}, headers=h)
        assert r.status_code == 200, r.text
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    return h


def make_user(client, tokens, **over):
    n = make_user.n = getattr(make_user, "n", 0) + 1
    body = {"full_name": f"Test User {n}", "employee_id": f"T{n:04d}", "email": f"test{n}@college.edu", "role": "PROFESSOR",
            "password": PASSWORD} | over
    r = client.post("/api/admin/users", json=body, headers=tokens["ADMIN"])
    assert r.status_code == 201, r.text
    return r.json()


def dsa_plan(db):
    return db.scalar(select(TeachingPlan).where(TeachingPlan.name.like("Data Structures%Section A")))


def future_lecture(db, plan, skip=0):
    """A lecture nobody has touched yet, comfortably in the future."""
    return db.scalars(select(Lecture).join(LectureSchedule).where(
        Lecture.teaching_plan_id == plan.id, LectureSchedule.planned_date > clock.today() + timedelta(days=2),
        Lecture.is_cancelled.is_(False), Lecture.professor_id.is_(None), ~Lecture.progress.has())
        .order_by(LectureSchedule.planned_date).offset(skip)).first()


# ---------------------------------------------------------------- sign-in

def test_sign_in_needs_a_real_account_and_password(client):
    assert client.post("/api/demo-login", json={"role": "ADMIN"}).status_code == 404  # the role-selection shortcut is gone
    r = login(client, "admin.demo", "wrong-password")
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert login(client, "nobody@nowhere.edu", "Demo@1234").json()["error"]["code"] == "INVALID_CREDENTIALS"
    # Email, username and employee ID all identify the same account; the role comes from the database.
    for ident in ("admin.demo", "ADMIN@demo.institute.edu", "adm-001"):
        r = login(client, ident, "Demo@1234")
        assert r.status_code == 200 and r.json()["role"] == "ADMIN", ident
    assert "password" not in str(r.json()).lower().replace("must_change_password", "")


def test_passwords_are_stored_only_as_hashes(client, tokens, db):
    make_user(client, tokens, email="hash.check@college.edu")
    u = db.scalar(select(User).where(User.email == "hash.check@college.edu"))
    assert u.password_hash.startswith("scrypt$") and PASSWORD not in u.password_hash
    logged = db.scalars(select(AuditLog).where(AuditLog.entity_id == u.id)).all()
    assert logged and all(PASSWORD not in str(a.new_values) + a.summary for a in logged)


def test_admin_creates_each_role_and_they_can_sign_in(client, tokens):
    homes = {"PROFESSOR": "tasks.read_own", "CL_CH": "verify.cl_ch", "OM": "operations.record"}
    for role, permission in homes.items():
        u = make_user(client, tokens, role=role)
        assert u["role"] == role and u["status"] == "ACTIVE" and u["must_change_password"] is True
        session = login(client, u["employee_id"]).json()
        assert session["role"] == role and permission in session["permissions"]
        assert session["must_change_password"] is True
        assert client.get("/api/admin/users", headers=bearer(client, u["email"])).status_code == 403
    # Only the administrator manages users; a second administrator can be created like any other account.
    body = {"full_name": "X Y", "employee_id": "ZZ1", "email": "zz1@college.edu", "role": "ADMIN", "password": PASSWORD}
    r = client.post("/api/admin/users", json=body, headers=tokens["ADMIN"])
    assert r.status_code == 201 and r.json()["role"] == "ADMIN"
    assert client.post("/api/admin/users", json=body, headers=tokens["OM"]).status_code == 403
    for role in ("PROFESSOR", "CL_CH", "OM"):
        assert client.get("/api/admin/users", headers=tokens[role]).status_code == 403
        assert client.post("/api/admin/users", json=body | {"role": "OM"}, headers=tokens[role]).status_code == 403


def test_duplicate_identity_and_weak_password_rejected(client, tokens):
    u = make_user(client, tokens)
    base = {"full_name": "Other Person", "role": "OM", "password": PASSWORD}
    r = client.post("/api/admin/users", json=base | {"employee_id": u["employee_id"].lower(), "email": "fresh@college.edu"}, headers=tokens["ADMIN"])
    assert r.status_code == 409 and "employee_id" in r.json()["error"]["details"]["fields"]
    r = client.post("/api/admin/users", json=base | {"employee_id": "FRESH1", "email": u["email"].upper()}, headers=tokens["ADMIN"])
    assert r.status_code == 409 and "email" in r.json()["error"]["details"]["fields"]
    r = client.post("/api/admin/users", json=base | {"employee_id": "FRESH2", "email": "f2@college.edu", "password": "short"}, headers=tokens["ADMIN"])
    assert r.status_code == 422


def test_change_password_and_admin_reset(client, tokens):
    u = make_user(client, tokens)
    h = {"Authorization": f"Bearer {login(client, u['email']).json()['access_token']}"}
    # On the temporary password nothing works except reading the session and changing the password.
    assert client.get("/api/me", headers=h).status_code == 200
    for path in ("/api/professor/dashboard", "/api/notifications", "/api/schedule/today"):
        r = client.get(path, headers=h)
        assert r.status_code == 403 and r.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED", path
    r = client.post("/api/auth/change-password", json={"current_password": "nope", "new_password": "Brand#New123"}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "WRONG_PASSWORD"
    r = client.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "Brand#New123"}, headers=h)
    assert r.status_code == 200 and r.json()["must_change_password"] is False
    fresh = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/professor/dashboard", headers=fresh).status_code == 200
    assert client.get("/api/me", headers=h).status_code == 401  # tokens issued for the old password are dead
    assert login(client, u["email"]).status_code == 401
    assert login(client, u["email"], "Brand#New123").status_code == 200
    # The admin sets a new temporary password: old sessions end and the user must change it again.
    r = client.post(f"/api/admin/users/{u['id']}/password", json={"password": "Reset@98765"}, headers=tokens["ADMIN"])
    assert r.status_code == 200 and r.json()["must_change_password"] is True
    assert client.get("/api/me", headers=fresh).status_code == 401
    assert login(client, u["email"], "Reset@98765").json()["must_change_password"] is True


def test_sign_in_throttle_is_per_account_not_per_identifier(client, tokens):
    u = make_user(client, tokens)
    for _ in range(8):
        assert login(client, u["employee_id"], "wrong-wrong").status_code == 401
    # Switching to the email does not give a guesser a fresh counter.
    r = login(client, u["email"], "wrong-wrong")
    assert r.status_code == 429 and r.json()["error"]["code"] == "TOO_MANY_ATTEMPTS"
    from app.services import user_service
    user_service._failures.clear()


def test_placeholder_secret_key_is_never_used_to_sign():
    from app.core import config
    key = config._signing_key("change-me-in-every-environment", False)
    assert key not in config.PLACEHOLDER_KEYS and len(key) >= 32
    assert config._signing_key("change-me-in-every-environment", False) == key  # stable across restarts
    import pytest
    with pytest.raises(RuntimeError):
        config._signing_key("generate-a-long-random-string", True)  # production refuses to start
    assert config._signing_key("x" * 40, True) == "x" * 40


def test_deactivated_user_is_locked_out_but_history_stays(client, tokens, db):
    u = make_user(client, tokens, role="OM")
    h = bearer(client, u["email"])
    assert client.get("/api/om/dashboard", headers=h).status_code == 200
    r = client.patch(f"/api/admin/users/{u['id']}", json={"is_active": False}, headers=tokens["ADMIN"])
    assert r.status_code == 200 and r.json()["status"] == "INACTIVE"
    assert client.get("/api/om/dashboard", headers=h).status_code == 401  # the existing session stops working at once
    assert login(client, u["email"], OWN).json()["error"]["code"] == "ACCOUNT_INACTIVE"
    assert db.get(User, u["id"]) is not None  # deactivated, never deleted
    actions = {a.action for a in db.scalars(select(AuditLog).where(AuditLog.entity_id == u["id"]))}
    assert {"user.created", "user.deactivated"} <= actions
    # An admin cannot lock themselves out.
    me = client.get("/api/me", headers=tokens["ADMIN"]).json()["user"]["id"]
    assert client.patch(f"/api/admin/users/{me}", json={"is_active": False}, headers=tokens["ADMIN"]).json()["error"]["code"] == "SELF_DEACTIVATE"


def test_role_change_blocked_once_the_account_has_history(client, tokens, db):
    fresh = make_user(client, tokens, role="OM")
    r = client.patch(f"/api/admin/users/{fresh['id']}", json={"role": "CL_CH"}, headers=tokens["ADMIN"])
    assert r.status_code == 200 and r.json()["role"] == "CL_CH"
    prof = dsa_plan(db).professor_id
    r = client.patch(f"/api/admin/users/{prof}", json={"role": "OM"}, headers=tokens["ADMIN"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "ROLE_CHANGE_BLOCKED"


def test_professor_dropdown_lists_only_active_professor_accounts(client, tokens, db):
    gone = make_user(client, tokens, is_active=False)
    dsa = db.scalar(select(Subject).where(Subject.code == "CS501"))
    other = db.scalar(select(Subject).where(Subject.code == "CS502"))
    picky = make_user(client, tokens, scope={"subject_ids": [str(other.id)]})
    items = client.get("/api/admin/users", params={"role": "PROFESSOR", "status": "ACTIVE"}, headers=tokens["ADMIN"]).json()["items"]
    assert items and all(u["role"] == "PROFESSOR" and u["is_active"] for u in items)
    assert gone["id"] not in {u["id"] for u in items} and picky["id"] in {u["id"] for u in items}
    # Subject eligibility narrows the list further where the admin has recorded it.
    eligible = client.get("/api/admin/users", params={"role": "PROFESSOR", "status": "ACTIVE", "subject_id": str(dsa.id)},
                          headers=tokens["ADMIN"]).json()["items"]
    assert picky["id"] not in {u["id"] for u in eligible}
    seeded = next(u for u in items if u["username"] == "professor.demo")
    assert seeded["workload"]["subjects"] >= 1 and "subject" in seeded["scope_label"]


# ---------------------------------------------------------------- allocation

def test_lecture_follows_the_professor_it_is_allocated_to(client, tokens, db):
    plan = dsa_plan(db)
    lec = future_lecture(db, plan)
    newcomer = make_user(client, tokens, full_name="Prof. New Comer")
    N, P = bearer(client, newcomer["email"]), tokens["PROFESSOR"]
    week = {"week_start": lec.schedule.planned_date.isoformat()}

    def sees(h):
        days = client.get("/api/professor/sprint-plan", params=week, headers=h).json()["days"]
        return str(lec.id) in {r["lecture_id"] for d in days for r in d["lectures"]}

    assert sees(P) and not sees(N)
    assert client.get(f"/api/lectures/{lec.id}", headers=N).status_code == 403
    # A professor_id sent by the client is never trusted - the schedule is always the signed-in professor's own.
    hacked = client.get("/api/professor/sprint-plan", params=week | {"professor_id": str(plan.professor_id)}, headers=N).json()
    assert all(not d["lectures"] for d in hacked["days"])

    r = client.patch(f"/api/lectures/{lec.id}", json={"reason": "Faculty availability", "professor_id": newcomer["id"]}, headers=tokens["ADMIN"])
    assert r.status_code == 200 and r.json()["professor"]["id"] == newcomer["id"]
    assert sees(N) and not sees(P)
    assert client.get(f"/api/lectures/{lec.id}", headers=P).status_code == 403
    assert client.get(f"/api/lectures/{lec.id}", headers=N).json()["professor"]["full_name"] == "Prof. New Comer"
    notes = client.get("/api/notifications", headers=N).json()["items"]
    assert any("assigned to you" in n["title"] for n in notes)
    # The plan's own professor no longer sees the reallocated lecture anywhere, including the course page.
    course = client.get(f"/api/professor/courses/{plan.id}", headers=P).json()
    assert str(lec.id) not in {l["id"] for l in course["lectures"]}
    # The lecture stores the account, not a name.
    db.expire_all()
    assert str(db.get(Lecture, lec.id).professor_id) == newcomer["id"]


def test_professor_cannot_be_put_in_two_classes_at_once(client, tokens, db):
    plan = dsa_plan(db)
    lec = future_lecture(db, plan, skip=1)
    sch = lec.schedule
    # Another published plan's lecture is moved on top of it for the same professor.
    other_plan = db.scalar(select(TeachingPlan).where(TeachingPlan.status == "PUBLISHED", TeachingPlan.professor_id != plan.professor_id))
    victim = future_lecture(db, other_plan)
    r = client.patch(f"/api/lectures/{victim.id}", headers=tokens["ADMIN"], json={
        "reason": "Trying a clash", "professor_id": str(plan.professor_id), "planned_date": sch.planned_date.isoformat(),
        "planned_start_time": sch.planned_start_time.strftime("%H:%M"), "planned_end_time": sch.planned_end_time.strftime("%H:%M")})
    assert r.status_code == 409 and r.json()["error"]["code"] == "SCHEDULE_CONFLICT"
    assert "overlapping class" in r.json()["error"]["message"]
    db.expire_all()
    assert db.get(Lecture, victim.id).professor_id is None  # nothing was saved


def test_import_maps_employee_ids_to_accounts_and_never_creates_them(client, tokens, db):
    from tests.test_api import ids, new_plan
    i = ids(db)
    cs502 = db.scalar(select(Subject.id).where(Subject.code == "CS502"))
    plan_id = new_plan(client, tokens, i, cs502, i["cse5b"], i["free_prof"])
    h = tokens["ADMIN"]
    meera = db.scalar(select(User).where(User.full_name == "Dr. Meera Iyer"))
    busy = db.get(User, i["prof"])
    taken = future_lecture(db, dsa_plan(db)).schedule  # a published class of the demo professor
    sid = client.post("/api/imports/session", json={"teaching_plan_id": plan_id}, headers=h).json()["id"]
    client.put(f"/api/imports/{sid}/mode", json={"import_mode": "FULL_TABLE"}, headers=h)
    sheet = ("Lecture_No\tContent_Topic\tScheduled_Date\tStart Time\tEnd Time\tRoom\tProfessor Employee ID\n"
             f"1\tProcesses\t06/11/2026\t07:00 AM\t08:00 AM\tC-310\t{meera.employee_code.lower()}\n"
             "2\tThreads\t13/11/2026\t07:00 AM\t08:00 AM\t\tGHOST-99\n"
             "3\tScheduling\t20/11/2026\t07:00 AM\t08:00 AM\t\t\n"
             f"4\tClashing lecture\t{taken.planned_date:%d/%m/%Y}\t{taken.planned_start_time:%H:%M}\t{taken.planned_end_time:%H:%M}"
             f"\t\t{busy.employee_code}\n")
    r = client.post(f"/api/imports/{sid}/full-table", json={"raw_text": sheet}, headers=h)
    assert r.status_code == 200, r.text
    before = db.scalar(select(User.id).where(User.employee_code == "GHOST-99"))
    v = client.post(f"/api/imports/{sid}/validate", json={}, headers=h).json()["preview"]
    rows = v["rows"]
    assert rows[0]["values"]["professor_name"] == "Dr. Meera Iyer" and rows[0]["values"]["room"] == "C-310"
    assert rows[1]["status"] == "ERROR" and "Professor not found" in rows[1]["issues"][0]["message"]
    assert rows[2]["values"]["professor_id"] is None and rows[2]["values"]["professor_name"] == "Dr. Kavita Rao"  # the plan's professor
    # Row 4 would put the demo professor in two published classes at the same time.
    assert rows[3]["status"] == "ERROR" and any("overlapping class" in x["message"] for x in rows[3]["issues"])
    assert not v["can_commit"]
    # "Map Professor": the admin points each row at a real, free account.
    client.put(f"/api/imports/{sid}/rows/1", json={"values": {"professor_employee_id": meera.employee_code}}, headers=h)
    r = client.put(f"/api/imports/{sid}/rows/3", json={"values": {"professor_employee_id": ""}}, headers=h)
    assert r.json()["preview"]["can_commit"] is True
    assert client.post(f"/api/imports/{sid}/commit", json={"confirm": True}, headers=h).status_code == 200
    db.expire_all()
    assert before is None and db.scalar(select(User.id).where(User.employee_code == "GHOST-99")) is None
    lectures = db.scalars(select(Lecture).where(Lecture.teaching_plan_id == plan_id).order_by(Lecture.lecture_no)).all()
    assert [l.professor_id for l in lectures] == [meera.id, meera.id, None, None]
    assert lectures[0].schedule.room == "C-310"


def test_one_sheet_cannot_put_the_professor_in_two_overlapping_rows(db):
    from datetime import date
    from app.services.validation_service import ValidationContext, validate_rows
    cols = [{"key": "a", "header": "Lecture_No", "values": ["1", "2", "3"]},
            {"key": "b", "header": "Content_Topic", "values": ["One", "Two", "Three"]},
            {"key": "c", "header": "Date", "values": ["20/10/2026", "20/10/2026", "21/10/2026"]},
            {"key": "d", "header": "Start", "values": ["14:00", "14:30", "14:30"]},
            {"key": "e", "header": "End", "values": ["15:00", "15:30", "15:30"]}]
    mapping = {k: {"status": "MAPPED", "field": f} for k, f in
               (("a", "lecture_no"), ("b", "content_topic"), ("c", "planned_date"), ("d", "planned_start_time"), ("e", "planned_end_time"))}
    prof = db.scalar(select(User).where(User.username == "professor2.demo"))
    ctx = ValidationContext(semester_start=date(2026, 7, 1), semester_end=date(2026, 12, 31),
                            plan_professor={"id": str(prof.id), "name": prof.full_name})
    out = validate_rows(cols, mapping, ctx=ctx)
    assert [r["status"] for r in out["rows"]] == ["VALID", "ERROR", "VALID"]
    assert "two classes at once" in out["rows"][1]["issues"][-1]["message"] and not out["can_commit"]


def test_sprint_move_to_another_week_is_checked_on_the_day_it_lands(client, tokens, db):
    """A lecture moved out of the revised week must not land on top of the same professor's class elsewhere."""
    A = tokens["ADMIN"]
    busy = db.execute(
        select(Lecture, LectureSchedule).join(LectureSchedule, LectureSchedule.lecture_id == Lecture.id)
        .join(TeachingPlan, Lecture.teaching_plan_id == TeachingPlan.id)
        .where(TeachingPlan.status == "PUBLISHED", Lecture.is_cancelled.is_(False), ~Lecture.progress.has(),
               LectureSchedule.planned_date > clock.today() + timedelta(days=16)).order_by(LectureSchedule.planned_date)).first()
    target, target_sch = busy
    prof = target.effective_professor_id
    # another future lecture of the same professor, in an earlier week
    monday = lambda d: d - timedelta(days=d.weekday())  # noqa: E731
    mover = db.scalars(
        select(Lecture).join(LectureSchedule).join(TeachingPlan, Lecture.teaching_plan_id == TeachingPlan.id)
        .where(TeachingPlan.status == "PUBLISHED", Lecture.is_cancelled.is_(False), ~Lecture.progress.has(), Lecture.id != target.id,
               TeachingPlan.professor_id == prof, Lecture.professor_id.is_(None),
               LectureSchedule.planned_date > clock.today() + timedelta(days=1),
               LectureSchedule.planned_date < monday(target_sch.planned_date)).order_by(LectureSchedule.planned_date)).first()
    assert mover is not None
    week = monday(mover.schedule.planned_date).isoformat()
    draft = client.post("/api/admin/sprint-plan/revisions", json={"week_start": week}, headers=A).json()["draft"]
    r = client.patch(f"/api/admin/sprint-plan/revisions/{draft['id']}/lectures/{mover.id}", headers=A, json={
        "planned_date": target_sch.planned_date.isoformat(), "planned_start_time": target_sch.planned_start_time.strftime("%H:%M"),
        "planned_end_time": target_sch.planned_end_time.strftime("%H:%M"), "reason": "HOLIDAY_ADJUSTMENT"})
    assert r.status_code == 200, r.text
    assert any(c["kind"] == "PROFESSOR" and c["level"] == "ERROR" for c in r.json()["conflicts"]), r.json()["conflicts"]
    r = client.post(f"/api/admin/sprint-plan/revisions/{draft['id']}/publish", json={}, headers=A)
    assert r.status_code == 409 and r.json()["error"]["code"] == "SCHEDULE_CONFLICT"
    client.delete(f"/api/admin/sprint-plan/revisions/{draft['id']}", headers=A)
    db.expire_all()
    assert db.get(Lecture, mover.id).schedule.planned_date != target_sch.planned_date  # nothing was applied


# ---------------------------------------------------------------- scopes

def test_clch_sees_only_submissions_inside_the_assigned_scope(client, tokens, db):
    everything = client.get("/api/verifications/queue/pending", headers=tokens["CL_CH"]).json()["items"]
    sections = {x["section"] for x in everything}
    assert len(everything) > 1 and "A" in sections
    cs502 = db.scalar(select(Subject).where(Subject.code == "CS502"))
    narrow = make_user(client, tokens, role="CL_CH", scope={"mode": "SELECTED", "subject_ids": [str(cs502.id)]})
    assert narrow["scope_label"] == "CS502"
    H = bearer(client, narrow["email"])
    mine = client.get("/api/verifications/queue/pending", headers=H).json()["items"]
    assert mine and {x["subject"]["code"] for x in mine} == {"CS502"}
    assert client.get("/api/verifications/metrics", headers=H).json()["pending"] == len(mine)
    # A record outside the scope does not exist for this verifier - not in lists, not by direct link, not for actions.
    outside = next(x for x in everything if x["subject"]["code"] != "CS502")
    assert client.get(f"/api/verifications/{outside['id']}", headers=H).status_code == 404
    assert client.post(f"/api/verifications/{outside['id']}/verify", json={}, headers=H).status_code == 404
    assert client.get(f"/api/lectures/{outside['lecture_id']}", headers=H).status_code == 404
    sheet = client.get("/api/sprint-plan/sheet", headers=H).json()
    assert all(r["subject"]["code"] == "CS502" for r in sheet["rows"])
    # Reports, plan lists and plan pages follow the same scope; institution-wide screens are admin-only.
    report = client.get("/api/reports/progress", headers=H).json()
    assert {x["subject_code"] for x in report["subjects"]} == {"CS502"}
    whole = client.get("/api/reports/progress", headers=tokens["ADMIN"]).json()
    assert report["summary"]["total"] < whole["summary"]["total"]
    plans = client.get("/api/teaching-plans", headers=H).json()["items"]
    assert plans and {p["subject"]["code"] for p in plans} == {"CS502"}
    assert client.get(f"/api/teaching-plans/{outside['plan_id']}", headers=H).status_code == 404
    assert client.get(f"/api/teaching-plans/{outside['plan_id']}/lectures", headers=H).status_code == 404
    assert all(x["subject"]["code"] == "CS502" for x in client.get("/api/reports/verification/pending", headers=H).json()["items"])
    assert client.get("/api/admin/dashboard", headers=H).status_code == 403
    assert client.get("/api/audit", headers=H).status_code == 403
    # Widening the scope takes effect immediately, with no new sign-in.
    r = client.patch(f"/api/admin/users/{narrow['id']}", json={"scope": {"mode": "ALL"}}, headers=tokens["ADMIN"])
    assert r.json()["scope_label"] == "All professors"
    assert len(client.get("/api/verifications/queue/pending", headers=H).json()["items"]) == len(everything)
    # A selected scope has to select something.
    r = client.patch(f"/api/admin/users/{narrow['id']}", json={"scope": {"mode": "SELECTED"}}, headers=tokens["ADMIN"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "SCOPE_EMPTY"


def test_scope_by_semester_and_section(client, tokens, db):
    b = db.scalar(select(Section).where(Section.name == "B"))
    u = make_user(client, tokens, role="CL_CH", scope={"mode": "SELECTED", "department_id": str(b.branch.department_id),
                                                       "semester_numbers": [5], "section_names": ["b"]})
    assert u["scope_label"].endswith("Sem V · Sec B")
    H = bearer(client, u["email"])
    rows = client.get("/api/sprint-plan/sheet", headers=H).json()["rows"]
    assert all(r["section"] == "B" for r in rows)
    assert all(x["section"] == "B" for x in client.get("/api/verifications/queue/all", headers=H).json()["items"])


def test_om_scope_limits_classes_alerts_and_final_verification(client, tokens, db):
    today = clock.today()
    span = {"date_from": (today - timedelta(days=3)).isoformat(), "date_to": (today + timedelta(days=4)).isoformat()}
    full = client.get("/api/om/classes", params=span, headers=tokens["OM"]).json()["items"]
    assert len({r["subject"]["code"] for r in full}) > 1
    code = full[0]["subject"]["code"]
    subject = db.scalar(select(Subject).where(Subject.code == code))
    u = make_user(client, tokens, role="OM", scope={"mode": "SELECTED", "subject_ids": [str(subject.id)]})
    H = bearer(client, u["email"])
    mine = client.get("/api/om/classes", params=span, headers=H).json()["items"]
    assert mine and {r["subject"]["code"] for r in mine} == {code}
    feed = client.get("/api/schedule/today", headers=H).json()["classes"]
    assert {c["subject"]["code"] for c in feed} <= {code}
    outside = next(r for r in full if r["subject"]["code"] != code)
    assert client.post(f"/api/om/classes/{outside['lecture_id']}/entry", json={"time": "00:01"}, headers=H).status_code == 404
    assert client.get(f"/api/om/classes/{outside['lecture_id']}", headers=H).status_code == 404
    pending = client.get("/api/verifications/queue/pending", headers=H).json()["items"]
    assert all(x["subject"]["code"] == code and x["level"] == "OM" for x in pending)


def test_om_final_verify_waits_for_clch(client, tokens):
    rows = [r for r in client.get("/api/sprint-plan/sheet", params={"week_start": (clock.today() - timedelta(days=7)).isoformat()},
                                  headers=tokens["OM"]).json()["rows"]]
    rows += client.get("/api/sprint-plan/sheet", headers=tokens["OM"]).json()["rows"]
    waiting = [r for r in rows if r["clch"]["status"] == "PENDING"]
    ready = [r for r in rows if r["om"]["status"] == "PENDING"]
    assert waiting and all(r["waiting_for"] == "Waiting for CL/CH academic verification." and r["my_verification_id"] is None for r in waiting)
    assert all(r["clch"]["status"] == "VERIFIED" and r["my_verification_id"] for r in ready)
    assert all(set(r["verification"]) == {"CL_CH", "OM"} for r in rows)


def test_admin_monitors_but_cannot_verify(client, tokens, db):
    sheet = client.get("/api/sprint-plan/sheet", headers=tokens["ADMIN"])
    assert sheet.status_code == 200 and sheet.json()["scope"]["label"] == "Whole institution"
    v = db.scalar(select(Verification).where(Verification.status == "PENDING"))
    assert client.post(f"/api/verifications/{v.id}/verify", json={}, headers=tokens["ADMIN"]).status_code == 403
    assert client.get("/api/sprint-plan/sheet", headers=tokens["PROFESSOR"]).status_code == 403
