"""The professor's live-class workflow and the shared "what is on today" feed.

Three different facts are kept apart on purpose:
  schedule            lecture_schedules.planned_start_time / planned_end_time
  professor's clicks  lecture_progress.professor_started_at / professor_ended_at   (this module)
  OM's observation    class_sessions.entry_at / exit_at                            (operations_service)
All timestamps written here come from the server clock, never from the browser.
"""
from __future__ import annotations

import uuid
from datetime import datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.core.enums import ExecutionStatus, MaterialType, Role, SubmissionStatus
from app.core.errors import AppError, BusinessRuleViolation, Conflict, NotFound
from app.models import Lecture, LectureMaterial, LectureProgress, Notification, User
from app.services import audit_service, operations_service, storage
from app.services.professor_service import EDITABLE_SUBMISSION_STATES, _owned_lecture, lecture_detail

MAX_IMAGES_PER_LECTURE = 12
EVIDENCE_TYPES = (MaterialType.CLASS_EVIDENCE, MaterialType.CHECKIN_IMAGE)


def _progress(db: Session, lec: Lecture, professor: User) -> LectureProgress:
    pr = lec.progress
    if pr is None:
        pr = LectureProgress(lecture_id=lec.id, professor_id=professor.id, submission_status=SubmissionStatus.DRAFT,
                             execution_status=ExecutionStatus.SCHEDULED)
        db.add(pr)
        db.flush()
    if pr.submission_status not in EDITABLE_SUBMISSION_STATES:
        raise Conflict("This lecture record has been submitted and is locked.", code="PROGRESS_LOCKED")
    return pr


def start_class(db: Session, professor: User, lecture_id: uuid.UUID, checkin: str) -> dict:
    lec = _owned_lecture(db, professor, lecture_id)
    on = operations_service.class_date(lec)
    if on != clock.today():
        raise BusinessRuleViolation(
            "A class can be started only on the day it is scheduled." if on else "This lecture has no scheduled date yet.",
            code="NOT_TODAY")
    pr = _progress(db, lec, professor)
    if pr.professor_started_at:
        raise Conflict("This class has already been started.", code="ALREADY_STARTED")
    pr.professor_started_at = clock.now_utc()
    pr.checkin_mode = checkin
    if pr.execution_status in (ExecutionStatus.SCHEDULED, ExecutionStatus.RESCHEDULED, ExecutionStatus.NOT_CONDUCTED):
        pr.execution_status, pr.rescheduled_to = ExecutionStatus.IN_PROGRESS, None
    plan = lec.teaching_plan
    audit_service.record(db, actor=professor, action="class.started", entity_type="lecture_progress", entity_id=pr.id,
                         summary=f"Started {plan.subject.short_name or plan.subject.code} Lecture {lec.lecture_no}.",
                         new={"professor_started_at": pr.professor_started_at, "checkin": checkin},
                         scope_type="teaching_plan", scope_id=plan.id)
    db.commit()
    db.expire_all()
    return lecture_detail(db, professor, lecture_id)


def end_class(db: Session, professor: User, lecture_id: uuid.UUID) -> dict:
    lec = _owned_lecture(db, professor, lecture_id)
    pr = lec.progress
    if not pr or not pr.professor_started_at:
        raise BusinessRuleViolation("Start the class first.", code="NOT_STARTED")
    if pr.professor_ended_at:
        raise Conflict("This class has already been ended.", code="ALREADY_ENDED")
    if pr.submission_status not in EDITABLE_SUBMISSION_STATES:
        raise Conflict("This lecture record has been submitted and is locked.", code="PROGRESS_LOCKED")
    pr.professor_ended_at = clock.now_utc()
    plan = lec.teaching_plan
    audit_service.record(db, actor=professor, action="class.ended", entity_type="lecture_progress", entity_id=pr.id,
                         summary=f"Ended {plan.subject.short_name or plan.subject.code} Lecture {lec.lecture_no}.",
                         new={"professor_ended_at": pr.professor_ended_at}, scope_type="teaching_plan", scope_id=plan.id)
    db.commit()
    db.expire_all()
    return lecture_detail(db, professor, lecture_id)


def add_evidence(db: Session, professor: User, lecture_id: uuid.UUID, *, data: bytes, original_name: str | None,
                 caption: str | None, kind: str) -> dict:
    lec = _owned_lecture(db, professor, lecture_id)
    if kind not in (MaterialType.CLASS_EVIDENCE.value, MaterialType.CHECKIN_IMAGE.value):
        raise AppError("Unknown evidence type.", code="EVIDENCE_KIND")
    limit = get_settings().evidence_max_mb
    if not data:
        raise AppError("The file is empty.", code="FILE_EMPTY")
    if len(data) > limit * 1024 * 1024:
        raise AppError(f"Images must be smaller than {limit} MB.", code="FILE_TOO_LARGE")
    content_type, ext = storage.sniff_image(data)
    pr = _progress(db, lec, professor)
    if sum(1 for m in pr.materials if m.material_type in EVIDENCE_TYPES) >= MAX_IMAGES_PER_LECTURE:
        raise BusinessRuleViolation(f"A lecture can have at most {MAX_IMAGES_PER_LECTURE} images.", code="TOO_MANY_IMAGES")
    stored = storage.get_image_store().save(data, folder=f"class-evidence/{lec.id}", ext=ext, content_type=content_type)
    pr.materials.append(LectureMaterial(
        material_type=kind, title=None, caption=(caption or "").strip()[:300] or None,
        file_name=(original_name or "")[-255:] or None,  # display only - never used as a path
        file_url=stored.file_url, storage_key=stored.storage_key, content_type=stored.content_type, size_bytes=stored.size_bytes,
        uploaded_by_id=professor.id, uploaded_at=clock.now_utc()))
    db.commit()
    db.expire_all()
    return lecture_detail(db, professor, lecture_id)


def remove_evidence(db: Session, professor: User, material_id: uuid.UUID) -> dict:
    m = db.get(LectureMaterial, material_id)
    if not m or m.material_type not in EVIDENCE_TYPES:
        raise NotFound("Image not found.")
    pr = m.progress
    lec = _owned_lecture(db, professor, pr.lecture_id)
    if pr.submission_status not in EDITABLE_SUBMISSION_STATES:
        raise Conflict("This lecture record has been submitted; its images can no longer be removed.", code="PROGRESS_LOCKED")
    key = m.storage_key
    pr.materials.remove(m)
    db.commit()
    if key:
        storage.get_image_store().delete(key)
    db.expire_all()
    return lecture_detail(db, professor, lec.id)


# ------------------------------------------------------------------ today's feed + alerts

def today_schedule(db: Session, user: User) -> dict:
    """Today's classes for the signed-in professor (their own) or OM (their scope). Drives countdowns and the 5-minute alert."""
    s = get_settings()
    now = clock.now_utc().astimezone(s.tz)
    role = user.role_code
    rows: list[dict] = []
    if role in (Role.PROFESSOR, Role.OM):
        rows = operations_service.classes(db, now.date(), professor_id=user.id if role == Role.PROFESSOR else None,
                                          viewer=user if role == Role.OM else None)
    lectures = {str(l.id): l for l in db.scalars(select(Lecture).where(Lecture.id.in_([uuid.UUID(r["lecture_id"]) for r in rows])))} if rows else {}
    out = []
    for r in rows:
        pr = lectures[r["lecture_id"]].progress
        out.append({
            "lecture_id": r["lecture_id"], "date": r["date"], "start": r["scheduled_start"], "end": r["scheduled_end"],
            "subject": r["subject"], "section": r["section"], "semester": r["semester"], "room": r["room"],
            "professor": r["professor"]["full_name"], "lecture_no": r["lecture_no"], "topic": r["topic"],
            "started": bool(pr and pr.professor_started_at), "entry_recorded": r["entry_time"] is not None,
            "link": f"/professor/lectures/{r['lecture_id']}" if role == Role.PROFESSOR else f"/om/today?class={r['lecture_id']}",
        })
    return {"now": now.isoformat(), "timezone": s.institution_timezone, "today": now.date().isoformat(),
            "lead_minutes": s.class_alert_lead_minutes, "role": role.value, "classes": out}


def record_alert(db: Session, user: User, lecture_id: uuid.UUID) -> dict:
    """Store the "class starts soon" alert in the notification history, once per user per class per day."""
    feed = today_schedule(db, user)
    cls = next((c for c in feed["classes"] if c["lecture_id"] == str(lecture_id)), None)
    if not cls:
        raise NotFound("This class is not on your schedule today.")
    link = cls["link"]
    marker = f"{lecture_id}:{feed['today']}"
    start_of_day = datetime.combine(clock.today(), time.min, tzinfo=get_settings().tz)
    exists = db.scalar(select(Notification.id).where(Notification.user_id == user.id, Notification.kind == "class.upcoming",
                                                    Notification.created_at >= start_of_day, Notification.body.like(f"%[{marker}]")))
    if exists:
        return {"created": False}
    subject = cls["subject"]["name"]
    who = "" if user.role_code == Role.PROFESSOR else f"{cls['professor']} · "
    db.add(Notification(user_id=user.id, kind="class.upcoming", title=f"Upcoming class: {subject} at {cls['start']}",
                        body=f"{who}Sem {cls['semester'].replace('Semester ', '')}-{cls['section']} · Room {cls['room'] or 'not set'} [{marker}]",
                        link=link))
    db.commit()
    return {"created": True}
