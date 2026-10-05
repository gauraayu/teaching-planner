"""End-to-end API tests: roles, imports, execution, verification order."""
import io
import uuid
from datetime import date, timedelta

import pytest
from openpyxl import Workbook
from sqlalchemy import func, select

from app.core import clock
from app.models import ImportSession, Lecture, LectureSubtopic, Section, Subject, TeachingPlan, User


def ids(db):
    plan = db.scalar(select(TeachingPlan).where(TeachingPlan.name.like("Data Structures%Section A")))
    return {
        "ay": plan.academic_year_id, "dept": plan.department_id, "sem": plan.semester_id,
        "cse": plan.branch_id, "plan_dsa_a": plan.id,
        "cse5a": plan.section_id,
        "cse5b": db.scalar(select(Section.id).where(Section.name == "B", Section.branch_id == plan.branch_id)),
        "cs505": db.scalar(select(Subject.id).where(Subject.code == "CS505")),
        "cs503": db.scalar(select(Subject.id).where(Subject.code == "CS503")),
        "cs504": db.scalar(select(Subject.id).where(Subject.code == "CS504")),
        "dsa": plan.subject_id,
        "prof": plan.professor_id,
        "other_prof": db.scalar(select(User.id).where(User.full_name == "Dr. Meera Iyer")),
        # Teaches only on Wednesday afternoons in the seed, so morning slots never clash.
        "free_prof": db.scalar(select(User.id).where(User.full_name == "Dr. Kavita Rao")),
    }


def new_plan(client, tokens, i, subject, section, professor=None):
    body = {"academic_year_id": str(i["ay"]), "semester_id": str(i["sem"]), "department_id": str(i["dept"]),
            "branch_id": str(i["cse"]), "section_id": str(section), "subject_id": str(subject),
            "professor_id": str(professor or i["prof"])}
    r = client.post("/api/teaching-plans", json=body, headers=tokens["ADMIN"])
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------------------------------------------------------- auth & permissions

def test_login_returns_role_and_permissions(client, tokens):
    me = client.get("/api/me", headers=tokens["CL_CH"]).json()
    assert me["role"] == "CL_CH" and me["role_label"] == "CL/CH"
    assert "verify.cl_ch" in me["permissions"] and "verify.om" not in me["permissions"]
    assert me["academic_session"]["semester"]["name"] == "Semester V"


def test_missing_or_forged_token_rejected(client):
    assert client.get("/api/me").status_code == 401
    r = client.get("/api/me", headers={"Authorization": "Bearer v1.eyJzdWIiOiJ4In0.forged"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "NOT_AUTHENTICATED"


def test_role_permissions_enforced_on_backend(client, tokens, db):
    i = ids(db)
    assert client.get("/api/imports/fields", headers=tokens["PROFESSOR"]).status_code == 403
    assert client.post("/api/teaching-plans", json={}, headers=tokens["CL_CH"]).status_code in (403, 422)
    assert client.get("/api/professor/dashboard", headers=tokens["ADMIN"]).status_code == 403
    lec = db.scalar(select(Lecture.id).where(Lecture.teaching_plan_id == i["plan_dsa_a"]))
    r = client.put(f"/api/lectures/{lec}/progress", json={"execution_status": "COMPLETED"}, headers=tokens["CL_CH"])
    assert r.status_code == 403


def test_duplicate_plan_rejected(client, tokens, db):
    i = ids(db)
    body = {"academic_year_id": str(i["ay"]), "semester_id": str(i["sem"]), "department_id": str(i["dept"]),
            "branch_id": str(i["cse"]), "section_id": str(i["cse5a"]), "subject_id": str(i["dsa"]), "professor_id": str(i["prof"])}
    r = client.post("/api/teaching-plans", json=body, headers=tokens["ADMIN"])
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "DUPLICATE_PLAN"


def test_plan_relationship_integrity(client, tokens, db):
    i = ids(db)
    body = {"academic_year_id": str(i["ay"]), "semester_id": str(i["sem"]), "department_id": str(i["dept"]),
            "branch_id": str(i["cse"]), "section_id": str(i["cse5b"]), "subject_id": str(i["cs505"]),
            "professor_id": str(db.scalar(select(User.id).where(User.email == "clch@demo.institute.edu")))}
    r = client.post("/api/teaching-plans", json=body, headers=tokens["ADMIN"])
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_FACULTY"


# ---------------------------------------------------------------- full-table import

SHEET = (
    "SrNo\tLecture_No\tUnit_No\tContent_Topic\tBloom Taxnomy\tSub_Topic1\tSub_Topic2\tScheduled_Date\tStart Time\tRemarks about Task Completion\n"
    "1\t1\t1\tIntroduction to Automata\tK1\tAlphabets and strings\tLanguages\t05/10/2026\t10:00 AM\t\n"
    "2\t2\t1\tDeterministic Finite Automata\tK2\tTransition function\t\t07/10/2026\t10:00 AM\t\n"
    "3\t3\t\tNFA\tK3\tε-transitions\t\t31/02/2026\t10:00 AM\t\n"
    "4\t4\t2\tRegular Expressions\tK2\t\t\t12/10/2026\t10:00 AM\t\n"
)


def test_full_table_import_flow(client, tokens, db):
    i = ids(db)
    plan_id = new_plan(client, tokens, i, i["cs505"], i["cse5b"], i["free_prof"])
    h = tokens["ADMIN"]
    s = client.post("/api/imports/session", json={"teaching_plan_id": plan_id}, headers=h).json()
    sid = s["id"]
    client.put(f"/api/imports/{sid}/mode", json={"import_mode": "FULL_TABLE"}, headers=h)
    r = client.post(f"/api/imports/{sid}/full-table", json={"raw_text": SHEET}, headers=h)
    assert r.status_code == 200, r.text
    result, session = r.json()["result"], r.json()["session"]
    assert (result["rows_detected"], result["columns_detected"], result["has_header"]) == (4, 10, True)
    by_header = {c["header"]: c["mapping"] for c in session["columns"]}
    assert by_header["Bloom Taxnomy"]["status"] == "SUGGESTED"
    assert by_header["Remarks about Task Completion"]["status"] == "IGNORED"

    # Unconfirmed fuzzy mapping blocks the import.
    v = client.post(f"/api/imports/{sid}/validate", json={}, headers=h).json()
    assert not v["preview"]["can_commit"]
    assert any(x["code"] == "MAPPING_UNRESOLVED" for x in v["preview"]["session_issues"])

    client.post(f"/api/imports/{sid}/mapping/confirm-suggestions", headers=h)
    v = client.post(f"/api/imports/{sid}/validate", json={}, headers=h).json()["preview"]
    assert v["summary"]["errors"] == 1  # 31/02/2026
    bad = next(r for r in v["rows"] if r["status"] == "ERROR")
    assert bad["row_number"] == 3
    # Blank unit on row 3 did not shift row 4's unit.
    assert v["rows"][3]["values"]["unit_no"] == 2

    commit = client.post(f"/api/imports/{sid}/commit", json={"confirm": True}, headers=h)
    assert commit.status_code == 422 and commit.json()["error"]["code"] == "IMPORT_HAS_ERRORS"

    r = client.put(f"/api/imports/{sid}/rows/2", json={"values": {"planned_date": "09/10/2026", "unit_no": "1"}}, headers=h)
    assert r.json()["preview"]["can_commit"] is True

    r = client.post(f"/api/imports/{sid}/commit", json={"confirm": True}, headers=h)
    assert r.status_code == 200, r.text
    assert (r.json()["lectures"], r.json()["subtopics"], r.json()["status"]) == (4, 4, "PUBLISHED")

    db.expire_all()
    plan = db.get(TeachingPlan, uuid.UUID(plan_id))
    assert plan.status == "PUBLISHED"
    lec = db.scalar(select(Lecture).where(Lecture.teaching_plan_id == plan.id, Lecture.lecture_no == 1))
    assert [s.title for s in lec.subtopics] == ["Alphabets and strings", "Languages"]
    assert lec.schedule.planned_date == date(2026, 10, 5)
    assert lec.blooms_taxonomy == "K1"

    # A published plan cannot be re-imported into.
    r = client.post("/api/imports/session", json={"teaching_plan_id": plan_id}, headers=h)
    assert r.status_code == 409
    activity = client.get(f"/api/teaching-plans/{plan_id}/activity", headers=h).json()["items"]
    assert {"plan.imported", "plan.published"} <= {a["action"] for a in activity}


# ---------------------------------------------------------------- column-wise import

def test_column_wise_import_with_row_mismatch(client, tokens, db):
    i = ids(db)
    plan_id = new_plan(client, tokens, i, i["cs504"], i["cse5a"])
    h = tokens["ADMIN"]
    sid = client.post("/api/imports/session", json={"teaching_plan_id": plan_id}, headers=h).json()["id"]
    client.put(f"/api/imports/{sid}/mode", json={"import_mode": "COLUMN_WISE"}, headers=h)

    add = lambda **kw: client.post(f"/api/imports/{sid}/column", json=kw, headers=h).json()  # noqa: E731
    assert add(field="content_topic", raw_text="OSI Model\nTCP/IP Model\nIP Addressing\nSubnetting\nRouting\n")["result"]["status"] == "ADDED"
    assert add(field="lecture_no", raw_text="1\n2\n3\n4\n5")["result"]["row_count"] == 5

    # Bloom column is one short: never imported silently.
    mismatch = add(field="blooms_taxonomy", raw_text="K1\nK2\nK2\nK3")["result"]
    assert mismatch["status"] == "MISMATCH"
    assert (mismatch["expected"], mismatch["received"], mismatch["difference"]) == (5, 4, 1)
    assert mismatch["can_pad"] and not mismatch["can_extend"]
    session = client.get(f"/api/imports/{sid}", headers=h).json()
    assert len(session["columns"]) == 2

    padded = add(field="blooms_taxonomy", raw_text="K1\nK2\nK2\nK3", on_mismatch="PAD")["session"]
    bloom = next(c for c in padded["columns"] if c["header"] == "Bloom's Taxonomy")
    assert bloom["values"] == ["K1", "K2", "K2", "K3", ""]

    # Blank in the middle stays in place.
    add(field="subtopic", raw_text="Layers\n\nClassful\nMasks\nDistance vector")
    v = client.post(f"/api/imports/{sid}/validate", json={}, headers=h).json()["preview"]
    assert [r["values"]["subtopics"] for r in v["rows"]] == [["Layers"], [], ["Classful"], ["Masks"], ["Distance vector"]]
    assert any(x["code"] == "ROW_COUNT_PADDED" for x in v["session_issues"])

    # Duplicate field needs Replace; undo restores the previous state.
    r = client.post(f"/api/imports/{sid}/column", json={"field": "lecture_no", "raw_text": "1\n2\n3\n4\n5"}, headers=h)
    assert r.status_code == 409
    key = next(c["key"] for c in padded["columns"] if c["header"] == "Lecture Number")
    add(field="lecture_no", raw_text="1\n2\n3\n4\n6", replace_key=key)
    session = client.post(f"/api/imports/{sid}/undo", headers=h).json()
    lec_col = next(c for c in session["columns"] if c["header"] == "Lecture Number")
    assert lec_col["values"][-1] == "5"

    r = client.post(f"/api/imports/{sid}/commit", json={"confirm": True}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["lectures"] == 5


# ---------------------------------------------------------------- file upload

def _xlsx_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Teaching Plan"
    ws.append(["Lecture No", "Unit", "Topic", "Bloom's Level", "Date"])
    ws.append([1, 1, "Process Concept", "K1", date(2026, 10, 6)])
    ws.append([2, None, "Process Scheduling", "K2", date(2026, 10, 8)])
    ws.append([3, None, "Threads", "K2", date(2026, 10, 13)])
    ws.merge_cells("B2:B4")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_excel_upload_expands_merged_cells(client, tokens, db):
    i = ids(db)
    plan_id = new_plan(client, tokens, i, i["cs503"], i["cse5b"])
    h = tokens["ADMIN"]
    sid = client.post("/api/imports/session", json={"teaching_plan_id": plan_id}, headers=h).json()["id"]
    r = client.post(f"/api/imports/{sid}/file", files={"file": ("plan.xlsx", _xlsx_bytes(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"]["rows_detected"] == 3 and body["session"]["import_mode"] == "EXCEL"
    assert all(c["mapping"]["status"] == "MAPPED" for c in body["session"]["columns"])
    preview = client.post(f"/api/imports/{sid}/validate", json={}, headers=h).json()["preview"]
    assert [r["values"]["unit_no"] for r in preview["rows"]] == [1, 1, 1]
    assert preview["rows"][2]["values"]["planned_date"] == "2026-10-13"


def test_csv_upload_and_unsupported_file(client, tokens, db):
    sid = db.scalar(select(ImportSession.id).where(ImportSession.status != "IMPORTED", ImportSession.import_mode == "EXCEL"))
    h = tokens["ADMIN"]
    csv_bytes = "Lecture No,Topic,Unit\n1,Process Concept,1\n2,\"Scheduling, part 1\",1\n".encode()
    r = client.post(f"/api/imports/{sid}/file", files={"file": ("plan.csv", csv_bytes, "text/csv")}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["session"]["import_mode"] == "CSV"
    assert r.json()["session"]["columns"][1]["samples"][1] == "Scheduling, part 1"
    r = client.post(f"/api/imports/{sid}/file", files={"file": ("plan.pdf", b"%PDF", "application/pdf")}, headers=h)
    assert r.status_code == 400 and r.json()["error"]["code"] == "UNSUPPORTED_FILE"


# ---------------------------------------------------------------- transaction safety

def test_commit_failure_rolls_back_everything(client, tokens, db, monkeypatch):
    i = ids(db)
    toc = db.scalar(select(TeachingPlan).where(TeachingPlan.subject_id == i["cs505"], TeachingPlan.section_id == i["cse5a"]))
    h = tokens["ADMIN"]
    sid = client.post("/api/imports/session", json={"teaching_plan_id": str(toc.id)}, headers=h).json()["id"]
    client.post(f"/api/imports/{sid}/column", json={"field": "unit_no", "raw_text": "1\n1\n1\n1\n2\n2"}, headers=h)
    client.post(f"/api/imports/{sid}/validate", json={}, headers=h)

    from app.services import notification_service

    def boom(*a, **k):
        raise RuntimeError("simulated failure after lectures were inserted")

    monkeypatch.setattr(notification_service, "notify", boom)
    r = client.post(f"/api/imports/{sid}/commit", json={"confirm": True}, headers=h)
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "IMPORT_FAILED"
    db.expire_all()
    assert db.scalar(select(func.count(Lecture.id)).where(Lecture.teaching_plan_id == toc.id)) == 0
    assert db.get(TeachingPlan, toc.id).status == "DRAFT"
    assert db.get(ImportSession, uuid.UUID(sid)).status == "FAILED"


# ---------------------------------------------------------------- professor execution & verification

def _today_lecture(db, i) -> Lecture:
    from app.models import LectureSchedule

    return db.scalar(select(Lecture).join(LectureSchedule).where(
        Lecture.teaching_plan_id == i["plan_dsa_a"], LectureSchedule.planned_date == clock.today()))


def test_professor_today_tasks_are_derived(client, tokens, db):
    i = ids(db)
    items = client.get("/api/professor/tasks/today", headers=tokens["PROFESSOR"]).json()["items"]
    lec = _today_lecture(db, i)
    if lec is None:
        pytest.skip("No DSA lecture falls on today's date")
    assert str(lec.id) in {t["id"] for t in items}
    overdue = client.get("/api/professor/tasks/overdue", headers=tokens["PROFESSOR"]).json()["items"]
    assert all(t["is_overdue"] for t in overdue) and overdue


def test_professor_cannot_edit_master_data(client, tokens, db):
    i = ids(db)
    lec = db.scalar(select(Lecture).where(Lecture.teaching_plan_id == i["plan_dsa_a"]).order_by(Lecture.sequence.desc()))
    h = tokens["PROFESSOR"]
    r = client.put(f"/api/lectures/{lec.id}/progress", json={"execution_status": "IN_PROGRESS", "content_topic": "Hacked"}, headers=h)
    assert r.status_code == 422
    r = client.patch(f"/api/lectures/{lec.id}", json={"reason": "change topic", "content_topic": "Hacked"}, headers=h)
    assert r.status_code == 403
    db.expire_all()
    assert db.get(Lecture, lec.id).content_topic != "Hacked"


def test_professor_cannot_touch_another_professors_lecture(client, tokens, db):
    i = ids(db)
    other_plan = db.scalar(select(TeachingPlan.id).where(TeachingPlan.professor_id == i["other_prof"]))
    lec = db.scalar(select(Lecture.id).where(Lecture.teaching_plan_id == other_plan))
    r = client.put(f"/api/lectures/{lec}/progress", json={"execution_status": "IN_PROGRESS"}, headers=tokens["PROFESSOR"])
    assert r.status_code == 403


def test_execution_rules_and_full_verification_chain(client, tokens, db):
    i = ids(db)
    lec = _today_lecture(db, i) or db.scalar(select(Lecture).where(Lecture.teaching_plan_id == i["plan_dsa_a"], Lecture.progress == None).order_by(Lecture.sequence))  # noqa: E711
    subs = list(db.scalars(select(LectureSubtopic.id).where(LectureSubtopic.lecture_id == lec.id).order_by(LectureSubtopic.position)))
    assert len(subs) >= 2
    P = tokens["PROFESSOR"]
    today = clock.today().isoformat()
    base = {"actual_completion_date": today, "shared_with_students": True,
            "notes": [{"title": "Notes", "file_url": "https://drive.google.com/file/d/abc/view"}]}

    r = client.put(f"/api/lectures/{lec.id}/progress", json=base | {"execution_status": "COMPLETED", "covered_subtopic_ids": [str(subs[0])]}, headers=P)
    assert r.status_code == 422 and r.json()["error"]["code"] == "SUBTOPICS_INCOMPLETE"
    r = client.put(f"/api/lectures/{lec.id}/progress", json=base | {"execution_status": "COMPLETED", "shared_with_students": False,
                   "covered_subtopic_ids": [str(s) for s in subs]}, headers=P)
    assert r.status_code == 422 and r.json()["error"]["code"] == "NOT_SHARED_REASON_REQUIRED"
    future = (clock.today() + timedelta(days=1)).isoformat()
    r = client.put(f"/api/lectures/{lec.id}/progress", json=base | {"execution_status": "COMPLETED", "actual_completion_date": future,
                   "covered_subtopic_ids": [str(s) for s in subs]}, headers=P)
    assert r.status_code == 422

    r = client.put(f"/api/lectures/{lec.id}/progress", json=base | {"execution_status": "PARTIALLY_COMPLETED",
                   "covered_subtopic_ids": [str(subs[0])], "remarks": "Ran out of time"}, headers=P)
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["can_submit"] and detail["execution"]["covered_subtopic_ids"] == [str(subs[0])]
    assert detail["master"]["planned_date"] == lec.schedule.planned_date.isoformat()  # planned date untouched
    pid = detail["execution"]["id"]

    r = client.post(f"/api/lecture-progress/{pid}/submit", headers=P)
    assert r.status_code == 200 and r.json()["execution"]["submission_status"] == "SUBMITTED"
    r = client.put(f"/api/lectures/{lec.id}/progress", json=base | {"execution_status": "COMPLETED",
                   "covered_subtopic_ids": [str(s) for s in subs]}, headers=P)
    assert r.status_code == 409 and r.json()["error"]["code"] == "PROGRESS_LOCKED"

    def pending_for(role):
        items = client.get("/api/verifications/queue/pending", headers=tokens[role]).json()["items"]
        return next((x for x in items if x["lecture_id"] == str(lec.id)), None)

    item = pending_for("CL_CH")
    assert item and item["level"] == "CL_CH" and item["level_label"] == "CL/CH"
    assert pending_for("OM") is None  # OM cannot see it before CL/CH acts

    # OM cannot jump the queue.
    r = client.post(f"/api/verifications/{item['id']}/verify", json={}, headers=tokens["OM"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "WRONG_VERIFICATION_LEVEL"
    assert client.get(f"/api/verifications/{item['id']}", headers=tokens["OM"]).json()["waiting_for"] == "Waiting for CL/CH academic verification."
    # A professor cannot verify at all, and an admin only monitors.
    assert client.post(f"/api/verifications/{item['id']}/verify", json={}, headers=P).status_code == 403
    assert client.post(f"/api/verifications/{item['id']}/verify", json={}, headers=tokens["ADMIN"]).status_code == 403

    r = client.post(f"/api/verifications/{item['id']}/request-correction", json={"remarks": ""}, headers=tokens["CL_CH"])
    assert r.status_code == 422  # remarks are mandatory
    r = client.post(f"/api/verifications/{item['id']}/request-correction",
                    json={"remarks": "Mark the second subtopic once it is covered in the next class."}, headers=tokens["CL_CH"])
    assert r.status_code == 200
    assert client.post(f"/api/verifications/{item['id']}/verify", json={}, headers=tokens["CL_CH"]).status_code == 409
    notes = client.get("/api/notifications", headers=P).json()["items"]
    assert any(n["title"].startswith("Correction requested by CL/CH") for n in notes)

    # Professor fixes and resubmits; round 2 starts at CL/CH again.
    detail = client.get(f"/api/lectures/{lec.id}", headers=P).json()
    assert detail["execution"]["submission_status"] == "CORRECTION_REQUIRED" and detail["open_correction"]
    r = client.put(f"/api/lectures/{lec.id}/progress", json=base | {"execution_status": "COMPLETED",
                   "covered_subtopic_ids": [str(s) for s in subs]}, headers=P)
    assert r.status_code == 200
    r = client.post(f"/api/lecture-progress/{pid}/submit", headers=P)
    assert r.json()["execution"]["submission_status"] == "RESUBMITTED"

    item = pending_for("CL_CH")
    assert item["round"] == 2 and item["is_resubmission"]
    assert pending_for("OM") is None
    r = client.post(f"/api/verifications/{item['id']}/verify", json={"remarks": "OK"}, headers=tokens["CL_CH"])
    assert r.status_code == 200
    # One academic step only: the record now waits for the Operations Manager, with no second CH approval.
    waiting = client.get(f"/api/lectures/{lec.id}", headers=P).json()
    assert waiting["execution"]["submission_status"] == "RESUBMITTED"
    assert waiting["verification_chain"] == ["CL_CH", "OM"]

    om_item = pending_for("OM")
    assert om_item and [p["verification_level"] for p in om_item["prior_verifications"]] == ["CL_CH"]
    assert client.post(f"/api/verifications/{om_item['id']}/verify", json={}, headers=tokens["CL_CH"]).status_code == 403
    r = client.post(f"/api/verifications/{om_item['id']}/verify", json={"remarks": "Timings match."}, headers=tokens["OM"])
    assert r.status_code == 200, r.text
    final = client.get(f"/api/lectures/{lec.id}", headers=P).json()
    assert final["execution"]["submission_status"] == "FINAL_VERIFIED"
    assert [(v["verification_level"], v["status"]) for v in final["verifications"]] == [
        ("CL_CH", "CORRECTION_REQUIRED"), ("CL_CH", "VERIFIED"), ("OM", "VERIFIED")]
    # The audit trail names the person, not just the role.
    assert all(v["verifier"]["full_name"] for v in final["verifications"])

    notes = client.get("/api/notifications", headers=P).json()
    assert any("final verified" in n["title"] for n in notes["items"])


# ---------------------------------------------------------------- reports

def test_progress_buckets_add_up(client, tokens):
    r = client.get("/api/reports/progress", headers=tokens["ADMIN"]).json()
    s = r["summary"]
    assert s["completed"] + s["partial"] + s["delayed"] + s["pending"] == s["total"]
    assert s["execution_pct"] == round(s["completed"] * 100 / s["total"])
    dash = client.get("/api/admin/dashboard", headers=tokens["ADMIN"]).json()
    assert dash["metrics"]["verification_pending"] > 0


def test_admin_controlled_correction_is_audited(client, tokens, db):
    i = ids(db)
    lec = db.scalar(select(Lecture).where(Lecture.teaching_plan_id == i["plan_dsa_a"]).order_by(Lecture.sequence.desc()))
    r = client.patch(f"/api/lectures/{lec.id}", json={"reason": "Syllabus revision", "blooms_taxonomy": "K5"}, headers=tokens["ADMIN"])
    assert r.status_code == 200
    activity = client.get(f"/api/teaching-plans/{i['plan_dsa_a']}/activity", headers=tokens["ADMIN"]).json()["items"]
    entry = next(a for a in activity if a["action"] == "lecture.corrected")
    assert entry["new_values"] == {"blooms_taxonomy": "K5"}
