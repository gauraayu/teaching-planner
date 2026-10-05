"""Model -> JSON shapes shared by every router. One place, so the API stays consistent."""
from __future__ import annotations

from app.models import (
    AcademicYear, Assignment, AuditLog, Branch, Department, FacultySubjectAssignment, ImportSession, Lecture,
    LectureMaterial, Notification, Section, Semester, Subject, TeachingPlan, User, Verification,
)


def _iso(v):
    return v.isoformat() if v is not None else None


def _hm(t):
    return t.strftime("%H:%M") if t else None


def user_brief(u: User | None) -> dict | None:
    if not u:
        return None
    return {"id": str(u.id), "full_name": u.full_name, "designation": u.designation, "role": u.role.code}


def user_full(u: User) -> dict:
    return user_brief(u) | {
        "email": u.email, "employee_code": u.employee_code, "employee_id": u.employee_code, "username": u.username,
        "is_active": u.is_active, "is_demo": u.is_demo,
        "department": department(u.department) if u.department else None,
    }


def academic_year(a: AcademicYear) -> dict:
    return {"id": str(a.id), "name": a.name, "start_date": _iso(a.start_date), "end_date": _iso(a.end_date), "is_current": a.is_current}


def semester(s: Semester) -> dict:
    return {"id": str(s.id), "academic_year_id": str(s.academic_year_id), "academic_year": s.academic_year.name,
            "number": s.number, "name": s.name, "start_date": _iso(s.start_date), "end_date": _iso(s.end_date),
            "is_current": s.is_current}


def department(d: Department) -> dict:
    return {"id": str(d.id), "code": d.code, "name": d.name}


def branch(b: Branch) -> dict:
    return {"id": str(b.id), "department_id": str(b.department_id), "department": b.department.name, "code": b.code, "name": b.name}


def section(s: Section) -> dict:
    return {"id": str(s.id), "name": s.name, "branch_id": str(s.branch_id), "branch": s.branch.name, "branch_code": s.branch.code,
            "semester_id": str(s.semester_id), "semester": s.semester.name, "academic_year": s.semester.academic_year.name,
            "student_count": s.student_count}


def subject(s: Subject) -> dict:
    return {"id": str(s.id), "code": s.code, "name": s.name, "short_name": s.short_name, "branch_id": str(s.branch_id),
            "branch": s.branch.name, "branch_code": s.branch.code, "semester_number": s.semester_number, "credits": s.credits,
            "is_active": s.is_active}


def faculty_assignment(a: FacultySubjectAssignment) -> dict:
    return {"id": str(a.id), "professor": user_brief(a.professor), "subject": {"id": str(a.subject.id), "code": a.subject.code, "name": a.subject.name},
            "section": {"id": str(a.section.id), "name": a.section.name, "branch_code": a.section.branch.code, "semester": a.section.semester.name},
            "is_primary": a.is_primary}


def plan_brief(p: TeachingPlan) -> dict:
    return {
        "id": str(p.id), "name": p.name, "status": p.status, "room": p.room,
        "classes_per_week": p.classes_per_week, "labs_per_week": p.labs_per_week, "lab_room": p.lab_room,
        "sprint_plan": {"id": str(p.sprint_plan_id), "name": p.sprint_plan.name} if p.sprint_plan_id and p.sprint_plan else None,
        "academic_year": {"id": str(p.academic_year_id), "name": p.academic_year.name},
        "semester": {"id": str(p.semester_id), "name": p.semester.name, "number": p.semester.number},
        "department": {"id": str(p.department_id), "name": p.department.name},
        "branch": {"id": str(p.branch_id), "name": p.branch.name, "code": p.branch.code},
        "section": {"id": str(p.section_id), "name": p.section.name},
        "subject": {"id": str(p.subject_id), "code": p.subject.code, "name": p.subject.name, "short_name": p.subject.short_name},
        "professor": user_brief(p.professor),
        "published_at": _iso(p.published_at), "created_at": _iso(p.created_at), "updated_at": _iso(p.updated_at),
    }


def lecture(lec: Lecture, *, include_progress: bool = True) -> dict:
    sch = lec.schedule
    data = {
        "id": str(lec.id), "teaching_plan_id": str(lec.teaching_plan_id), "sequence": lec.sequence,
        "serial_no": lec.serial_no, "lecture_no": lec.lecture_no, "lecture_type": lec.lecture_type, "unit_no": lec.unit_no,
        "content_topic": lec.content_topic, "blooms_taxonomy": lec.blooms_taxonomy,
        "subtopics": [{"id": str(s.id), "position": s.position, "title": s.title} for s in lec.subtopics],
        "planned_date": _iso(sch.planned_date) if sch else None,
        "planned_start_time": _hm(sch.planned_start_time) if sch else None,
        "planned_end_time": _hm(sch.planned_end_time) if sch else None,
        "room": (sch.room if sch else None) or lec.teaching_plan.room,
        "professor": user_brief(lec.effective_professor), "is_substitute": lec.professor_id is not None,
        "is_cancelled": lec.is_cancelled,
    }
    if include_progress:
        pr = lec.progress
        data["progress"] = None if not pr else {
            "id": str(pr.id), "execution_status": pr.execution_status, "submission_status": pr.submission_status,
            "actual_completion_date": _iso(pr.actual_completion_date), "rescheduled_to": _iso(pr.rescheduled_to),
            "submitted_at": _iso(pr.submitted_at), "final_verified_at": _iso(pr.final_verified_at),
        }
    return data


def material(m: LectureMaterial) -> dict:
    return {"id": str(m.id), "material_type": m.material_type, "caption": m.caption, "content_type": m.content_type,
            "size_bytes": m.size_bytes, "title": m.title, "file_name": m.file_name, "file_url": m.file_url,
            "uploaded_by_id": str(m.uploaded_by_id), "uploaded_at": _iso(m.uploaded_at)}


def assignment(a: Assignment | None) -> dict | None:
    if not a:
        return None
    return {"id": str(a.id), "title": a.title, "description": a.description, "link_url": a.link_url, "due_date": _iso(a.due_date),
            "shared_with_students": a.shared_with_students, "shared_at": _iso(a.shared_at),
            "not_shared_reason": a.not_shared_reason, "created_at": _iso(a.created_at)}


def verification(v: Verification) -> dict:
    from app.core.enums import LEVEL_LABELS
    return {"id": str(v.id), "round": v.round, "verification_level": v.verification_level,
            "level_label": LEVEL_LABELS.get(v.verification_level, v.verification_level), "status": v.status,
            "verifier": user_brief(v.verifier), "verifier_role": v.verifier_role, "remarks": v.remarks,
            "verified_at": _iso(v.verified_at), "created_at": _iso(v.created_at)}


def audit_entry(a: AuditLog) -> dict:
    return {"id": str(a.id), "action": a.action, "entity_type": a.entity_type, "entity_id": str(a.entity_id) if a.entity_id else None,
            "summary": a.summary, "actor": user_brief(a.actor), "actor_role": a.actor_role,
            "old_values": a.old_values, "new_values": a.new_values, "created_at": _iso(a.created_at)}


def notification(n: Notification) -> dict:
    return {"id": str(n.id), "kind": n.kind, "title": n.title, "body": n.body, "link": n.link, "is_read": n.is_read,
            "created_at": _iso(n.created_at)}


def import_session(s: ImportSession, *, include_draft: bool = True) -> dict:
    from app.services.import_service import source_columns

    draft = s.draft_data or {}
    data = {
        "id": str(s.id), "status": s.status, "import_mode": s.import_mode, "current_step": s.current_step,
        "source_name": s.source_name, "row_count": s.row_count, "revision": s.revision,
        "validated_revision": s.validated_revision, "is_validation_stale": s.validated_revision != s.revision,
        "failure_reason": s.failure_reason, "committed_at": _iso(s.committed_at),
        "created_at": _iso(s.created_at), "updated_at": _iso(s.updated_at),
        "teaching_plan": plan_brief(s.teaching_plan),
        "summary": (s.validation_result or {}).get("summary"),
    }
    if include_draft:
        cols = source_columns(s)
        data["columns"] = [
            {"key": c["key"], "header": c["header"], "letter": c.get("letter"), "value_count": len(c["values"]),
             "non_empty_count": sum(1 for v in c["values"] if v), "samples": [v for v in c["values"] if v][:4],
             "values": c["values"] if s.import_mode == "COLUMN_WISE" else None,
             "mapping": (s.column_mapping or {}).get(c["key"])}
            for c in cols
        ]
        data["has_header"] = draft.get("has_header")
        data["source"] = draft.get("source")
        data["padded"] = draft.get("padded", {})
        data["last_added_key"] = draft.get("last_added_key")
        data["can_undo"] = bool(draft.get("history"))
        data["overrides"] = draft.get("overrides", {})
        data["removed"] = draft.get("removed", [])
        # A small window of the raw grid lets the mapping screen show real data under each header.
        if s.import_mode != "COLUMN_WISE":
            grid = draft.get("grid") or []
            data["grid_preview"] = grid[:8]
    return data
