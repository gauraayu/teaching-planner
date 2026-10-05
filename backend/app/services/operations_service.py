"""Classroom operations for the Operations Manager (OM).

The OM does not edit the plan or the professor's update. They record what
happened at the classroom door (entry / exit) and, at the end of the chain,
give the final verification. Class state is derived from the schedule, the
clock and the recorded times - it is never stored.
"""
from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core import clock
from app.core.config import get_settings
from app.core.enums import (
    VERIFICATION_CHAIN, ClassState, DelayReason, ExecutionStatus, PlanStatus, SubmissionStatus, TimingStatus,
    VerificationLevel, VerificationStatus,
)
from app.core.errors import BusinessRuleViolation, Conflict, NotFound
from app.models import ClassSession, Lecture, LectureProgress, LectureSchedule, TeachingPlan, User
from app.schemas import requests as rq
from app.services import audit_service, scope_service
from app.services import serializers as ser

DELAY_REASON_LABELS = {
    DelayReason.PREVIOUS_CLASS_OVERRUN: "Previous class overrun",
    DelayReason.DEPARTMENTAL_MEETING: "Departmental meeting",
    DelayReason.ADMINISTRATIVE_WORK: "Administrative work",
    DelayReason.TECHNICAL_ISSUE: "Technical issue",
    DelayReason.ROOM_ISSUE: "Room issue",
    DelayReason.EMERGENCY: "Emergency",
    DelayReason.PROFESSOR_ARRIVED_LATE: "Professor arrived late",
    DelayReason.OTHER: "Other",
}


def tolerance() -> int:
    return get_settings().entry_delay_tolerance_minutes


def _local(dt: datetime | None) -> datetime | None:
    return dt.astimezone(get_settings().tz) if dt else None


def _hm(dt: datetime | None) -> str | None:
    return _local(dt).strftime("%H:%M") if dt else None


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def class_date(lec: Lecture) -> date | None:
    """The day the class is really held: the professor's rescheduled date if any, else the planned date."""
    pr = lec.progress
    if pr and pr.execution_status == ExecutionStatus.RESCHEDULED and pr.rescheduled_to:
        return pr.rescheduled_to
    return lec.schedule.planned_date if lec.schedule else None


def _state(lec: Lecture, on: date, now: datetime) -> ClassState:
    cs: ClassSession | None = lec.class_session
    today = now.date()
    if cs:
        if cs.exit_at:
            return ClassState.COMPLETED
        return ClassState.IN_CLASS if cs.session_date == today else ClassState.EXIT_MISSING

    sch = lec.schedule
    if on > today:
        return ClassState.YET_TO_START
    if on < today or not sch or not sch.planned_start_time:
        return ClassState.NOT_RECORDED if on < today else ClassState.YET_TO_START
    now_min = now.hour * 60 + now.minute
    if now_min < _minutes(sch.planned_start_time):
        return ClassState.YET_TO_START
    end = sch.planned_end_time
    if end is None or now_min <= _minutes(end):
        return ClassState.ENTRY_DUE
    return ClassState.NOT_RECORDED


def _chain(lec: Lecture) -> dict:
    """Latest-round status per level, so one row shows Professor -> CL/CH -> OM at a glance."""
    pr: LectureProgress | None = lec.progress
    out: dict = {"submission_status": pr.submission_status if pr else None,
                 "submitted_at": ser._iso(pr.submitted_at) if pr else None, "round": pr.submission_count if pr else 0,
                 "levels": {lvl.value: None for lvl in VERIFICATION_CHAIN}, "om_verification_id": None, "steps": [],
                 "final_ready": False, "waiting_for": "Waiting for the professor to submit the lecture record."}
    if not pr or not pr.submission_count:
        return out
    current = [v for v in pr.verifications if v.round == pr.submission_count and v.status != VerificationStatus.SUPERSEDED]
    for v in current:
        if v.verification_level not in out["levels"]:
            continue  # a legacy CH step: kept in the audit trail, not part of the active chain
        out["levels"][v.verification_level] = v.status
        out["steps"].append({"level": v.verification_level, "status": v.status, "verifier": ser.user_brief(v.verifier),
                             "remarks": v.remarks, "verified_at": ser._iso(v.verified_at)})
        if v.verification_level == VerificationLevel.OM:
            out["om_verification_id"] = str(v.id)
    academic = out["levels"][VerificationLevel.CL_CH.value]
    # Final Verify is only possible once the academic step is done; the UI shows this sentence otherwise.
    out["final_ready"] = out["levels"][VerificationLevel.OM.value] == VerificationStatus.PENDING
    out["waiting_for"] = None
    if out["levels"][VerificationLevel.OM.value] is None:
        if pr.submission_status == SubmissionStatus.CORRECTION_REQUIRED:
            out["waiting_for"] = "Waiting for the professor to correct and resubmit the record."
        elif academic != VerificationStatus.VERIFIED:
            out["waiting_for"] = "Waiting for CL/CH academic verification."
    return out


def class_row(lec: Lecture, on: date | None = None, now: datetime | None = None) -> dict:
    now = now or _local(clock.now_utc())
    plan: TeachingPlan = lec.teaching_plan
    sch = lec.schedule
    cs: ClassSession | None = lec.class_session
    pr = lec.progress
    on = on or (cs.session_date if cs else class_date(lec))
    start = cs.scheduled_start if cs else (sch.planned_start_time if sch else None)
    end = cs.scheduled_end if cs else (sch.planned_end_time if sch else None)
    duration = int((cs.exit_at - cs.entry_at).total_seconds() // 60) if cs and cs.exit_at else None
    return {
        "lecture_id": str(lec.id), "plan_id": str(plan.id), "date": on.isoformat() if on else None,
        "scheduled_start": ser._hm(start), "scheduled_end": ser._hm(end),
        "room": (cs.room if cs else None) or (sch.room if sch else None) or plan.room,
        "professor": ser.user_brief(lec.effective_professor),
        "subject": {"code": plan.subject.code, "name": plan.subject.name, "short_name": plan.subject.short_name},
        "section": plan.section.name, "semester": plan.semester.name, "semester_number": plan.semester.number,
        "branch_code": plan.branch.code,
        "lecture_no": lec.lecture_no, "topic": lec.content_topic, "lecture_type": lec.lecture_type,
        "state": _state(lec, on, now).value if on else ClassState.YET_TO_START.value,
        "is_rescheduled": bool(pr and pr.execution_status == ExecutionStatus.RESCHEDULED and pr.rescheduled_to),
        "entry_time": _hm(cs.entry_at) if cs else None, "exit_time": _hm(cs.exit_at) if cs else None,
        "delay_minutes": cs.entry_delay_minutes if cs else None,
        "timing_status": cs.timing_status if cs else None,
        "delay_reason": cs.delay_reason if cs else None,
        "delay_reason_label": DELAY_REASON_LABELS.get(DelayReason(cs.delay_reason)) if cs and cs.delay_reason else None,
        "delay_remarks": cs.delay_remarks if cs else None,
        "duration_minutes": duration,
        "early_exit_minutes": cs.early_exit_minutes if cs else None, "early_exit_reason": cs.early_exit_reason if cs else None,
        # The professor's own Start / End clicks - shown beside, never merged with, the OM's entry / exit.
        "professor_started_at": _hm(pr.professor_started_at) if pr else None,
        "professor_ended_at": _hm(pr.professor_ended_at) if pr else None,
        "execution_status": pr.execution_status if pr else ExecutionStatus.SCHEDULED.value,
        "verification": _chain(lec),
    }


def session_brief(cs: ClassSession | None) -> dict | None:
    """Timing record as shown to professors and verifiers beside the lecture update."""
    if not cs:
        return None
    return {
        "date": cs.session_date.isoformat(), "scheduled_start": ser._hm(cs.scheduled_start), "scheduled_end": ser._hm(cs.scheduled_end),
        "room": cs.room, "entry_time": _hm(cs.entry_at), "exit_time": _hm(cs.exit_at),
        "delay_minutes": cs.entry_delay_minutes, "timing_status": cs.timing_status, "delay_reason": cs.delay_reason,
        "delay_reason_label": DELAY_REASON_LABELS.get(DelayReason(cs.delay_reason)) if cs.delay_reason else None,
        "delay_remarks": cs.delay_remarks,
        "duration_minutes": int((cs.exit_at - cs.entry_at).total_seconds() // 60) if cs.exit_at else None,
        "early_exit_minutes": cs.early_exit_minutes, "early_exit_reason": cs.early_exit_reason,
    }


def _lectures_between(db: Session, start: date, end: date, *, professor_id=None, viewer: User | None = None) -> list[tuple[Lecture, date]]:
    stmt = (
        select(Lecture)
        .join(TeachingPlan, Lecture.teaching_plan_id == TeachingPlan.id)
        .join(LectureSchedule, LectureSchedule.lecture_id == Lecture.id)
        .outerjoin(LectureProgress, LectureProgress.lecture_id == Lecture.id)
        .outerjoin(ClassSession, ClassSession.lecture_id == Lecture.id)
        .where(TeachingPlan.status == PlanStatus.PUBLISHED, Lecture.is_cancelled.is_(False), Lecture.is_released.is_(True),
               or_(LectureSchedule.planned_date.between(start, end), LectureProgress.rescheduled_to.between(start, end),
                   ClassSession.session_date.between(start, end)))
        .options(selectinload(Lecture.schedule), selectinload(Lecture.progress), selectinload(Lecture.class_session),
                 selectinload(Lecture.teaching_plan))
    )
    if professor_id:
        stmt = stmt.where(func.coalesce(Lecture.professor_id, TeachingPlan.professor_id) == professor_id)
    if viewer:
        stmt = stmt.where(*scope_service.plan_filter(viewer))
    out = []
    for lec in db.scalars(stmt).unique():
        d = lec.class_session.session_date if lec.class_session else class_date(lec)  # a recorded class sits on the day it was held
        if d and start <= d <= end:
            out.append((lec, d))
    out.sort(key=lambda p: (p[1], p[0].schedule.planned_start_time or time.min, p[0].teaching_plan.subject.code))
    return out


def classes(db: Session, start: date, end: date | None = None, *, professor_id=None, viewer: User | None = None) -> list[dict]:
    """`viewer` limits the list to the signed-in OM's scope; admins and professor queries pass through unfiltered."""
    now = _local(clock.now_utc())
    return [class_row(lec, d, now) for lec, d in _lectures_between(db, start, end or start, professor_id=professor_id, viewer=viewer)]


def _awaiting_final(db: Session, viewer: User | None = None) -> int:
    from app.models import Verification
    stmt = (select(func.count(Verification.id)).join(LectureProgress, Verification.lecture_progress_id == LectureProgress.id)
            .join(Lecture, LectureProgress.lecture_id == Lecture.id).join(TeachingPlan, Lecture.teaching_plan_id == TeachingPlan.id)
            .where(Verification.verification_level == VerificationLevel.OM, Verification.status == VerificationStatus.PENDING))
    if viewer:
        stmt = stmt.where(*scope_service.plan_filter(viewer))
    return db.scalar(stmt) or 0


def dashboard(db: Session, on: date | None = None, *, viewer: User | None = None) -> dict:
    on = on or clock.today()
    rows = classes(db, on, viewer=viewer)
    states = Counter(r["state"] for r in rows)
    return {
        "date": on.isoformat(), "is_today": on == clock.today(),
        "now": _local(clock.now_utc()).strftime("%H:%M"),
        "tolerance_minutes": tolerance(),
        "metrics": {
            "total": len(rows),
            "running": states[ClassState.IN_CLASS],
            "entry_due": states[ClassState.ENTRY_DUE],
            "yet_to_start": states[ClassState.YET_TO_START],
            "completed": states[ClassState.COMPLETED],
            "not_recorded": states[ClassState.NOT_RECORDED],
            "exit_missing": states[ClassState.EXIT_MISSING],
            "delayed_entry": sum(1 for r in rows if r["timing_status"] == TimingStatus.DELAYED),
            "awaiting_final_verification": _awaiting_final(db, viewer),
        },
        "scope": scope_service.describe(db, viewer) if viewer else None,
        "classes": rows,
    }


# ------------------------------------------------------------------ recording

def _recordable(db: Session, om: User, lecture_id: uuid.UUID) -> tuple[Lecture, date]:
    lec = db.scalar(select(Lecture).where(Lecture.id == lecture_id).with_for_update(of=Lecture))
    if not lec:
        raise NotFound("Class not found.")
    scope_service.require(om, lec.teaching_plan, "This class")
    if lec.teaching_plan.status != PlanStatus.PUBLISHED:
        raise Conflict("This class belongs to a plan that is not published.", code="PLAN_NOT_PUBLISHED")
    on = lec.class_session.session_date if lec.class_session else class_date(lec)
    if not on or not lec.schedule or not lec.schedule.planned_start_time:
        raise BusinessRuleViolation("This class has no scheduled date and start time, so timings cannot be recorded.",
                                    code="CLASS_NOT_SCHEDULED")
    if on > clock.today():
        raise BusinessRuleViolation("Timings can be recorded on the day of the class, not before.", code="CLASS_IN_FUTURE")
    pr = lec.progress
    if pr and pr.submission_status == SubmissionStatus.FINAL_VERIFIED:
        raise Conflict("This class is final verified; its timing record is locked.", code="TIMING_LOCKED")
    return lec, on


def _server_time(on: date, hhmm: str | None) -> str:
    """Clock In / Clock Out send no time: the server's clock is the record. A typed time is a later correction."""
    if hhmm:
        return hhmm
    now = _local(clock.now_utc())
    if on != now.date():
        raise BusinessRuleViolation("This class was on an earlier day. Enter the time to correct its record.", code="TIME_REQUIRED")
    return now.strftime("%H:%M")


def _at(on: date, hhmm: str) -> datetime:
    moment = datetime.combine(on, time.fromisoformat(hhmm), tzinfo=get_settings().tz)
    if moment > _local(clock.now_utc()) + timedelta(minutes=1):
        raise BusinessRuleViolation("The time cannot be in the future.", code="TIME_IN_FUTURE")
    return moment


def record_entry(db: Session, om: User, lecture_id: uuid.UUID, data: rq.EntryRecord) -> dict:
    lec, on = _recordable(db, om, lecture_id)
    cs: ClassSession | None = lec.class_session
    if cs and cs.exit_at:
        raise Conflict("Exit is already recorded for this class. The entry time can no longer be changed.", code="CLASS_CLOSED")
    stamp = None if data.time else _local(clock.now_utc())  # Clock In: the server's own timestamp, to the second
    data = data.model_copy(update={"time": _server_time(on, data.time)})
    entry = stamp or _at(on, data.time)
    sch = lec.schedule
    delay = max(0, _minutes(time.fromisoformat(data.time)) - _minutes(sch.planned_start_time))
    delayed = delay > tolerance()
    if delayed and not data.delay_reason:
        # The backend decides what counts as a delay; the UI then asks for the reason and repeats the call.
        raise BusinessRuleViolation(
            f"Entry is {delay} minutes after the scheduled start. Select a delay reason.", code="DELAY_REASON_REQUIRED",
            details={"delay_minutes": delay, "tolerance_minutes": tolerance()})
    if delayed and data.delay_reason == DelayReason.OTHER and not (data.delay_remarks or "").strip():
        raise BusinessRuleViolation("Add remarks when the delay reason is Other.", code="DELAY_REMARKS_REQUIRED",
                                    details={"delay_minutes": delay, "tolerance_minutes": tolerance()})
    before = None
    if cs is None:
        cs = ClassSession(lecture_id=lec.id, professor_id=lec.effective_professor_id, session_date=on,
                          scheduled_start=sch.planned_start_time, scheduled_end=sch.planned_end_time,
                          room=sch.room or lec.teaching_plan.room, entry_recorded_by_id=om.id)
        db.add(cs)
    else:
        before = {"entry_time": _hm(cs.entry_at), "delay_minutes": cs.entry_delay_minutes, "delay_reason": cs.delay_reason}
    cs.entry_at, cs.entry_delay_minutes, cs.entry_recorded_by_id = entry, delay, om.id
    cs.timing_status = TimingStatus.DELAYED if delayed else TimingStatus.ON_TIME
    cs.delay_reason = data.delay_reason.value if delayed else None
    cs.delay_remarks = (data.delay_remarks or None) if delayed else None
    db.flush()
    plan = lec.teaching_plan
    audit_service.record(
        db, actor=om, action="operations.entry_corrected" if before else "operations.entry_recorded",
        entity_type="class_session", entity_id=cs.id,
        summary=(f"Recorded entry {data.time} for {plan.subject.short_name or plan.subject.code} Lecture {lec.lecture_no}"
                 + (f" ({delay} min late: {DELAY_REASON_LABELS[data.delay_reason]})." if delayed else " (on time).")),
        old=before, new={"entry_time": data.time, "delay_minutes": delay, "delay_reason": cs.delay_reason},
        scope_type="teaching_plan", scope_id=plan.id)
    db.commit()
    db.expire_all()
    return class_row(db.get(Lecture, lecture_id))


def record_exit(db: Session, om: User, lecture_id: uuid.UUID, data: rq.ExitRecord) -> dict:
    lec, on = _recordable(db, om, lecture_id)
    cs: ClassSession | None = lec.class_session
    if cs is None:
        raise BusinessRuleViolation("Record the entry time first.", code="ENTRY_NOT_RECORDED")
    stamp = None if data.time else _local(clock.now_utc())  # Clock Out: the server's own timestamp, to the second
    data = data.model_copy(update={"time": _server_time(on, data.time)})
    leaving = stamp or _at(on, data.time)
    if leaving <= cs.entry_at:
        raise BusinessRuleViolation(f"Exit must be after the entry time ({_hm(cs.entry_at)}).", code="EXIT_BEFORE_ENTRY")
    early = 0
    if cs.scheduled_end:
        early = max(0, _minutes(cs.scheduled_end) - _minutes(time.fromisoformat(data.time)))
    tolerance_exit = get_settings().exit_early_tolerance_minutes
    if early > tolerance_exit and not (data.early_exit_reason or "").strip():
        # Same pattern as a late entry: the backend decides what counts as leaving early.
        raise BusinessRuleViolation(
            f"Exit is {early} minutes before the scheduled end. Give the reason for the early exit.", code="EARLY_EXIT_REASON_REQUIRED",
            details={"early_minutes": early, "tolerance_minutes": tolerance_exit})
    before = {"exit_time": _hm(cs.exit_at)} if cs.exit_at else None
    cs.exit_at, cs.exit_recorded_by_id = leaving, om.id
    cs.early_exit_minutes = early
    cs.early_exit_reason = (data.early_exit_reason or "").strip() or None if early > tolerance_exit else None
    plan = lec.teaching_plan
    audit_service.record(
        db, actor=om, action="operations.exit_corrected" if before else "operations.exit_recorded",
        entity_type="class_session", entity_id=cs.id,
        summary=f"Recorded exit {data.time} for {plan.subject.short_name or plan.subject.code} Lecture {lec.lecture_no}.",
        old=before, new={"exit_time": data.time}, scope_type="teaching_plan", scope_id=plan.id)
    db.commit()
    db.expire_all()
    return class_row(db.get(Lecture, lecture_id))


def class_detail(db: Session, lecture_id: uuid.UUID, *, viewer: User | None = None) -> dict:
    lec = db.get(Lecture, lecture_id)
    if not lec or lec.teaching_plan.status != PlanStatus.PUBLISHED:
        raise NotFound("Class not found.")
    if viewer:
        scope_service.require(viewer, lec.teaching_plan, "This class")
    pr = lec.progress
    return class_row(lec) | {
        "subtopics": [s.title for s in lec.subtopics],
        "professor_update": None if not pr else {
            "execution_status": pr.execution_status, "actual_completion_date": ser._iso(pr.actual_completion_date),
            "remarks": pr.remarks, "notes_count": len(pr.materials), "has_assignment": pr.assignment is not None,
        },
        "tolerance_minutes": tolerance(),
    }


# ------------------------------------------------------------------ records & reports

def records(db: Session, start: date, end: date, *, professor_id=None, timing: str | None = None,
            subject_id=None, q: str | None = None, viewer: User | None = None) -> list[dict]:
    """Recorded class sessions (entry exists), newest first."""
    stmt = (select(ClassSession).join(Lecture, ClassSession.lecture_id == Lecture.id)
            .join(TeachingPlan, Lecture.teaching_plan_id == TeachingPlan.id)
            .where(ClassSession.session_date.between(start, end))
            .order_by(ClassSession.session_date.desc(), ClassSession.scheduled_start.desc()))
    if professor_id:
        stmt = stmt.where(ClassSession.professor_id == professor_id)
    if subject_id:
        stmt = stmt.where(TeachingPlan.subject_id == subject_id)
    if timing:
        stmt = stmt.where(ClassSession.timing_status == timing)
    if viewer:
        stmt = stmt.where(*scope_service.plan_filter(viewer))
    now = _local(clock.now_utc())
    rows = [class_row(cs.lecture, cs.session_date, now) for cs in db.scalars(stmt.limit(1000)).unique()]
    if q:
        needle = q.lower()
        rows = [r for r in rows if needle in f"{r['professor']['full_name']} {r['subject']['code']} {r['subject']['name']} {r['topic']} {r['room'] or ''}".lower()]
    return rows


def _aggregate(rows: list[dict]) -> dict:
    recorded = len(rows)
    delayed = [r for r in rows if r["timing_status"] == TimingStatus.DELAYED]
    durations = [r["duration_minutes"] for r in rows if r["duration_minutes"] is not None]
    return {
        "recorded": recorded, "on_time": recorded - len(delayed), "delayed": len(delayed),
        "on_time_pct": round((recorded - len(delayed)) * 100 / recorded) if recorded else 0,
        "average_delay_minutes": round(sum(r["delay_minutes"] for r in delayed) / len(delayed), 1) if delayed else 0,
        "total_delay_minutes": sum(r["delay_minutes"] for r in delayed),
        "average_duration_minutes": round(sum(durations) / len(durations)) if durations else None,
        "exit_missing": sum(1 for r in rows if r["exit_time"] is None),
    }


def faculty_records(db: Session, start: date, end: date, *, viewer: User | None = None) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in records(db, start, end, viewer=viewer):
        groups[r["professor"]["id"]].append(r)
    out = []
    for rows in groups.values():
        reasons = Counter(r["delay_reason_label"] for r in rows if r["delay_reason_label"])
        out.append({"professor": rows[0]["professor"],
                    "subjects": sorted({f"{r['subject']['short_name'] or r['subject']['code']} · {r['section']}" for r in rows}),
                    "top_delay_reason": reasons.most_common(1)[0][0] if reasons else None,
                    "last_recorded": max(r["date"] for r in rows), **_aggregate(rows)})
    return sorted(out, key=lambda r: (-r["delayed"], r["professor"]["full_name"]))


def report(db: Session, start: date, end: date, *, viewer: User | None = None) -> dict:
    """Definitions: On time = entry within the tolerance of the scheduled start. Coverage = classes with a
    recorded entry / classes scheduled up to today in the range."""
    rows = records(db, start, end, viewer=viewer)
    scheduled = [r for r in classes(db, start, min(end, clock.today()), viewer=viewer)]
    reasons = Counter(r["delay_reason"] for r in rows if r["delay_reason"])
    by_day: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_day[r["date"]].append(r)
    return {
        "date_from": start.isoformat(), "date_to": end.isoformat(), "tolerance_minutes": tolerance(),
        "summary": _aggregate(rows) | {
            "scheduled": len(scheduled),
            "coverage_pct": round(len(rows) * 100 / len(scheduled)) if scheduled else 0,
            "awaiting_final_verification": _awaiting_final(db, viewer),
        },
        "reasons": [{"reason": k, "label": DELAY_REASON_LABELS[DelayReason(k)], "count": n} for k, n in reasons.most_common()],
        "daily": [{"date": d, "recorded": len(v), "delayed": sum(1 for r in v if r["timing_status"] == TimingStatus.DELAYED),
                   "on_time": sum(1 for r in v if r["timing_status"] == TimingStatus.ON_TIME)}
                  for d, v in sorted(by_day.items())],
        "faculty": faculty_records(db, start, end, viewer=viewer),
        "definitions": {
            "on_time": f"Entry within {tolerance()} minutes of the scheduled start.",
            "delayed": f"Entry more than {tolerance()} minutes after the scheduled start; a reason is mandatory.",
            "coverage": "Classes with a recorded entry ÷ classes scheduled up to today in the selected range.",
        },
    }
