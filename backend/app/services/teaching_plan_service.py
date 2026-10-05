"""Teaching plans: creation (with duplicate protection), listing, publishing, controlled corrections."""
from __future__ import annotations

import uuid
from datetime import time

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.clock import now_utc
from app.core.enums import LectureType, PlanStatus, Role
from app.core.errors import BusinessRuleViolation, Conflict, NotFound
from app.models import (
    AcademicYear, AuditLog, Branch, Department, ImportSession, Lecture, LectureSchedule, LectureSubtopic, Section, Semester,
    Subject, TeachingPlan, User,
)
from app.schemas import requests as rq
from app.services import audit_service, conflict_service, notification_service, report_service, scope_service


def get_plan(db: Session, plan_id: uuid.UUID) -> TeachingPlan:
    plan = db.get(TeachingPlan, plan_id)
    if not plan:
        raise NotFound("Teaching plan not found.")
    return plan


def find_duplicate(db: Session, *, subject_id, section_id, semester_id, exclude_id=None) -> TeachingPlan | None:
    stmt = select(TeachingPlan).where(
        TeachingPlan.subject_id == subject_id, TeachingPlan.section_id == section_id,
        TeachingPlan.semester_id == semester_id, TeachingPlan.status != PlanStatus.ARCHIVED,
    )
    if exclude_id:
        stmt = stmt.where(TeachingPlan.id != exclude_id)
    return db.scalar(stmt)


def create_plan(db: Session, admin: User, data: rq.TeachingPlanCreate) -> TeachingPlan:
    year = db.get(AcademicYear, data.academic_year_id)
    sem = db.get(Semester, data.semester_id)
    dept = db.get(Department, data.department_id)
    br = db.get(Branch, data.branch_id)
    sec = db.get(Section, data.section_id)
    sub = db.get(Subject, data.subject_id)
    prof = db.get(User, data.professor_id)
    missing = [label for label, obj in (("Academic year", year), ("Semester", sem), ("Department", dept), ("Branch", br),
                                        ("Section", sec), ("Subject", sub), ("Professor", prof)) if obj is None]
    if missing:
        raise NotFound(f"{', '.join(missing)} not found.")

    # Relationship integrity: every selection must belong to the one above it.
    if sem.academic_year_id != year.id:
        raise BusinessRuleViolation(f"{sem.name} does not belong to {year.name}.", code="INVALID_ASSIGNMENT")
    if br.department_id != dept.id:
        raise BusinessRuleViolation(f"{br.name} is not part of {dept.name}.", code="INVALID_ASSIGNMENT")
    if sec.branch_id != br.id or sec.semester_id != sem.id:
        raise BusinessRuleViolation(f"Section {sec.name} is not a {br.code} section in {sem.name}.", code="INVALID_ASSIGNMENT")
    if sub.branch_id != br.id:
        raise BusinessRuleViolation(f"{sub.name} is not offered by {br.name}.", code="INVALID_ASSIGNMENT")
    if sub.semester_number != sem.number:
        raise BusinessRuleViolation(f"{sub.name} is a semester {sub.semester_number} subject, not {sem.name}.", code="INVALID_ASSIGNMENT")
    if prof.role_code != Role.PROFESSOR or not prof.is_active:
        raise BusinessRuleViolation(f"{prof.full_name} is not an active professor.", code="INVALID_FACULTY")
    if not scope_service.eligible_professor(prof, sub.id):
        raise BusinessRuleViolation(f"{prof.full_name} is not marked as eligible to teach {sub.name}. "
                                    "Add the subject to the professor's account in User Management first.", code="PROFESSOR_NOT_ELIGIBLE")

    sprint = None
    if data.sprint_plan_id:
        from app.models import SemesterSprintPlan
        sprint = db.get(SemesterSprintPlan, data.sprint_plan_id)
        if not sprint or sprint.status == "ARCHIVED":
            raise NotFound("Sprint plan not found or archived.")

    dup = find_duplicate(db, subject_id=sub.id, section_id=sec.id, semester_id=sem.id)
    if dup:
        raise Conflict(
            f"A teaching plan for {sub.name}, {sem.name} Section {sec.name} already exists ({dup.status.title()}).",
            code="DUPLICATE_PLAN", details={"plan_id": str(dup.id), "name": dup.name, "status": dup.status},
        )

    plan = TeachingPlan(
        name=data.name or f"{sub.name} – {sem.name} – Section {sec.name}",
        academic_year_id=year.id, semester_id=sem.id, department_id=dept.id, branch_id=br.id, section_id=sec.id,
        subject_id=sub.id, professor_id=prof.id, status=PlanStatus.DRAFT, created_by_id=admin.id,
        room=data.room or None, classes_per_week=data.classes_per_week, labs_per_week=data.labs_per_week,
        lab_room=data.lab_room or None, sprint_plan_id=sprint.id if sprint else None,
    )
    db.add(plan)
    db.flush()
    audit_service.record(db, actor=admin, action="plan.created", entity_type="teaching_plan", entity_id=plan.id,
                         summary=f"Created teaching plan {plan.name} for {prof.full_name}.",
                         new={"name": plan.name, "professor": prof.full_name}, scope_type="teaching_plan", scope_id=plan.id)
    db.commit()
    db.refresh(plan)
    return plan


def list_plans(db: Session, *, status: str | None = None, semester_id=None, academic_year_id=None, branch_id=None,
               section_id=None, subject_id=None, professor_id=None, q: str | None = None) -> list[dict]:
    stmt = select(TeachingPlan).order_by(TeachingPlan.updated_at.desc())
    filters = {TeachingPlan.semester_id: semester_id, TeachingPlan.academic_year_id: academic_year_id,
               TeachingPlan.branch_id: branch_id, TeachingPlan.section_id: section_id,
               TeachingPlan.subject_id: subject_id, TeachingPlan.professor_id: professor_id}
    for col, val in filters.items():
        if val:
            stmt = stmt.where(col == val)
    if status:
        stmt = stmt.where(TeachingPlan.status.in_(status.split(",")))
    plans = list(db.scalars(stmt))
    if q:
        needle = q.lower()
        plans = [p for p in plans if needle in f"{p.name} {p.subject.code} {p.professor.full_name}".lower()]
    if not plans:
        return []
    counts = dict(db.execute(select(Lecture.teaching_plan_id, func.count(Lecture.id))
                             .where(Lecture.teaching_plan_id.in_([p.id for p in plans])).group_by(Lecture.teaching_plan_id)).all())
    progress = {r["plan_id"]: r for r in report_service.subject_progress(
        report_service.facts(db, statuses=tuple(PlanStatus)) if len(plans) > 1 else
        report_service.facts(db, plan_id=plans[0].id, statuses=tuple(PlanStatus)))}
    from app.services.serializers import plan_brief

    return [plan_brief(p) | {"lecture_count": counts.get(p.id, 0), "metrics": progress.get(str(p.id))} for p in plans]


def plan_detail(db: Session, plan: TeachingPlan) -> dict:
    from app.services.serializers import import_session, plan_brief

    items = report_service.facts(db, plan_id=plan.id, statuses=tuple(PlanStatus))
    sessions = list(db.scalars(select(ImportSession).where(ImportSession.teaching_plan_id == plan.id)
                               .order_by(ImportSession.created_at.desc())))
    return plan_brief(plan) | {
        "metrics": report_service.summarize(items),
        "units": report_service.unit_progress(items),
        "adherence": report_service.schedule_adherence(items),
        "definitions": report_service.METRIC_DEFINITIONS,
        "import_sessions": [import_session(s, include_draft=False) for s in sessions],
    }


def plan_lectures(db: Session, plan_id: uuid.UUID) -> list[Lecture]:
    return list(db.scalars(
        select(Lecture).where(Lecture.teaching_plan_id == plan_id)
        .options(selectinload(Lecture.subtopics), selectinload(Lecture.schedule), selectinload(Lecture.progress))
        .order_by(Lecture.sequence)
    ))


def change_status(db: Session, admin: User, plan: TeachingPlan, data: rq.PlanStatusChange) -> TeachingPlan:
    old = plan.status
    if data.status == PlanStatus.PUBLISHED:
        if plan.status != PlanStatus.READY:
            raise BusinessRuleViolation("Only a plan that is Ready (imported but not published) can be published here.")
        if not db.scalar(select(func.count(Lecture.id)).where(Lecture.teaching_plan_id == plan.id)):
            raise BusinessRuleViolation("The plan has no lectures yet. Import lectures before publishing.")
        ensure_publishable(db, plan)
        plan.status, plan.published_at, plan.published_by_id = PlanStatus.PUBLISHED, now_utc(), admin.id
        notify_published(db, plan)
    elif data.status == PlanStatus.ARCHIVED:
        if plan.status == PlanStatus.ARCHIVED:
            raise Conflict("The plan is already archived.")
        if not data.reason:
            raise BusinessRuleViolation("Give a reason for archiving the plan.")
        plan.status, plan.archived_at = PlanStatus.ARCHIVED, now_utc()
    audit_service.record(db, actor=admin, action=f"plan.{data.status.lower()}", entity_type="teaching_plan", entity_id=plan.id,
                         summary=f"{'Published' if data.status == PlanStatus.PUBLISHED else 'Archived'} {plan.name}."
                                 + (f" Reason: {data.reason}" if data.reason else ""),
                         old={"status": old}, new={"status": plan.status}, scope_type="teaching_plan", scope_id=plan.id)
    db.commit()
    return plan


def ensure_publishable(db: Session, plan: TeachingPlan) -> list[dict]:
    """Refuse to publish while a professor would be in two classes at once. Returns the remaining (room) warnings."""
    found = conflict_service.plan_conflicts(db, plan)
    blocking = conflict_service.blocking(found)
    if blocking:
        raise Conflict("Schedule conflict: " + blocking[0]["message"]
                       + (f" ({len(blocking) - 1} more.)" if len(blocking) > 1 else "")
                       + " Assign another professor or change the time before publishing.",
                       code="SCHEDULE_CONFLICT", details={"conflicts": blocking})
    return [c for c in found if c["level"] != "ERROR"]


def notify_published(db: Session, plan: TeachingPlan, lecture_count: int | None = None) -> None:
    """Every professor who teaches at least one lecture of the plan is told it is now on their dashboard."""
    counts: dict[uuid.UUID, int] = {}
    for lec in plan.lectures:
        if not lec.is_cancelled:
            counts[lec.effective_professor_id] = counts.get(lec.effective_professor_id, 0) + 1
    counts.setdefault(plan.professor_id, lecture_count or 0)
    for pid, n in counts.items():
        notification_service.notify(db, pid, kind="plan.published", title=f"Sprint Plan Published: {plan.subject.name}",
                                    body=f"{plan.name}: {n} lecture{'s' if n != 1 else ''} assigned to you.",
                                    link=f"/professor/sprint-plan")


def _allocation_clash(db: Session, lecture: Lecture) -> None:
    """After an allocation change on a published plan: the professor must be free at that time."""
    slot = conflict_service.lecture_slot(lecture)
    if not slot or lecture.teaching_plan.status != PlanStatus.PUBLISHED:
        return
    found = conflict_service.blocking(conflict_service.clashes(slot, conflict_service.published_slots(db, slot.on, slot.on)))
    if found:
        raise Conflict("Schedule conflict: " + found[0]["message"], code="SCHEDULE_CONFLICT", details={"conflicts": found})


def correct_lecture(db: Session, admin: User, lecture: Lecture, data: rq.LectureCorrection) -> Lecture:
    """Controlled edit of master data after publishing - reason required, full before/after audit."""
    plan = lecture.teaching_plan
    if plan.status == PlanStatus.ARCHIVED:
        raise Conflict("Archived plans cannot be changed.")
    sch = lecture.schedule or LectureSchedule(lecture_id=lecture.id)

    def snapshot() -> dict:
        return {
            "content_topic": lecture.content_topic, "unit_no": lecture.unit_no, "blooms_taxonomy": lecture.blooms_taxonomy,
            "lecture_type": lecture.lecture_type, "planned_date": sch.planned_date,
            "planned_start_time": sch.planned_start_time.strftime("%H:%M") if sch.planned_start_time else None,
            "planned_end_time": sch.planned_end_time.strftime("%H:%M") if sch.planned_end_time else None,
            "subtopics": [s.title for s in lecture.subtopics],
            "professor": lecture.effective_professor.full_name, "room": sch.room or plan.room,
        }

    before = snapshot()
    old_professor_id = lecture.effective_professor_id
    fields = data.model_dump(exclude_unset=True, exclude={"reason"})
    if "lecture_type" in fields and fields["lecture_type"] not in LectureType.__members__:
        raise BusinessRuleViolation("Unknown lecture type.")
    for key in ("content_topic", "unit_no", "blooms_taxonomy", "lecture_type"):
        if key in fields:
            setattr(lecture, key, fields[key])
    if "planned_date" in fields:
        sch.planned_date = fields["planned_date"]
    if "planned_start_time" in fields:
        sch.planned_start_time = time.fromisoformat(fields["planned_start_time"]) if fields["planned_start_time"] else None
    if "planned_end_time" in fields:
        sch.planned_end_time = time.fromisoformat(fields["planned_end_time"]) if fields["planned_end_time"] else None
    if sch.planned_start_time and sch.planned_end_time and sch.planned_end_time <= sch.planned_start_time:
        raise BusinessRuleViolation("End time must be after start time.")
    if "room" in fields:
        sch.room = (fields["room"] or "").strip() or None
    if fields.get("professor_id"):
        prof = db.get(User, fields["professor_id"])
        if not prof or prof.role_code != Role.PROFESSOR or not prof.is_active:
            raise BusinessRuleViolation("Choose an active professor account.", code="INVALID_FACULTY")
        if lecture.progress and (lecture.progress.professor_started_at or lecture.progress.submission_count):
            raise Conflict("This lecture has already been started or submitted; its professor can no longer be changed.",
                           code="LECTURE_LOCKED")
        lecture.professor_id = None if prof.id == plan.professor_id else prof.id
        if lecture.progress:
            lecture.progress.professor_id = prof.id
    lecture.schedule = sch
    if "subtopics" in fields and fields["subtopics"] is not None:
        titles = [t.strip() for t in fields["subtopics"] if t and t.strip()]
        existing = {s.position: s for s in lecture.subtopics}
        for pos, title in enumerate(titles, start=1):
            if pos in existing:
                existing[pos].title = title  # keep the row so professor coverage ticks survive a rename
            else:
                lecture.subtopics.append(LectureSubtopic(position=pos, title=title))
        for pos, sub in existing.items():
            if pos > len(titles):
                lecture.subtopics.remove(sub)
    db.flush()
    db.refresh(lecture)
    sch = lecture.schedule
    old, new = audit_service.diff(before, snapshot())
    if not new:
        raise BusinessRuleViolation("Nothing was changed.")
    if {"professor", "planned_date", "planned_start_time", "planned_end_time"} & set(new):
        _allocation_clash(db, lecture)
    audit_service.record(db, actor=admin, action="lecture.corrected", entity_type="lecture", entity_id=lecture.id,
                         summary=f"Corrected Lecture {lecture.lecture_no} of {plan.name}. Reason: {data.reason}",
                         old=old, new=new, scope_type="teaching_plan", scope_id=plan.id)
    if plan.status == PlanStatus.PUBLISHED:
        subject = plan.subject.short_name or plan.subject.code
        new_professor_id = lecture.effective_professor_id
        notification_service.notify(db, new_professor_id, kind="lecture.corrected",
                                    title=(f"{subject} Lecture {lecture.lecture_no} assigned to you" if new_professor_id != old_professor_id
                                           else f"Lecture {lecture.lecture_no} was updated by the administrator"),
                                    body=f"{', '.join(k.replace('_', ' ') for k in new)} changed. Reason: {data.reason}",
                                    link=f"/professor/lectures/{lecture.id}")
        if new_professor_id != old_professor_id:
            notification_service.notify(db, old_professor_id, kind="lecture.corrected",
                                        title=f"{subject} Lecture {lecture.lecture_no} reassigned",
                                        body=f"This lecture is now taught by {lecture.effective_professor.full_name}. Reason: {data.reason}",
                                        link="/professor/sprint-plan")
    db.commit()
    return lecture


def activity(db: Session, plan_id: uuid.UUID, limit: int = 100) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).where(AuditLog.scope_type == "teaching_plan", AuditLog.scope_id == plan_id)
                           .order_by(AuditLog.created_at.desc()).limit(limit)))


def set_allocation(db: Session, admin: User, plan_id: uuid.UUID, data: rq.PlanAllocation) -> TeachingPlan:
    plan = get_plan(db, plan_id)
    if plan.status == PlanStatus.ARCHIVED:
        raise Conflict("This plan is archived.", code="PLAN_ARCHIVED")
    before = {"classes_per_week": plan.classes_per_week, "labs_per_week": plan.labs_per_week, "room": plan.room, "lab_room": plan.lab_room}
    plan.classes_per_week, plan.labs_per_week = data.classes_per_week, data.labs_per_week
    plan.room, plan.lab_room = (data.room or "").strip() or None, (data.lab_room or "").strip() or None
    after = {"classes_per_week": plan.classes_per_week, "labs_per_week": plan.labs_per_week, "room": plan.room, "lab_room": plan.lab_room}
    old, new = audit_service.diff(before, after)
    if new:
        audit_service.record(db, actor=admin, action="plan.allocation_changed", entity_type="teaching_plan", entity_id=plan.id,
                             summary=f"Changed the weekly allocation of {plan.name}.", old=old, new=new,
                             scope_type="teaching_plan", scope_id=plan.id)
    db.commit()
    db.refresh(plan)
    return plan
