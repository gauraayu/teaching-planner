"""Professor workflow: derived task lists, lecture execution updates and submission.

Tasks are not stored. They are derived from the published schedule + progress:
    plan.professor = me AND plan.status = PUBLISHED AND schedule.planned_date ...
"""
from __future__ import annotations

import uuid
from datetime import date, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core import clock
from app.core.enums import (
    LEVEL_LABELS, LEVEL_ROLE, VERIFICATION_CHAIN, ExecutionStatus, MaterialType, PlanStatus, Role, SubmissionStatus, VerificationStatus,
)
from app.core.errors import BusinessRuleViolation, Conflict, NotFound, PermissionDenied
from app.models import (
    Assignment, Lecture, LectureMaterial, LectureProgress, LectureSchedule, LectureSubtopicProgress, TeachingPlan, User,
    Verification,
)
from app.schemas import requests as rq
from app.services import audit_service, notification_service, report_service
from app.services import serializers as ser

def _session_brief(lec: Lecture) -> dict | None:
    from app.services.operations_service import session_brief  # local import: operations_service imports serializers too
    return session_brief(lec.class_session)


def _class_date(lec: Lecture) -> str | None:
    from app.services.operations_service import class_date
    d = class_date(lec)
    return d.isoformat() if d else None


def _sprint_change(db: Session, lec: Lecture) -> dict | None:
    """The latest published weekly revision that changed this lecture (shown as "Updated · v2")."""
    from app.services import sprint_service
    item = sprint_service._latest_published_items(db, [lec.id]).get(lec.id)
    if not item:
        return None
    names = sprint_service._names(db, [item.old_values, item.new_values])
    return sprint_service.item_view(item, names)


EDITABLE_SUBMISSION_STATES = (SubmissionStatus.DRAFT, SubmissionStatus.CORRECTION_REQUIRED)
SUBMITTABLE_EXECUTION = (ExecutionStatus.COMPLETED, ExecutionStatus.PARTIALLY_COMPLETED)


# ------------------------------------------------------------------ tasks

def _my_lectures(db: Session, professor_id: uuid.UUID):
    return (
        select(Lecture)
        .join(TeachingPlan, Lecture.teaching_plan_id == TeachingPlan.id)
        .join(LectureSchedule, LectureSchedule.lecture_id == Lecture.id)
        # A weekly sprint revision can hand one lecture to a substitute; cancelled lectures are nobody's task.
        .where(func.coalesce(Lecture.professor_id, TeachingPlan.professor_id) == professor_id,
               TeachingPlan.status == PlanStatus.PUBLISHED, Lecture.is_cancelled.is_(False), Lecture.is_released.is_(True))
        .options(selectinload(Lecture.subtopics), selectinload(Lecture.schedule), selectinload(Lecture.progress),
                 selectinload(Lecture.teaching_plan))
    )


def task_card(lec: Lecture) -> dict:
    plan = lec.teaching_plan
    pr = lec.progress
    data = ser.lecture(lec)
    execution = pr.execution_status if pr else ExecutionStatus.SCHEDULED.value
    today = clock.today()
    effective = pr.rescheduled_to if (pr and pr.execution_status == ExecutionStatus.RESCHEDULED and pr.rescheduled_to) else (
        lec.schedule.planned_date if lec.schedule else None)
    covered = sum(1 for s in (pr.subtopic_progress if pr else []) if s.is_covered)
    return data | {
        "plan": {"id": str(plan.id), "name": plan.name, "section": plan.section.name, "semester": plan.semester.name},
        "room": (lec.schedule.room if lec.schedule else None) or plan.room,
        "origin": lec.origin, "is_cancelled": lec.is_cancelled,
        "subject": {"id": str(plan.subject.id), "code": plan.subject.code, "name": plan.subject.name, "short_name": plan.subject.short_name},
        "execution_status": execution,
        "submission_status": pr.submission_status if pr else None,
        "effective_date": effective.isoformat() if effective else None,
        "is_overdue": bool(effective and effective < today and execution not in SUBMITTABLE_EXECUTION),
        "subtopics_covered": covered,
    }


def tasks(db: Session, professor: User, category: str, *, days: int = 14, limit: int = 50) -> list[dict]:
    today = clock.today()
    base = _my_lectures(db, professor.id)
    open_states = (ExecutionStatus.SCHEDULED, ExecutionStatus.IN_PROGRESS, ExecutionStatus.RESCHEDULED)
    prog = select(LectureProgress.lecture_id)

    if category == "today":
        stmt = base.where(LectureSchedule.planned_date == today)
        order = (LectureSchedule.planned_start_time,)
    elif category == "upcoming":
        stmt = base.where(LectureSchedule.planned_date > today, LectureSchedule.planned_date <= today + timedelta(days=days))
        order = (LectureSchedule.planned_date, LectureSchedule.planned_start_time)
    elif category == "overdue":
        not_done = ~Lecture.id.in_(prog.where(LectureProgress.execution_status.notin_(open_states)))
        stmt = base.where(LectureSchedule.planned_date < today, not_done)
        order = (LectureSchedule.planned_date,)
    elif category == "completed":
        done = Lecture.id.in_(prog.where(LectureProgress.execution_status.in_(SUBMITTABLE_EXECUTION)))
        stmt = base.where(done)
        order = (LectureSchedule.planned_date.desc(),)
    elif category == "corrections":
        stmt = base.where(Lecture.id.in_(prog.where(LectureProgress.submission_status == SubmissionStatus.CORRECTION_REQUIRED)))
        order = (LectureSchedule.planned_date,)
    else:
        raise NotFound("Unknown task category.")
    lectures = db.scalars(stmt.order_by(*order).limit(limit)).unique().all()
    cards = [task_card(lec) for lec in lectures]
    if category == "overdue":
        # A lecture rescheduled to a future date is no longer overdue - it shows under upcoming instead.
        cards = [c for c in cards if c["is_overdue"]]
    return cards


def dashboard(db: Session, professor: User) -> dict:
    """Everything on the professor's home screen, computed from stored records - nothing is hard-coded."""
    from app.services import sprint_service

    items = report_service.facts(db, professor_id=professor.id)
    today = clock.today()
    summary = report_service.summarize(items)
    plans = report_service.subject_progress(items)

    todays = [sprint_service.lecture_row(l) for l in db.scalars(
        _my_lectures(db, professor.id).where(LectureSchedule.planned_date == today)
        .order_by(LectureSchedule.planned_start_time)).unique()]

    # --- action items: only things the professor must do
    actions: list[dict] = []
    for c in tasks(db, professor, "corrections", limit=20):
        lec = db.get(Lecture, uuid.UUID(c["id"]))
        last = next((v for v in reversed(lec.progress.verifications) if v.status == VerificationStatus.CORRECTION_REQUIRED), None)
        actions.append({"kind": "CORRECTION", "lecture_id": c["id"], "title": f"Lecture {c['lecture_no']} · {c['content_topic']}",
                        "subject": c["subject"]["short_name"] or c["subject"]["code"],
                        "detail": f"{LEVEL_LABELS.get(last.verification_level, last.verification_level)} remark: {last.remarks}" if last else "A verifier asked for a correction.",
                        "by": last.verifier.full_name if last and last.verifier else None,
                        "at": ser._iso(last.verified_at) if last else None, "action": "Fix record"})
    for c in tasks(db, professor, "overdue", limit=20):
        actions.append({"kind": "PENDING_LOG", "lecture_id": c["id"], "title": f"Lecture {c['lecture_no']} · {c['content_topic']}",
                        "subject": c["subject"]["short_name"] or c["subject"]["code"],
                        "detail": "Lecture execution has not been recorded.", "by": None, "at": c["effective_date"], "action": "Update now"})
    drafts = db.scalars(_my_lectures(db, professor.id).join(LectureProgress, LectureProgress.lecture_id == Lecture.id)
                        .where(LectureProgress.execution_status.in_(SUBMITTABLE_EXECUTION),
                               LectureProgress.submission_status == SubmissionStatus.DRAFT)
                        .order_by(LectureSchedule.planned_date).limit(20)).unique().all()
    for lec in drafts:
        plan = lec.teaching_plan
        missing_notes = not any(m.material_type == MaterialType.LECTURE_NOTES for m in lec.progress.materials)
        actions.append({"kind": "MISSING_ASSET" if missing_notes else "NOT_SUBMITTED", "lecture_id": str(lec.id),
                        "title": f"Lecture {lec.lecture_no} · {lec.content_topic}",
                        "subject": plan.subject.short_name or plan.subject.code,
                        "detail": "Lecture notes link is missing and the record is not submitted." if missing_notes
                        else "Saved as a draft. Submit it for verification.",
                        "by": None, "at": ser._iso(lec.progress.actual_completion_date), "action": "Add link" if missing_notes else "Submit"})

    # --- verification pipeline: the most recent submission still moving through CL/CH -> OM
    latest = db.scalars(select(LectureProgress).where(LectureProgress.professor_id == professor.id, LectureProgress.submitted_at.is_not(None))
                        .order_by(LectureProgress.submitted_at.desc()).limit(1)).first()
    pipeline = None
    if latest:
        lec = latest.lecture
        plan = lec.teaching_plan
        current = [v for v in latest.verifications if v.round == latest.submission_count and v.status != VerificationStatus.SUPERSEDED
                   and v.verification_level in VERIFICATION_CHAIN]
        pipeline = {"lecture_id": str(lec.id), "lecture_no": lec.lecture_no, "topic": lec.content_topic,
                    "subject": plan.subject.short_name or plan.subject.code, "submission_status": latest.submission_status,
                    "submitted_at": ser._iso(latest.submitted_at), "round": latest.submission_count,
                    "chain": [lvl.value for lvl in VERIFICATION_CHAIN],
                    "steps": [{"verification_level": v.verification_level, "status": v.status, "round": v.round,
                               "verified_at": ser._iso(v.verified_at)} for v in current]}
    from app.models import AuditLog
    my_progress = select(LectureProgress.id).where(LectureProgress.professor_id == professor.id)
    my_verifications = select(Verification.id).where(Verification.lecture_progress_id.in_(my_progress))
    recent = db.scalars(
        select(AuditLog).where(AuditLog.action.notin_(("auth.demo_login", "auth.login"))).where(
            (AuditLog.actor_id == professor.id)
            | ((AuditLog.entity_type == "lecture_progress") & AuditLog.entity_id.in_(my_progress))
            | ((AuditLog.entity_type == "verification") & AuditLog.entity_id.in_(my_verifications)))
        .order_by(AuditLog.created_at.desc()).limit(5)).all()

    syllabus = []
    for p in plans:
        mine = [f for f in items if str(f.plan_id) == p["plan_id"]]
        syllabus.append(p | {"units": report_service.unit_progress(mine)})

    return {
        "today": today.isoformat(),
        "counts": {
            "today": len(todays),
            "today_completed": sum(1 for r in todays if r["execution_status"] in SUBMITTABLE_EXECUTION),
            "pending": summary["pending"],
            "overdue": sum(1 for a in actions if a["kind"] == "PENDING_LOG"),
            "completed": summary["completed"],
            "partial": summary["partial"],
            "total": summary["total"],
            "corrections": summary["correction_required"],
            "awaiting_verification": summary["awaiting_verification"],
            "verified": summary["verified"],
            "pending_updates": len(actions),
            "course_progress_pct": summary["execution_pct"],
        },
        "courses": plans,
        "schedule_today": todays,
        "action_items": actions,
        "pipeline": pipeline,
        "recent": [ser.audit_entry(a) for a in recent],
        "syllabus": syllabus,
    }


def course_view(db: Session, professor: User, plan_id: uuid.UUID) -> dict:
    plan = db.get(TeachingPlan, plan_id)
    if not plan or plan.professor_id != professor.id or plan.status != PlanStatus.PUBLISHED:
        raise NotFound("Course not found in your assigned plans.")
    # Only this professor's own lectures: one reallocated to a colleague is that colleague's record now.
    items = report_service.facts(db, plan_id=plan.id, professor_id=professor.id)
    lectures = db.scalars(_my_lectures(db, professor.id).where(Lecture.teaching_plan_id == plan.id).order_by(Lecture.sequence)).unique().all()
    # Lectures without a schedule row are still part of the course.
    unscheduled = db.scalars(select(Lecture).where(Lecture.teaching_plan_id == plan.id, ~Lecture.id.in_([l.id for l in lectures]),
                                                   Lecture.is_cancelled.is_(False), Lecture.professor_id.is_(None))
                             .options(selectinload(Lecture.subtopics), selectinload(Lecture.progress))).all()
    return ser.plan_brief(plan) | {
        "metrics": report_service.summarize(items),
        "units": report_service.unit_progress(items),
        "definitions": report_service.METRIC_DEFINITIONS,
        # Topics of weeks that are not published yet are part of the syllabus, but their projected slot is not shown.
        "lectures": [task_card(l) if l.is_released else task_card(l) | {"planned_date": None, "planned_start_time": None, "planned_end_time": None}
                     for l in sorted([*lectures, *unscheduled], key=lambda x: x.sequence)],
    }


def schedule(db: Session, professor: User, date_from: date, date_to: date) -> list[dict]:
    stmt = _my_lectures(db, professor.id).where(LectureSchedule.planned_date.between(date_from, date_to)) \
        .order_by(LectureSchedule.planned_date, LectureSchedule.planned_start_time)
    return [task_card(l) for l in db.scalars(stmt).unique().all()]


# ------------------------------------------------------------------ lecture detail & updates

def _owned_lecture(db: Session, professor: User, lecture_id: uuid.UUID) -> Lecture:
    lec = db.get(Lecture, lecture_id)
    if not lec:
        raise NotFound("Lecture not found.")
    plan = lec.teaching_plan
    if lec.effective_professor_id != professor.id:
        raise PermissionDenied("This lecture belongs to another professor's plan.")
    if lec.is_cancelled:
        raise Conflict("This lecture was cancelled in a sprint revision.", code="LECTURE_CANCELLED")
    if plan.status != PlanStatus.PUBLISHED:
        raise Conflict("This plan is not published, so its lectures cannot be updated.", code="PLAN_NOT_PUBLISHED")
    if not lec.is_released:
        raise NotFound("This class is not in a published weekly sprint plan yet.")
    return lec


def lecture_detail(db: Session, viewer: User, lecture_id: uuid.UUID) -> dict:
    lec = db.get(Lecture, lecture_id)
    if not lec:
        raise NotFound("Lecture not found.")
    pr = lec.progress
    if viewer.role_code == Role.PROFESSOR and viewer.id not in (lec.effective_professor_id, pr.professor_id if pr else None):
        raise PermissionDenied("This lecture belongs to another professor's plan.")
    from app.services import scope_service
    scope_service.require(viewer, lec.teaching_plan, "This lecture")  # CL/CH and OM: only inside their assigned scope
    covered = {str(s.subtopic_id) for s in (pr.subtopic_progress if pr else []) if s.is_covered}
    editable = viewer.role_code == Role.PROFESSOR and lec.effective_professor_id == viewer.id and not lec.is_cancelled \
        and lec.teaching_plan.status == PlanStatus.PUBLISHED and (
        not pr or pr.submission_status in EDITABLE_SUBMISSION_STATES)
    open_correction = None
    if pr and pr.submission_status == SubmissionStatus.CORRECTION_REQUIRED:
        last = next((v for v in reversed(pr.verifications) if v.status == VerificationStatus.CORRECTION_REQUIRED), None)
        open_correction = ser.verification(last) if last else None
    return task_card(lec) | {
        "master": {
            "subject": lec.teaching_plan.subject.name, "lecture_no": lec.lecture_no, "lecture_type": lec.lecture_type,
            "unit_no": lec.unit_no, "content_topic": lec.content_topic, "blooms_taxonomy": lec.blooms_taxonomy,
            "planned_date": lec.schedule.planned_date.isoformat() if lec.schedule and lec.schedule.planned_date else None,
            "planned_start_time": ser._hm(lec.schedule.planned_start_time) if lec.schedule else None,
            "planned_end_time": ser._hm(lec.schedule.planned_end_time) if lec.schedule else None,
            "subtopics": [{"id": str(s.id), "position": s.position, "title": s.title} for s in lec.subtopics],
        },
        "execution": None if not pr else {
            "id": str(pr.id), "execution_status": pr.execution_status, "submission_status": pr.submission_status,
            "actual_completion_date": ser._iso(pr.actual_completion_date), "rescheduled_to": ser._iso(pr.rescheduled_to),
            "remarks": pr.remarks, "recording_url": pr.recording_url, "additional_topics": pr.additional_topics,
            "shared_with_students": pr.shared_with_students, "shared_at": ser._iso(pr.shared_at),
            "not_shared_reason": pr.not_shared_reason, "submitted_at": ser._iso(pr.submitted_at),
            "submission_count": pr.submission_count, "covered_subtopic_ids": sorted(covered),
            "notes": [ser.material(m) for m in pr.materials if m.material_type == MaterialType.LECTURE_NOTES],
            "evidence": [ser.material(m) for m in pr.materials if m.material_type in (MaterialType.CLASS_EVIDENCE, MaterialType.CHECKIN_IMAGE)],
            "professor_started_at": ser._iso(pr.professor_started_at), "professor_ended_at": ser._iso(pr.professor_ended_at),
            "checkin_mode": pr.checkin_mode,
            "assignment": ser.assignment(pr.assignment), "updated_at": ser._iso(pr.updated_at),
        },
        "verifications": [ser.verification(v) for v in (pr.verifications if pr else [])],
        "verification_chain": [lvl.value for lvl in VERIFICATION_CHAIN],
        "professor": ser.user_brief(lec.effective_professor),
        "class_session": _session_brief(lec),
        "open_correction": open_correction,
        "class_date": _class_date(lec),
        "can_start": editable and _class_date(lec) == clock.today().isoformat() and not (pr and pr.professor_started_at),
        "can_end": editable and bool(pr and pr.professor_started_at and not pr.professor_ended_at),
        "sprint_change": _sprint_change(db, lec),
        "can_edit": editable,
        "can_submit": editable and bool(pr) and pr.execution_status in SUBMITTABLE_EXECUTION,
    }


def _apply_rules(data: rq.ProgressUpdate, lec: Lecture) -> None:
    today = clock.today()
    subtopic_ids = {s.id for s in lec.subtopics}
    unknown = set(data.covered_subtopic_ids) - subtopic_ids
    if unknown:
        raise BusinessRuleViolation("Some covered subtopics do not belong to this lecture.", code="INVALID_SUBTOPIC")
    if data.actual_completion_date and data.actual_completion_date > today:
        raise BusinessRuleViolation("The actual completion date cannot be in the future.", code="FUTURE_DATE")
    if data.execution_status == ExecutionStatus.COMPLETED:
        if subtopic_ids and set(data.covered_subtopic_ids) != subtopic_ids:
            raise BusinessRuleViolation("Not every subtopic is ticked. Tick them all, or mark the lecture Partially Completed.",
                                        code="SUBTOPICS_INCOMPLETE")
    if data.execution_status == ExecutionStatus.PARTIALLY_COMPLETED and subtopic_ids and not data.covered_subtopic_ids:
        raise BusinessRuleViolation("Tick at least one covered subtopic for a partially completed lecture.", code="SUBTOPICS_NONE")
    if data.execution_status == ExecutionStatus.NOT_CONDUCTED and not (data.remarks or "").strip():
        raise BusinessRuleViolation("Say why the class was not conducted.", code="REMARKS_REQUIRED")
    if data.execution_status == ExecutionStatus.RESCHEDULED:
        if not data.rescheduled_to:
            raise BusinessRuleViolation("Choose the new date for the rescheduled lecture.", code="RESCHEDULE_DATE_REQUIRED")
        if data.rescheduled_to < today:
            raise BusinessRuleViolation("The new date cannot be in the past.", code="RESCHEDULE_DATE_PAST")
    if data.shared_with_students is False and not (data.not_shared_reason or "").strip():
        raise BusinessRuleViolation("Give a reason why the notes were not shared with students.", code="NOT_SHARED_REASON_REQUIRED")
    a = data.assignment
    if a and a.shared_with_students is False and not (a.not_shared_reason or "").strip():
        raise BusinessRuleViolation("Give a reason why the assignment was not shared with students.", code="NOT_SHARED_REASON_REQUIRED")


def save_progress(db: Session, professor: User, lecture_id: uuid.UUID, data: rq.ProgressUpdate) -> dict:
    lec = _owned_lecture(db, professor, lecture_id)
    pr = lec.progress
    if pr and pr.submission_status not in EDITABLE_SUBMISSION_STATES:
        raise Conflict("This update has been submitted for verification and is locked until a verifier requests a correction.",
                       code="PROGRESS_LOCKED")
    _apply_rules(data, lec)
    now = clock.now_utc()
    created = pr is None
    if created:
        pr = LectureProgress(lecture_id=lec.id, professor_id=professor.id, submission_status=SubmissionStatus.DRAFT)
        db.add(pr)
    before = {"execution_status": pr.execution_status, "actual_completion_date": pr.actual_completion_date,
              "shared_with_students": pr.shared_with_students, "rescheduled_to": pr.rescheduled_to}

    pr.execution_status = data.execution_status
    pr.actual_completion_date = data.actual_completion_date if data.execution_status in SUBMITTABLE_EXECUTION else None
    pr.rescheduled_to = data.rescheduled_to if data.execution_status == ExecutionStatus.RESCHEDULED else None
    pr.remarks = data.remarks
    pr.recording_url = str(data.recording_url) if data.recording_url else None
    pr.additional_topics = (data.additional_topics or "").strip() or None
    pr.shared_with_students = data.shared_with_students
    pr.not_shared_reason = data.not_shared_reason if data.shared_with_students is False else None
    if data.shared_with_students and not pr.shared_at:
        pr.shared_at = now
    elif not data.shared_with_students:
        pr.shared_at = None

    covered = set(data.covered_subtopic_ids)
    existing = {s.subtopic_id: s for s in pr.subtopic_progress}
    for sub in lec.subtopics:
        row = existing.get(sub.id)
        if row is None:
            pr.subtopic_progress.append(LectureSubtopicProgress(subtopic_id=sub.id, is_covered=sub.id in covered))
        else:
            row.is_covered = sub.id in covered

    # Notes: the submitted list is the new truth; unchanged items keep their original upload time.
    keep = {m.id: m for m in pr.materials if m.material_type == MaterialType.LECTURE_NOTES}
    incoming_ids = {n.id for n in data.notes if n.id}
    for m in list(pr.materials):
        if m.material_type == MaterialType.LECTURE_NOTES and m.id not in incoming_ids:
            pr.materials.remove(m)
    for n in data.notes:
        if n.id and n.id in keep:
            keep[n.id].title, keep[n.id].file_url = n.title, str(n.file_url)
        else:
            pr.materials.append(LectureMaterial(material_type=MaterialType.LECTURE_NOTES, title=n.title, file_url=str(n.file_url),
                                                file_name=str(n.file_url).rsplit("/", 1)[-1][:255] or None,
                                                uploaded_by_id=professor.id, uploaded_at=now))

    if data.assignment:
        a = pr.assignment or Assignment(created_by_id=professor.id)
        a.title, a.description = data.assignment.title, data.assignment.description
        a.link_url = str(data.assignment.link_url) if data.assignment.link_url else None
        a.due_date = data.assignment.due_date
        a.shared_with_students = data.assignment.shared_with_students
        a.not_shared_reason = data.assignment.not_shared_reason if data.assignment.shared_with_students is False else None
        if a.shared_with_students and not a.shared_at:
            a.shared_at = now
        elif not a.shared_with_students:
            a.shared_at = None
        pr.assignment = a
    elif pr.assignment is not None:
        pr.assignment = None

    db.flush()
    after = {"execution_status": pr.execution_status, "actual_completion_date": pr.actual_completion_date,
             "shared_with_students": pr.shared_with_students, "rescheduled_to": pr.rescheduled_to}
    old, new = audit_service.diff(before, after)
    plan = lec.teaching_plan
    if created or new:
        label = ExecutionStatus(pr.execution_status).value.replace("_", " ").lower()
        audit_service.record(db, actor=professor, action="progress.saved", entity_type="lecture_progress", entity_id=pr.id,
                             summary=f"Marked Lecture {lec.lecture_no} {label}." if "execution_status" in new
                             else f"Updated Lecture {lec.lecture_no} execution details.",
                             old=old or None, new=new or None, scope_type="teaching_plan", scope_id=plan.id)
    db.commit()
    db.expire_all()  # reload relationships (progress, verifications) changed in this request
    return lecture_detail(db, professor, lec.id)


def submit(db: Session, professor: User, progress_id: uuid.UUID) -> dict:
    pr = db.scalar(select(LectureProgress).where(LectureProgress.id == progress_id).with_for_update(of=LectureProgress))
    if not pr:
        raise NotFound("Nothing has been saved for this lecture yet.")
    lec = _owned_lecture(db, professor, pr.lecture_id)
    if pr.submission_status not in EDITABLE_SUBMISSION_STATES:
        raise Conflict("This update is already with the verifiers.", code="ALREADY_SUBMITTED")
    problems = []
    if pr.execution_status not in SUBMITTABLE_EXECUTION:
        problems.append("Only completed or partially completed lectures can be submitted.")
    if not pr.actual_completion_date:
        problems.append("Add the actual completion date.")
    if pr.shared_with_students is None:
        problems.append("Say whether the lecture material was shared with students.")
    if problems:
        raise BusinessRuleViolation(" ".join(problems), code="SUBMISSION_INCOMPLETE", details={"problems": problems})

    resubmission = pr.submission_status == SubmissionStatus.CORRECTION_REQUIRED
    pr.submission_status = SubmissionStatus.RESUBMITTED if resubmission else SubmissionStatus.SUBMITTED
    pr.submitted_at = clock.now_utc()
    pr.submission_count = (pr.submission_count or 0) + 1
    first_level = VERIFICATION_CHAIN[0]
    db.add(Verification(lecture_progress_id=pr.id, round=pr.submission_count, verification_level=first_level,
                        status=VerificationStatus.PENDING))
    plan = lec.teaching_plan
    audit_service.record(db, actor=professor, action="progress.resubmitted" if resubmission else "progress.submitted",
                         entity_type="lecture_progress", entity_id=pr.id,
                         summary=f"{'Resubmitted' if resubmission else 'Submitted'} Lecture {lec.lecture_no} for verification.",
                         new={"submission_status": pr.submission_status, "round": pr.submission_count},
                         scope_type="teaching_plan", scope_id=plan.id)
    from app.services import scope_service
    notification_service.notify_many(
        db, scope_service.users_covering(db, LEVEL_ROLE[first_level], plan), kind="verification.pending",
        title=("Professor has resubmitted a corrected lecture record" if resubmission else "New Professor lecture submitted for verification"),
        body=f"{professor.full_name} · {plan.subject.short_name or plan.subject.code} Lecture {lec.lecture_no} “{lec.content_topic}”.",
        link="/verification/pending")
    db.commit()
    db.expire_all()  # reload relationships (progress, verifications) changed in this request
    return lecture_detail(db, professor, lec.id)
