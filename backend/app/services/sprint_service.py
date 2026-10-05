"""Weekly sprint plan: MASTER PLAN + published weekly revisions = effective schedule.

The semester master plan is created once (bulk import). Every week the admin opens the
week in a sprint meeting, which creates a DRAFT revision. Edits are stored as diffs on the
draft and change nothing else, so professors keep seeing the last published schedule.
Publishing applies the diffs in one transaction, numbers the revision (v2, v3...), keeps the
master values in `lectures.master_snapshot`, audits every change and sends each affected
professor one consolidated notification.

Carry-forward items are derived from what professors actually recorded (partially
completed / not conducted). The system only lists them; the admin decides where they go.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core import clock
from app.core.config import get_settings
from app.core.enums import (
    VERIFICATION_CHAIN, CarryForwardStatus, ChangeReason, ChangeType, ExecutionStatus, LectureOrigin, LectureType,
    PlanStatus, RevisionStatus, Role, SubmissionStatus, VerificationStatus,
)
from app.core.errors import BusinessRuleViolation, Conflict, NotFound
from app.models import (
    CarryForwardItem, Lecture, LectureProgress, LectureSchedule, LectureSubtopic, Semester, SprintRevision,
    SprintRevisionItem, TeachingPlan, User,
)
from app.schemas import requests as rq
from app.services import audit_service, notification_service
from app.services import serializers as ser

REASON_LABELS = {
    ChangeReason.SPRINT_MEETING_DECISION: "Sprint meeting decision",
    ChangeReason.FACULTY_AVAILABILITY: "Faculty availability",
    ChangeReason.PREVIOUS_TOPIC_INCOMPLETE: "Previous topic incomplete",
    ChangeReason.HOLIDAY_ADJUSTMENT: "Holiday adjustment",
    ChangeReason.ROOM_CHANGE: "Room change",
    ChangeReason.LAB_AVAILABILITY: "Lab availability",
    ChangeReason.ACADEMIC_REQUIREMENT: "Academic requirement",
    ChangeReason.OTHER: "Other",
}
FIELDS = ("planned_date", "planned_start_time", "planned_end_time", "room", "professor_id", "content_topic", "subtopics", "lecture_type")
FIELD_LABELS = {"planned_date": "Date", "planned_start_time": "Start time", "planned_end_time": "End time", "room": "Room",
                "professor_id": "Professor", "content_topic": "Topic", "subtopics": "Subtopics", "lecture_type": "Lecture type"}
DELIVERED = (ExecutionStatus.COMPLETED, ExecutionStatus.PARTIALLY_COMPLETED)


# ------------------------------------------------------------------ weeks

def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def week_bounds(d: date | None) -> tuple[date, date]:
    start = monday(d or clock.today())
    return start, start + timedelta(days=6)


def week_info(db: Session, start: date) -> dict:
    from app.models import SemesterSprintPlan
    sp = db.scalar(select(SemesterSprintPlan).where(SemesterSprintPlan.status == "ACTIVE", SemesterSprintPlan.start_date <= start + timedelta(days=6),
                                                    SemesterSprintPlan.end_date >= start).order_by(SemesterSprintPlan.start_date))
    sem = db.scalar(select(Semester).where(Semester.is_current.is_(True)))
    first = sp.start_date if sp else (sem.start_date if sem else None)
    number = None
    if first:
        n = (start - monday(first)).days // 7 + 1
        number = n if n >= 1 else None
    return {"sprint_plan": {"id": str(sp.id), "name": sp.name, "end_date": sp.end_date.isoformat()} if sp else None,
            "start": start.isoformat(), "end": (start + timedelta(days=5)).isoformat(), "number": number,
            "is_current": start == monday(clock.today()), "is_past": start + timedelta(days=6) < clock.today()}


# ------------------------------------------------------------------ lecture values

def lecture_values(lec: Lecture) -> dict:
    sch = lec.schedule
    return {
        "planned_date": sch.planned_date.isoformat() if sch and sch.planned_date else None,
        "planned_start_time": ser._hm(sch.planned_start_time) if sch else None,
        "planned_end_time": ser._hm(sch.planned_end_time) if sch else None,
        "room": (sch.room if sch else None) or lec.teaching_plan.room,
        "professor_id": str(lec.effective_professor_id),
        "content_topic": lec.content_topic,
        "subtopics": [s.title for s in lec.subtopics],
        "lecture_type": lec.lecture_type,
    }


def lock_reason(lec: Lecture) -> str | None:
    """Why a lecture can no longer be changed in a sprint meeting (None = editable)."""
    if lec.is_cancelled:
        return "This lecture was cancelled in an earlier revision."
    if lec.class_session is not None:
        return "The Operations Manager has already recorded this class."
    pr = lec.progress
    if pr and (pr.professor_started_at or pr.submission_status != SubmissionStatus.DRAFT
               or pr.execution_status not in (ExecutionStatus.SCHEDULED, ExecutionStatus.RESCHEDULED)):
        return "The professor has already started or recorded this lecture."
    return None


def _names(db: Session, values: list[dict | None]) -> dict[str, str]:
    ids = {v["professor_id"] for v in values if v and v.get("professor_id")}
    if not ids:
        return {}
    return {str(i): n for i, n in db.execute(select(User.id, User.full_name).where(User.id.in_([uuid.UUID(i) for i in ids])))}


def _with_names(values: dict | None, names: dict[str, str]) -> dict | None:
    if not values:
        return values
    out = dict(values)
    if out.get("professor_id"):
        out["professor_name"] = names.get(out["professor_id"])
    return out


def revision_brief(r: SprintRevision | None) -> dict | None:
    if not r:
        return None
    return {"id": str(r.id), "week_start": r.week_start.isoformat(), "week_end": (r.week_start + timedelta(days=5)).isoformat(),
            "status": r.status, "revision_number": r.revision_number, "meeting_date": ser._iso(r.meeting_date),
            "meeting_notes": r.meeting_notes, "change_count": len(r.items),
            "created_by": ser.user_brief(r.created_by), "created_at": ser._iso(r.created_at),
            "published_by": ser.user_brief(r.published_by), "published_at": ser._iso(r.published_at)}


def item_view(item: SprintRevisionItem, names: dict[str, str], *, revision: SprintRevision | None = None) -> dict:
    rev = revision or item.revision
    lec = item.lecture
    plan = item.teaching_plan
    reason = ChangeReason(item.reason)
    return {
        "id": str(item.id), "change_type": item.change_type, "lecture_id": str(item.lecture_id) if item.lecture_id else None,
        "plan_id": str(plan.id),
        "subject": {"code": plan.subject.code, "name": plan.subject.name, "short_name": plan.subject.short_name},
        "section": plan.section.name, "semester": plan.semester.name,
        "lecture_no": lec.lecture_no if lec else None,
        "topic": (lec.content_topic if lec else None) or (item.new_values or {}).get("content_topic"),
        "old": _with_names(item.old_values, names), "new": _with_names(item.new_values, names),
        "changed_fields": [FIELD_LABELS[k] for k in FIELDS if k in (item.new_values or {})] if item.change_type == ChangeType.UPDATE else [],
        "reason": item.reason, "reason_label": REASON_LABELS[reason], "remarks": item.remarks,
        "is_carry_forward": item.carry_forward_lecture_id is not None,
        "revision_id": str(rev.id), "revision_number": rev.revision_number, "published_at": ser._iso(rev.published_at),
    }


# ------------------------------------------------------------------ week view

def _week_lectures(db: Session, start: date, end: date, *, professor_id: uuid.UUID | None = None, extra: list | None = None,
                   released_only: bool = False) -> list[Lecture]:
    stmt = (select(Lecture).join(TeachingPlan, Lecture.teaching_plan_id == TeachingPlan.id)
            .join(LectureSchedule, LectureSchedule.lecture_id == Lecture.id)
            .where(TeachingPlan.status == PlanStatus.PUBLISHED, LectureSchedule.planned_date.between(start, end))
            .options(selectinload(Lecture.schedule), selectinload(Lecture.progress), selectinload(Lecture.subtopics),
                     selectinload(Lecture.class_session), selectinload(Lecture.teaching_plan)))
    if released_only:  # everyone except the admin: only classes of a published week
        stmt = stmt.where(Lecture.is_released.is_(True))
    if professor_id:
        stmt = stmt.where(func.coalesce(Lecture.professor_id, TeachingPlan.professor_id) == professor_id)
    if extra:
        stmt = stmt.where(*extra)
    lectures = list(db.scalars(stmt).unique())
    lectures.sort(key=lambda l: (l.schedule.planned_date, l.schedule.planned_start_time or time.min, l.teaching_plan.subject.code))
    return lectures


def _latest_published_items(db: Session, lecture_ids: list[uuid.UUID]) -> dict[uuid.UUID, SprintRevisionItem]:
    if not lecture_ids:
        return {}
    rows = db.scalars(select(SprintRevisionItem).join(SprintRevision).where(
        SprintRevision.status == RevisionStatus.PUBLISHED, SprintRevisionItem.lecture_id.in_(lecture_ids))
        .order_by(SprintRevision.published_at)).unique()
    return {i.lecture_id: i for i in rows}  # last one wins


def _chain_levels(pr: LectureProgress | None) -> dict:
    levels = {lvl.value: None for lvl in VERIFICATION_CHAIN}
    if pr and pr.submission_count:
        for v in pr.verifications:
            if v.round == pr.submission_count and v.status != VerificationStatus.SUPERSEDED and v.verification_level in levels:
                levels[v.verification_level] = v.status
    return levels


def lecture_row(lec: Lecture, values: dict | None = None) -> dict:
    """One class as shown in a week view. `values` overrides the stored schedule (draft preview)."""
    plan = lec.teaching_plan
    v = values or lecture_values(lec)
    pr = lec.progress
    covered = sum(1 for s in (pr.subtopic_progress if pr else []) if s.is_covered)
    tz = get_settings().tz
    return {
        "lecture_id": str(lec.id), "plan_id": str(plan.id),
        "subject": {"code": plan.subject.code, "name": plan.subject.name, "short_name": plan.subject.short_name},
        "section": plan.section.name, "semester": plan.semester.name, "branch_code": plan.branch.code,
        "section_id": str(plan.section_id), "semester_number": plan.semester.number,
        "released": lec.is_released,
        "lecture_no": lec.lecture_no, "unit_no": lec.unit_no, "lecture_type": v["lecture_type"], "origin": lec.origin,
        "topic": v["content_topic"], "subtopics": v["subtopics"], "subtopics_covered": covered,
        "date": v["planned_date"], "start": v["planned_start_time"], "end": v["planned_end_time"], "room": v["room"],
        "professor": {"id": v["professor_id"], "full_name": lec.effective_professor.full_name},
        "is_cancelled": lec.is_cancelled,
        "execution_status": pr.execution_status if pr else ExecutionStatus.SCHEDULED.value,
        "submission_status": pr.submission_status if pr else None,
        "started_at": pr.professor_started_at.astimezone(tz).strftime("%H:%M") if pr and pr.professor_started_at else None,
        "ended_at": pr.professor_ended_at.astimezone(tz).strftime("%H:%M") if pr and pr.professor_ended_at else None,
        "verification": _chain_levels(pr),
    }


def execution_summary(lectures: list[Lecture]) -> dict:
    """Factual week-end numbers: lectures and subtopics planned vs delivered."""
    today = clock.today()
    live = [l for l in lectures if not l.is_cancelled]
    status = lambda l: l.progress.execution_status if l.progress else ExecutionStatus.SCHEDULED.value  # noqa: E731
    completed = sum(1 for l in live if status(l) == ExecutionStatus.COMPLETED)
    partial = sum(1 for l in live if status(l) == ExecutionStatus.PARTIALLY_COMPLETED)
    not_conducted = sum(1 for l in live if status(l) == ExecutionStatus.NOT_CONDUCTED
                        or (status(l) not in DELIVERED and l.schedule.planned_date < today))
    planned_subs = sum(len(l.subtopics) for l in live)
    covered = sum(sum(1 for s in l.progress.subtopic_progress if s.is_covered) for l in live if l.progress)
    return {"lectures_planned": len(live), "completed": completed, "partially_completed": partial, "not_conducted": not_conducted,
            "upcoming": len(live) - completed - partial - not_conducted,
            "subtopics_planned": planned_subs, "subtopics_covered": covered, "subtopics_remaining": planned_subs - covered,
            "cancelled": len(lectures) - len(live)}


def _days(start: date, rows: list[dict]) -> list[dict]:
    by_day: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_day[r["date"]].append(r)
    count = 7 if by_day.get((start + timedelta(days=6)).isoformat()) else 6  # Sunday only when something is on it
    out = []
    for i in range(count):
        d = start + timedelta(days=i)
        items = sorted(by_day.get(d.isoformat(), []), key=lambda r: (r["start"] or "", r["subject"]["code"]))
        out.append({"date": d.isoformat(), "lectures": items})
    return out


def _draft_for(db: Session, start: date) -> SprintRevision | None:
    return db.scalar(select(SprintRevision).where(SprintRevision.week_start == start, SprintRevision.status == RevisionStatus.DRAFT))


def _published_for(db: Session, start: date) -> list[SprintRevision]:
    return list(db.scalars(select(SprintRevision).where(SprintRevision.week_start == start, SprintRevision.status == RevisionStatus.PUBLISHED)
                           .order_by(SprintRevision.revision_number)).unique())


def admin_week(db: Session, week_start: date | None) -> dict:
    start, end = week_bounds(week_start)
    lectures = _week_lectures(db, start, end)
    draft = _draft_for(db, start)
    published = _published_for(db, start)
    latest_items = _latest_published_items(db, [l.id for l in lectures])
    draft_items = {i.lecture_id: i for i in (draft.items if draft else []) if i.lecture_id}
    names = _names(db, [i.old_values for i in [*latest_items.values(), *(draft.items if draft else [])]]
                   + [i.new_values for i in [*latest_items.values(), *(draft.items if draft else [])]]
                   + [l.master_snapshot for l in lectures])

    rows: list[dict] = []
    moved: list[tuple[Lecture, dict]] = []  # lectures the draft moves to another week: checked against that week
    # Lectures the draft brings INTO this week (the next pending topics, placed on this week's timetable slots).
    in_week = {l.id for l in lectures}
    for item in (draft.items if draft else []):
        lec = item.lecture
        if item.change_type != ChangeType.UPDATE or not lec or lec.id in in_week:
            continue
        preview = lecture_values(lec) | item.new_values
        if not preview.get("planned_date") or not (start.isoformat() <= preview["planned_date"] <= end.isoformat()):
            continue
        row = lecture_row(lec, preview)
        if "professor_id" in item.new_values:
            row["professor"] = {"id": preview["professor_id"], "full_name": names.get(preview["professor_id"], "")}
        row |= {"key": str(lec.id), "locked": lock_reason(lec), "revised": None, "master": _with_names(lec.master_snapshot, names),
                "draft": item_view(item, names, revision=draft) | {"moved_out": False, "moved_in": True}}
        rows.append(row)
    for lec in lectures:
        if lec.is_cancelled and lec.id not in latest_items:
            continue
        current = lecture_values(lec)
        item = draft_items.get(lec.id)
        preview = current
        moved_out = False
        if item and item.change_type == ChangeType.UPDATE:
            preview = current | item.new_values
            moved_out = not (start.isoformat() <= preview["planned_date"] <= end.isoformat())
        row = lecture_row(lec, preview)
        if moved_out:
            row["date"] = current["planned_date"]  # keep it visible on its original day, flagged below
            moved.append((lec, preview))
        if item and item.change_type == ChangeType.UPDATE and "professor_id" in item.new_values:
            row["professor"] = {"id": preview["professor_id"], "full_name": names.get(preview["professor_id"], "")}
        row |= {
            "key": str(lec.id), "locked": lock_reason(lec),
            "draft": None if not item else item_view(item, names, revision=draft) | {"moved_out": moved_out},
            "revised": item_view(latest_items[lec.id], names) if lec.id in latest_items else None,
            "master": _with_names(lec.master_snapshot, names),
        }
        rows.append(row)
    for item in (draft.items if draft else []):
        if item.change_type != ChangeType.ADD:
            continue
        v = item.new_values
        plan = item.teaching_plan
        rows.append({
            "key": f"item-{item.id}", "lecture_id": None, "plan_id": str(plan.id),
            "subject": {"code": plan.subject.code, "name": plan.subject.name, "short_name": plan.subject.short_name},
            "section": plan.section.name, "semester": plan.semester.name, "branch_code": plan.branch.code,
            "section_id": str(plan.section_id), "semester_number": plan.semester.number,
            "released": False,
            "lecture_no": None, "unit_no": None, "lecture_type": v["lecture_type"],
            "origin": LectureOrigin.CARRY_FORWARD.value if item.carry_forward_lecture_id else LectureOrigin.SPRINT_ADDED.value,
            "topic": v["content_topic"], "subtopics": v["subtopics"], "subtopics_covered": 0,
            "date": v["planned_date"], "start": v["planned_start_time"], "end": v["planned_end_time"], "room": v["room"],
            "professor": {"id": v["professor_id"], "full_name": names.get(v["professor_id"], "")},
            "is_cancelled": False, "execution_status": ExecutionStatus.SCHEDULED.value, "submission_status": None,
            "started_at": None, "ended_at": None, "verification": {lvl.value: None for lvl in VERIFICATION_CHAIN},
            "locked": None, "draft": item_view(item, names, revision=draft) | {"moved_out": False}, "revised": None, "master": None,
        })

    prev_start = start - timedelta(days=7)
    days = _days(start, rows)
    return {
        "week": week_info(db, start),
        "version": published[-1].revision_number if published else 1,
        "published": revision_brief(published[-1]) if published else None,
        "draft": revision_brief(draft),
        # Classes of this week that nobody but the admin can see yet. 0 = the week is published.
        "unpublished": sum(1 for r in rows if not r["released"] and not r["is_cancelled"]),
        "days": days,
        # Clashes the draft would create. A professor clash blocks publishing; a room clash is a warning.
        "conflicts": (_day_conflicts(days, _template_map(db)) + _moved_conflicts(db, moved, names)) if draft or any(not r["released"] for r in rows) else [],
        "summary": execution_summary(lectures),
        "previous_week": {"start": prev_start.isoformat(), "end": (prev_start + timedelta(days=5)).isoformat(),
                          **execution_summary(_week_lectures(db, prev_start, prev_start + timedelta(days=6)))},
        "carry_forward": carry_forward(db, start, draft),
        "reasons": [{"value": r.value, "label": REASON_LABELS[r]} for r in ChangeReason],
        "today": clock.today().isoformat(),
    }


# ------------------------------------------------------------------ carry-forward

def carry_forward(db: Session, before: date, draft: SprintRevision | None = None) -> list[dict]:
    """Remaining work from lectures held (or missed) before `before` that nobody has placed or resolved yet."""
    today = clock.today()
    stmt = (select(Lecture).join(TeachingPlan, Lecture.teaching_plan_id == TeachingPlan.id)
            .join(LectureSchedule, LectureSchedule.lecture_id == Lecture.id)
            .outerjoin(LectureProgress, LectureProgress.lecture_id == Lecture.id)
            .where(TeachingPlan.status == PlanStatus.PUBLISHED, Lecture.is_cancelled.is_(False),
                   LectureSchedule.planned_date < before, Lecture.is_released.is_(True),
                   (LectureProgress.id.is_(None)) | (LectureProgress.execution_status != ExecutionStatus.COMPLETED))
            .options(selectinload(Lecture.schedule), selectinload(Lecture.progress), selectinload(Lecture.subtopics),
                     selectinload(Lecture.teaching_plan))
            .order_by(LectureSchedule.planned_date))
    decided = {c.source_lecture_id: c for c in db.scalars(select(CarryForwardItem))}
    in_draft = {i.carry_forward_lecture_id: i for i in (draft.items if draft else []) if i.carry_forward_lecture_id}
    out = []
    for lec in db.scalars(stmt).unique():
        pr = lec.progress
        decision = decided.get(lec.id)
        if decision and decision.status in (CarryForwardStatus.SCHEDULED, CarryForwardStatus.RESOLVED):
            continue
        status = pr.execution_status if pr else ExecutionStatus.SCHEDULED.value
        if status == ExecutionStatus.RESCHEDULED and pr.rescheduled_to and pr.rescheduled_to >= today:
            continue  # the professor already moved it to a future date
        if status == ExecutionStatus.PARTIALLY_COMPLETED:
            covered = {s.subtopic_id for s in pr.subtopic_progress if s.is_covered}
            remaining = [s.title for s in lec.subtopics if s.id not in covered]
            kind, why = "PARTIAL", f"Partially completed in Lecture {lec.lecture_no}"
        else:
            # "Not conducted" needs evidence: the professor said so, or the day has passed without a record.
            if status != ExecutionStatus.NOT_CONDUCTED and lec.schedule.planned_date >= today:
                continue
            covered = set()
            remaining = [s.title for s in lec.subtopics]
            kind, why = "NOT_CONDUCTED", f"Lecture {lec.lecture_no} was not conducted"
        plan = lec.teaching_plan
        item = in_draft.get(lec.id)
        out.append({
            "lecture_id": str(lec.id), "plan_id": str(plan.id),
            "subject": {"code": plan.subject.code, "name": plan.subject.name, "short_name": plan.subject.short_name},
            "section": plan.section.name, "semester": plan.semester.name,
            "professor": {"id": str(lec.effective_professor_id), "full_name": lec.effective_professor.full_name},
            "lecture_no": lec.lecture_no, "unit_no": lec.unit_no, "topic": lec.content_topic, "lecture_type": lec.lecture_type,
            "date": lec.schedule.planned_date.isoformat(), "kind": kind, "why": why,
            "remaining": remaining, "covered": len(covered), "total": len(lec.subtopics),
            "status": decision.status if decision else CarryForwardStatus.OPEN.value, "note": decision.note if decision else None,
            "draft_item_id": str(item.id) if item else None,
            "room": (lec.schedule.room or plan.room), "duration_minutes": _duration(lec),
        })
    return out


def _duration(lec: Lecture) -> int | None:
    s, e = lec.schedule.planned_start_time, lec.schedule.planned_end_time
    return (e.hour * 60 + e.minute) - (s.hour * 60 + s.minute) if s and e else None


def decide_carry_forward(db: Session, admin: User, lecture_id: uuid.UUID, data: rq.CarryForwardDecision) -> dict:
    lec = db.get(Lecture, lecture_id)
    if not lec:
        raise NotFound("Lecture not found.")
    row = db.scalar(select(CarryForwardItem).where(CarryForwardItem.source_lecture_id == lecture_id))
    if row and row.status == CarryForwardStatus.SCHEDULED:
        raise Conflict("This item is already scheduled in a published week.", code="ALREADY_SCHEDULED")
    if data.status == CarryForwardStatus.OPEN:
        if row:
            db.delete(row)
    else:
        if not row:
            row = CarryForwardItem(source_lecture_id=lecture_id, decided_by_id=admin.id, decided_at=clock.now_utc(), status=data.status)
            db.add(row)
        row.status, row.note, row.decided_by_id, row.decided_at = data.status, data.note, admin.id, clock.now_utc()
    label = {CarryForwardStatus.DEFERRED: "deferred to a later week", CarryForwardStatus.RESOLVED: "marked resolved",
             CarryForwardStatus.OPEN: "reopened"}[data.status]
    audit_service.record(db, actor=admin, action="sprint.carry_forward_decided", entity_type="lecture", entity_id=lec.id,
                         summary=f"Carry-forward from Lecture {lec.lecture_no} ({lec.content_topic}) {label}.",
                         new={"status": data.status, "note": data.note}, scope_type="teaching_plan", scope_id=lec.teaching_plan_id)
    db.commit()
    return {"lecture_id": str(lecture_id), "status": data.status}


# ------------------------------------------------------------------ draft editing

def start_meeting(db: Session, admin: User, data: rq.SprintMeetingStart) -> dict:
    start, end = week_bounds(data.week_start)
    if end < clock.today():
        raise BusinessRuleViolation("This week is over. A sprint meeting can only revise the current or a future week.", code="WEEK_OVER")
    draft = _draft_for(db, start)
    if not draft:
        draft = SprintRevision(week_start=start, week_end=end, status=RevisionStatus.DRAFT, created_by_id=admin.id,
                               meeting_date=data.meeting_date or clock.today(), meeting_notes=data.meeting_notes)
        db.add(draft)
        db.flush()
        audit_service.record(db, actor=admin, action="sprint.revision_created", entity_type="sprint_revision", entity_id=draft.id,
                             summary=f"Started sprint meeting update for week of {start:%d %b %Y}.")
        db.commit()
    db.expire_all()
    return admin_week(db, start)


AUTO_REMARK = "Planned from the master timetable"


def generate_week(db: Session, admin: User, data: rq.SprintGenerate) -> dict:
    """MAKE WEEKLY SPRINT PLAN.

    For every subject-section in the published master timetable, take that week's real class slots (inside the
    semester, not on a holiday, not already in the past) and fill them in order: first the work carried forward
    from earlier classes, then the next topics of the master plan that have not been taught yet. Nothing is
    invented and nothing is published - the result is the week's DRAFT for the admin to review.
    """
    from app.services import sprint_plan_service
    from app.services import timetable_service as tt
    today = clock.today()
    start, end = week_bounds(data.week_start or today + timedelta(days=7))
    if end < today:
        raise BusinessRuleViolation("This week is over. A sprint plan can only be made for the current or a future week.", code="WEEK_OVER")
    entries = tt.published_entries(db)
    if not entries:
        raise Conflict("Generate the semester sprint first (Sprint Plans → open the plan → Generate Semester Sprint). "
                       "The weekly plan is made from it.", code="NO_TIMETABLE")
    draft = _draft_for(db, start)
    if draft and draft.items and not data.replace:
        raise Conflict(f"The week of {start:%d %b %Y} already has a draft with {len(draft.items)} change(s). "
                       "Generating again replaces them.", code="DRAFT_HAS_CHANGES", details={"changes": len(draft.items)})
    if not draft:
        draft = SprintRevision(week_start=start, week_end=end, status=RevisionStatus.DRAFT, created_by_id=admin.id, meeting_date=today)
        db.add(draft)
    else:
        draft.items.clear()
    db.flush()

    holidays = {h.date: h.name for h in tt.list_holidays(db)}
    open_cf: dict[str, list[dict]] = defaultdict(list)
    for c in carry_forward(db, start):
        if c["status"] == CarryForwardStatus.OPEN:
            open_cf[c["plan_id"]].append(c)
    by_plan: dict[uuid.UUID, list] = defaultdict(list)
    for e in entries:
        by_plan[e.teaching_plan_id].append(e)

    stats = {"slots": 0, "carry_forward": 0, "topics": 0, "unchanged": 0, "holiday_slots": 0, "outside_semester": 0,
             "empty_slots": 0, "left_over": 0, "skipped_plans": []}
    notes: list[str] = []
    ordered = sorted(by_plan.values(), key=lambda es: (es[0].teaching_plan.semester.number, es[0].teaching_plan.subject.code,
                                                       es[0].teaching_plan.section.name))
    for plan_entries in ordered:
        plan = plan_entries[0].teaching_plan
        name = f"{plan.subject.short_name or plan.subject.code} {plan.semester.name.replace('Semester', 'Sem')}-{plan.section.name}"
        if plan.status != PlanStatus.PUBLISHED:
            stats["skipped_plans"].append(name)
            continue
        sem = plan.semester
        slots = []
        for e in sorted(plan_entries, key=lambda e: (e.weekday, e.start_time)):
            d = start + timedelta(days=e.weekday)
            if d < today:
                continue
            if d < sem.start_date or d > sem.end_date:
                stats["outside_semester"] += 1
            elif d in holidays:
                stats["holiday_slots"] += 1
            else:
                slots.append((d, e))
        if plan.sprint_plan_id and plan.sprint_plan and plan.sprint_plan.status == "ACTIVE":
            # A subject of a semester sprint plan: topics that are not published yet are re-flowed from this week on,
            # leaving the first free slots to the carry-forward work. Only that work needs a draft entry.
            waiting = open_cf.get(str(plan.id), [])
            flow = sprint_plan_service.reflow(db, plan, max(start, today), reserve=[c["lecture_type"] for c in waiting], holidays=None)
            here = {i: (d, e) for i, (d, e) in flow["reserved"].items() if start <= d <= end}
            in_week = [l for l in sprint_plan_service._lectures(db, plan.id)
                       if l.schedule and l.schedule.planned_date and max(start, today) <= l.schedule.planned_date <= end]
            stats["slots"] += len(in_week) + len(here)
            stats["topics"] += sum(1 for l in in_week if not l.is_released)
            stats["unchanged"] += sum(1 for l in in_week if l.is_released)
            for i, c in enumerate(waiting):
                if i not in here:
                    continue
                d, e = here[i]
                db.add(SprintRevisionItem(
                    revision_id=draft.id, teaching_plan_id=plan.id, change_type=ChangeType.ADD, old_values=None,
                    new_values={"planned_date": d.isoformat(), "planned_start_time": ser._hm(e.start_time), "planned_end_time": ser._hm(e.end_time),
                                "room": e.room or plan.room, "professor_id": str(e.effective_professor.id),
                                "content_topic": c["topic"], "subtopics": c["remaining"], "lecture_type": c["lecture_type"]},
                    reason=ChangeReason.PREVIOUS_TOPIC_INCOMPLETE.value, remarks=f"{AUTO_REMARK}. {c['why']}.",
                    carry_forward_lecture_id=uuid.UUID(c["lecture_id"])))
                stats["carry_forward"] += 1
            if len(waiting) > len(here):
                notes.append(f"{name}: {len(waiting) - len(here)} carry-forward item(s) did not fit this week and stay in the carry-forward list.")
            if flow["unscheduled"]:
                notes.append(f"{name}: {flow['unscheduled']} topic(s) no longer fit before {plan.sprint_plan.end_date:%d %b %Y}.")
            continue
        lectures = list(db.scalars(select(Lecture).where(Lecture.teaching_plan_id == plan.id, Lecture.is_cancelled.is_(False))
                                   .order_by(Lecture.sequence)
                                   .options(selectinload(Lecture.schedule), selectinload(Lecture.progress), selectinload(Lecture.subtopics),
                                            selectinload(Lecture.class_session))).unique())
        taken: list[tuple[date, time, time | None]] = []  # classes of this week that already happened or started
        pending: list[Lecture] = []
        for lec in lectures:
            sch = lec.schedule
            d = sch.planned_date if sch else None
            if lock_reason(lec):
                if d and start <= d <= end and sch.planned_start_time:
                    taken.append((d, sch.planned_start_time, sch.planned_end_time))
            elif d is None or d >= start:
                pending.append(lec)  # earlier, not delivered lectures come back through carry-forward instead
        slots = [(d, e) for d, e in slots
                 if not any(td == d and ts < e.end_time and e.start_time < (te or e.end_time) for td, ts, te in taken)]
        stats["slots"] += len(slots)
        queue: list[tuple[str, object, str]] = [("CF", c, c["lecture_type"]) for c in open_cf.get(str(plan.id), [])]
        queue += [("LEC", lec, lec.lecture_type) for lec in pending]
        for d, e in slots:
            if not queue:
                stats["empty_slots"] += 1
                continue
            lab = e.class_type == "LAB"
            # A lab slot takes the next practical if one is waiting, a class slot the next non-practical; otherwise simply the next.
            pick = next((i for i, q in enumerate(queue) if (q[2] == LectureType.PRACTICAL) == lab), 0)
            kind, obj, _ = queue.pop(pick)
            target = {"planned_date": d.isoformat(), "planned_start_time": ser._hm(e.start_time), "planned_end_time": ser._hm(e.end_time),
                      "room": e.room or plan.room, "professor_id": str(e.effective_professor.id)}
            if kind == "CF":
                db.add(SprintRevisionItem(
                    revision_id=draft.id, teaching_plan_id=plan.id, change_type=ChangeType.ADD, old_values=None,
                    new_values=target | {"content_topic": obj["topic"], "subtopics": obj["remaining"], "lecture_type": obj["lecture_type"]},
                    reason=ChangeReason.PREVIOUS_TOPIC_INCOMPLETE.value, remarks=f"{AUTO_REMARK}. {obj['why']}.",
                    carry_forward_lecture_id=uuid.UUID(obj["lecture_id"])))
                stats["carry_forward"] += 1
                continue
            current = lecture_values(obj)
            new = {k: v for k, v in target.items() if current[k] != v}
            if not new:
                stats["unchanged"] += 1
                continue
            db.add(SprintRevisionItem(revision_id=draft.id, lecture_id=obj.id, teaching_plan_id=plan.id, change_type=ChangeType.UPDATE,
                                      old_values={k: current[k] for k in new}, new_values=new,
                                      reason=ChangeReason.SPRINT_MEETING_DECISION.value, remarks=AUTO_REMARK))
            stats["topics"] += 1
        left = [q for q in queue if q[0] == "LEC" and q[1].schedule and q[1].schedule.planned_date
                and start <= q[1].schedule.planned_date <= end]
        if left:
            stats["left_over"] += len(left)
            notes.append(f"{name}: {len(left)} class(es) already dated this week have no timetable slot and stay where they are.")
        waiting = sum(1 for q in queue if q[0] == "CF")
        if waiting:
            notes.append(f"{name}: {waiting} carry-forward item(s) did not fit this week and stay in the carry-forward list.")
    if stats["skipped_plans"]:
        notes.append("Not planned (teaching plan not published): " + ", ".join(stats["skipped_plans"]) + ".")
    if stats["holiday_slots"]:
        notes.append(f"{stats['holiday_slots']} class slot(s) fall on a holiday and were left out.")
    if stats["outside_semester"]:
        notes.append(f"{stats['outside_semester']} class slot(s) are outside the semester dates and were left out.")
    if stats["empty_slots"]:
        notes.append(f"{stats['empty_slots']} class slot(s) have no topic left in the master plan.")
    audit_service.record(db, actor=admin, action="sprint.week_generated", entity_type="sprint_revision", entity_id=draft.id,
                         summary=f"Made the weekly sprint plan (draft) for week of {start:%d %b %Y}: {stats['topics'] + stats['unchanged']} "
                                 f"topic(s) and {stats['carry_forward']} carry-forward item(s) on {stats['slots']} timetable slot(s).",
                         new={k: v for k, v in stats.items() if k != "skipped_plans"})
    db.commit()
    db.expire_all()
    # Completion check for the rest of the semester: is the weekly load still enough? Never changed automatically.
    pace = []
    sp = sprint_plan_service.current(db)
    if sp:
        for sub in sprint_plan_service.detail(db, sp.id)["subjects"]:
            pace.append({k: sub[k] for k in ("plan_id", "subject", "semester", "section", "remaining", "weeks_left", "required_pace",
                                             "weekly_sessions", "at_risk", "extra_sessions_needed", "risk_message", "projected_completion")})
    return admin_week(db, start) | {"generation": stats | {"notes": notes, "pace": pace}}


def _draft(db: Session, revision_id: uuid.UUID) -> SprintRevision:
    rev = db.scalar(select(SprintRevision).where(SprintRevision.id == revision_id).with_for_update(of=SprintRevision))
    if not rev:
        raise NotFound("Sprint revision not found.")
    if rev.status != RevisionStatus.DRAFT:
        raise Conflict("This revision is already published and can no longer be edited. Start a new sprint meeting update.",
                       code="REVISION_CLOSED")
    return rev


def _editable_lecture(db: Session, rev: SprintRevision, lecture_id: uuid.UUID) -> Lecture:
    lec = db.get(Lecture, lecture_id)
    if not lec or lec.teaching_plan.status != PlanStatus.PUBLISHED:
        raise NotFound("Lecture not found in a published plan.")
    d = lec.schedule.planned_date if lec.schedule else None
    placed_here = any(i.lecture_id == lec.id for i in rev.items)  # a pending topic this draft already brought into the week
    if not placed_here and (not d or not (rev.week_start <= d <= rev.week_end)):
        raise BusinessRuleViolation("This lecture is not scheduled in the week being revised.", code="OUTSIDE_WEEK")
    reason = lock_reason(lec)
    if reason:
        raise Conflict(reason + " It can no longer be changed in a sprint meeting.", code="LECTURE_LOCKED")
    return lec


def _check_reason(reason: ChangeReason, remarks: str | None) -> None:
    if reason == ChangeReason.OTHER and not (remarks or "").strip():
        raise BusinessRuleViolation("Add a remark when the reason is Other.", code="REMARK_REQUIRED")


def _clean(db: Session, merged: dict) -> dict:
    """Validate a complete set of lecture values (current + proposed)."""
    if not merged.get("planned_date"):
        raise BusinessRuleViolation("Choose the lecture date.", code="DATE_REQUIRED")
    if date.fromisoformat(merged["planned_date"]) < clock.today():
        raise BusinessRuleViolation("A lecture cannot be moved to a date in the past.", code="DATE_IN_PAST")
    s, e = merged.get("planned_start_time"), merged.get("planned_end_time")
    if not s:
        raise BusinessRuleViolation("Choose the start time.", code="TIME_REQUIRED")
    if e and e <= s:
        raise BusinessRuleViolation("End time must be after start time.", code="TIMES_ORDERED")
    if not (merged.get("content_topic") or "").strip():
        raise BusinessRuleViolation("The topic cannot be empty.", code="TOPIC_REQUIRED")
    if merged["lecture_type"] not in LectureType.__members__:
        raise BusinessRuleViolation("Unknown lecture type.", code="LECTURE_TYPE")
    prof = db.get(User, uuid.UUID(merged["professor_id"]))
    if not prof or not prof.is_active or prof.role_code != Role.PROFESSOR:
        raise BusinessRuleViolation("Choose an active professor.", code="PROFESSOR_INVALID")
    return merged


def _check_calendar(db: Session, plan: TeachingPlan, on: str | None) -> None:
    """A class can only be planned inside its semester and never on a holiday."""
    from app.models import Holiday
    if not on:
        return
    d = date.fromisoformat(on)
    sem = plan.semester
    if d < sem.start_date or d > sem.end_date:
        raise BusinessRuleViolation(f"{d:%d %b %Y} is outside {sem.name} ({sem.start_date:%d %b %Y} – {sem.end_date:%d %b %Y}).",
                                    code="OUTSIDE_SEMESTER")
    holiday = db.scalar(select(Holiday).where(Holiday.date == d))
    if holiday:
        raise BusinessRuleViolation(f"{d:%d %b %Y} is a holiday ({holiday.name}). Choose another day.", code="HOLIDAY")


def _template_map(db: Session) -> dict:
    from app.services import timetable_service
    return timetable_service.template_map(db)


def _normalise(data: dict) -> dict:
    out = {}
    for k, v in data.items():
        if k == "planned_date" and v is not None:
            v = v.isoformat()
        elif k == "professor_id" and v is not None:
            v = str(v)
        elif k == "subtopics" and v is not None:
            v = [t.strip() for t in v if t and t.strip()]
        elif k in ("room", "content_topic") and isinstance(v, str):
            v = v.strip() or None
        out[k] = v
    return out


def edit_lecture(db: Session, admin: User, revision_id: uuid.UUID, lecture_id: uuid.UUID, data: rq.SprintLectureEdit) -> dict:
    rev = _draft(db, revision_id)
    lec = _editable_lecture(db, rev, lecture_id)
    _check_reason(data.reason, data.remarks)
    current = lecture_values(lec)
    proposed = _normalise(data.model_dump(exclude_unset=True, exclude={"reason", "remarks"}))
    item = db.scalar(select(SprintRevisionItem).where(SprintRevisionItem.revision_id == rev.id, SprintRevisionItem.lecture_id == lec.id))
    if item and item.change_type == ChangeType.CANCEL:
        raise Conflict("This lecture is marked for cancellation in this draft. Undo the cancellation first.", code="CANCEL_PENDING")
    # An edit builds on what this draft already changed (e.g. the slot the weekly plan gave the topic); it does not undo it.
    proposed = (item.new_values if item else {}) | proposed
    new = {k: proposed[k] for k in FIELDS if k in proposed and proposed[k] != current[k]}
    if not new:
        if item:
            db.delete(item)
            db.commit()
            db.expire_all()
        return admin_week(db, rev.week_start)
    _clean(db, current | new)
    if "planned_date" in new:
        _check_calendar(db, lec.teaching_plan, new["planned_date"])
    if not item:
        item = SprintRevisionItem(revision_id=rev.id, lecture_id=lec.id, teaching_plan_id=lec.teaching_plan_id, change_type=ChangeType.UPDATE)
        db.add(item)
    item.old_values, item.new_values = {k: current[k] for k in new}, new
    item.reason, item.remarks = data.reason.value, data.remarks
    db.commit()
    db.expire_all()  # the draft's items changed
    return admin_week(db, rev.week_start)


def cancel_lecture(db: Session, admin: User, revision_id: uuid.UUID, lecture_id: uuid.UUID, data: rq.SprintCancel) -> dict:
    rev = _draft(db, revision_id)
    lec = _editable_lecture(db, rev, lecture_id)
    _check_reason(data.reason, data.remarks)
    current = lecture_values(lec)
    item = db.scalar(select(SprintRevisionItem).where(SprintRevisionItem.revision_id == rev.id, SprintRevisionItem.lecture_id == lec.id))
    if not item:
        item = SprintRevisionItem(revision_id=rev.id, lecture_id=lec.id, teaching_plan_id=lec.teaching_plan_id)
        db.add(item)
    item.change_type = ChangeType.CANCEL
    item.old_values = {k: current[k] for k in ("planned_date", "planned_start_time", "planned_end_time", "room", "professor_id")}
    item.new_values = {"is_cancelled": True}
    item.reason, item.remarks = data.reason.value, data.remarks
    db.commit()
    db.expire_all()  # the draft's items changed
    return admin_week(db, rev.week_start)


def add_lecture(db: Session, admin: User, revision_id: uuid.UUID, data: rq.SprintLectureAdd) -> dict:
    rev = _draft(db, revision_id)
    _check_reason(data.reason, data.remarks)
    plan = db.get(TeachingPlan, data.teaching_plan_id)
    if not plan or plan.status != PlanStatus.PUBLISHED:
        raise NotFound("Choose a published teaching plan.")
    if not (rev.week_start <= data.planned_date <= rev.week_end):
        raise BusinessRuleViolation("The new lecture must fall in the week being revised.", code="OUTSIDE_WEEK")
    source = None
    if data.carry_forward_lecture_id:
        source = db.get(Lecture, data.carry_forward_lecture_id)
        if not source or source.teaching_plan_id != plan.id:
            raise BusinessRuleViolation("The carry-forward item belongs to a different teaching plan.", code="CARRY_FORWARD_PLAN")
        if any(i.carry_forward_lecture_id == source.id for i in rev.items):
            raise Conflict("This carry-forward item is already placed in this draft.", code="CARRY_FORWARD_PLACED")
        done = db.scalar(select(CarryForwardItem).where(CarryForwardItem.source_lecture_id == source.id))
        if done and done.status in (CarryForwardStatus.SCHEDULED, CarryForwardStatus.RESOLVED):
            raise Conflict("This carry-forward item has already been handled.", code="CARRY_FORWARD_CLOSED")
    values = _clean(db, _normalise({
        "planned_date": data.planned_date, "planned_start_time": data.planned_start_time, "planned_end_time": data.planned_end_time,
        "room": data.room or plan.room, "professor_id": data.professor_id or plan.professor_id,
        "content_topic": data.content_topic, "subtopics": data.subtopics, "lecture_type": data.lecture_type,
    }))
    _check_calendar(db, plan, values["planned_date"])
    db.add(SprintRevisionItem(revision_id=rev.id, teaching_plan_id=plan.id, change_type=ChangeType.ADD, old_values=None,
                              new_values=values, reason=data.reason.value, remarks=data.remarks,
                              carry_forward_lecture_id=source.id if source else None))
    db.commit()
    db.expire_all()  # the draft's items changed
    return admin_week(db, rev.week_start)


def remove_item(db: Session, admin: User, revision_id: uuid.UUID, item_id: uuid.UUID) -> dict:
    rev = _draft(db, revision_id)
    item = db.get(SprintRevisionItem, item_id)
    if not item or item.revision_id != rev.id:
        raise NotFound("Change not found in this draft.")
    db.delete(item)
    db.commit()
    db.expire_all()  # the draft's items changed
    return admin_week(db, rev.week_start)


def update_meeting(db: Session, admin: User, revision_id: uuid.UUID, data: rq.SprintMeetingUpdate) -> dict:
    rev = _draft(db, revision_id)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(rev, k, v)
    db.commit()
    return revision_brief(rev)


def discard(db: Session, admin: User, revision_id: uuid.UUID) -> dict:
    rev = _draft(db, revision_id)
    start = rev.week_start
    rev.status = RevisionStatus.DISCARDED
    audit_service.record(db, actor=admin, action="sprint.revision_discarded", entity_type="sprint_revision", entity_id=rev.id,
                         summary=f"Discarded the draft sprint update for week of {start:%d %b %Y} ({len(rev.items)} unpublished changes).")
    db.commit()
    db.expire_all()
    return admin_week(db, start)


# ------------------------------------------------------------------ review & publish

def _day_conflicts(days: list[dict], tmap: dict | None = None) -> list[dict]:
    """What the draft would break, on real clock intervals: one professor, one section or one room in two
    classes at once, or a class running into ITS OWN year group's lunch (never the other group's)."""
    from app.services import timetable_service as tt
    tmap = tmap or {}
    out = []
    label = lambda r: (f"{r['subject']['short_name'] or r['subject']['code']} "  # noqa: E731
                       f"{r['semester'].replace('Semester', 'Sem')}-{r['section']} {r['start']}–{r['end'] or '?'}")
    for day in days:
        rows = [r for r in day["lectures"] if not r["is_cancelled"] and r["start"]
                and not (r["draft"] and (r["draft"]["change_type"] == ChangeType.CANCEL or r["draft"]["moved_out"]))]
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                if not (a["draft"] or b["draft"] or not a.get("released", True) or not b.get("released", True)):
                    continue  # only report clashes this draft, or a class not published yet, is part of
                overlap = a["start"] < (b["end"] or "24:00") and b["start"] < (a["end"] or "24:00")
                if not overlap:
                    continue
                keys = [r["key"] for r in (a, b)]
                shared = f"Overlap: {max(a['start'], b['start'])}–{min(a['end'] or '24:00', b['end'] or '24:00')}."
                if a["professor"]["id"] == b["professor"]["id"]:
                    out.append({"date": day["date"], "kind": "PROFESSOR", "level": "ERROR", "keys": keys,
                                "message": f"{a['professor']['full_name']} already has an overlapping class ({label(a)} and {label(b)}). {shared}"})
                if a.get("section_id") and a.get("section_id") == b.get("section_id"):
                    out.append({"date": day["date"], "kind": "SECTION", "level": "ERROR", "keys": keys,
                                "message": f"{a['semester'].replace('Semester', 'Sem')}-{a['section']} cannot attend two classes at once "
                                           f"({label(a)} and {label(b)}). {shared}"})
                if a["room"] and b["room"] and a["room"].strip().lower() == b["room"].strip().lower():
                    out.append({"date": day["date"], "kind": "ROOM", "level": "ERROR", "keys": keys,
                                "message": f"Room {a['room']} is double-booked ({label(a)} and {label(b)}). {shared}"})
        for r in rows:
            tpl = tmap.get(r.get("semester_number"))
            if not ((r["draft"] or not r.get("released", True)) and tpl and r["end"]):
                continue
            lunch = tt.lunch_overlap(tpl, time.fromisoformat(r["start"]), time.fromisoformat(r["end"]))
            if lunch:
                out.append({"date": day["date"], "kind": "LUNCH", "level": "ERROR", "keys": [r["key"]],
                            "message": f"{label(r)} runs into the {tpl.name} {lunch.slot_type.lower()} "
                                       f"({lunch.start_time:%H:%M}–{lunch.end_time:%H:%M})."})
    return out


def _moved_conflicts(db: Session, moved: list[tuple[Lecture, dict]], names: dict[str, str]) -> list[dict]:
    """A lecture moved out of the revised week must also be free on the day it lands on."""
    from app.services import conflict_service as cs
    slots = []
    for lec, v in moved:
        if not v.get("planned_start_time"):
            continue
        plan = lec.teaching_plan
        slots.append(cs.Slot(
            on=date.fromisoformat(v["planned_date"]), start=time.fromisoformat(v["planned_start_time"]),
            end=time.fromisoformat(v["planned_end_time"]) if v.get("planned_end_time") else None,
            professor_id=uuid.UUID(v["professor_id"]), professor_name=names.get(v["professor_id"]) or lec.effective_professor.full_name,
            room=(v.get("room") or "").strip() or None, lecture_id=lec.id, plan_id=plan.id,
            label=f"{plan.subject.short_name or plan.subject.code} Lecture {lec.lecture_no} "
                  f"({plan.semester.name.replace('Semester', 'Sem')}-{plan.section.name})"))
    out = []
    moved_ids = {s.lecture_id for s in slots}
    for i, slot in enumerate(slots):
        others = cs.published_slots(db, slot.on, slot.on, exclude_lecture_ids=moved_ids) + slots[i + 1:]
        out.extend({**c, "keys": [str(slot.lecture_id)]} for c in cs.clashes(slot, others))
    return out


def _conflicts(db: Session, rev: SprintRevision) -> list[dict]:
    return admin_week(db, rev.week_start)["conflicts"]


def changes(db: Session, revision_id: uuid.UUID) -> dict:
    rev = db.get(SprintRevision, revision_id)
    if not rev or rev.status == RevisionStatus.DISCARDED:
        raise NotFound("Sprint revision not found.")
    names = _names(db, [i.old_values for i in rev.items] + [i.new_values for i in rev.items])
    return {"revision": revision_brief(rev), "week": week_info(db, rev.week_start),
            "changes": [item_view(i, names, revision=rev) for i in rev.items],
            "conflicts": _conflicts(db, rev) if rev.status == RevisionStatus.DRAFT else []}


def _apply_subtopics(lec: Lecture, titles: list[str]) -> None:
    existing = {s.position: s for s in lec.subtopics}
    for pos, title in enumerate(titles, start=1):
        if pos in existing:
            existing[pos].title = title
        else:
            lec.subtopics.append(LectureSubtopic(position=pos, title=title))
    for pos, sub in existing.items():
        if pos > len(titles):
            lec.subtopics.remove(sub)


def _apply_values(lec: Lecture, new: dict) -> None:
    plan = lec.teaching_plan
    sch = lec.schedule or LectureSchedule(lecture_id=lec.id)
    lec.schedule = sch
    if "planned_date" in new:
        sch.planned_date = date.fromisoformat(new["planned_date"])
        pr = lec.progress
        if pr and pr.execution_status == ExecutionStatus.RESCHEDULED:  # the admin's date supersedes the professor's request
            pr.execution_status, pr.rescheduled_to = ExecutionStatus.SCHEDULED, None
    if "planned_start_time" in new:
        sch.planned_start_time = time.fromisoformat(new["planned_start_time"]) if new["planned_start_time"] else None
    if "planned_end_time" in new:
        sch.planned_end_time = time.fromisoformat(new["planned_end_time"]) if new["planned_end_time"] else None
    if "room" in new:
        sch.room = new["room"]
    if "professor_id" in new:
        pid = uuid.UUID(new["professor_id"])
        lec.professor_id = None if pid == plan.professor_id else pid
        if lec.progress:
            lec.progress.professor_id = pid
    if "content_topic" in new:
        lec.content_topic = new["content_topic"]
    if "lecture_type" in new:
        lec.lecture_type = new["lecture_type"]
    if "subtopics" in new:
        _apply_subtopics(lec, new["subtopics"])


def publish(db: Session, admin: User, revision_id: uuid.UUID, data: rq.SprintPublish) -> dict:
    rev = _draft(db, revision_id)
    blocking = [c for c in _conflicts(db, rev) if c["level"] == "ERROR"]
    if blocking:
        raise Conflict("Schedule conflict: " + blocking[0]["message"] + " Change the professor or the time, then publish again.",
                       code="SCHEDULE_CONFLICT", details={"conflicts": blocking})
    if data.meeting_notes is not None:
        rev.meeting_notes = data.meeting_notes
    now = clock.now_utc()
    number = (db.scalar(select(func.max(SprintRevision.revision_number)).where(
        SprintRevision.week_start == rev.week_start, SprintRevision.status == RevisionStatus.PUBLISHED)) or 1) + 1
    label = f"Week of {rev.week_start:%d %b %Y} v{number}"
    affected: dict[uuid.UUID, int] = defaultdict(int)

    for item in rev.items:
        plan = item.teaching_plan
        subject = plan.subject.short_name or plan.subject.code
        reason = REASON_LABELS[ChangeReason(item.reason)]
        if item.change_type == ChangeType.ADD:
            v = _clean(db, dict(item.new_values))
            last_no, last_seq = db.execute(select(func.max(Lecture.lecture_no), func.max(Lecture.sequence))
                                           .where(Lecture.teaching_plan_id == plan.id)).one()
            source = db.get(Lecture, item.carry_forward_lecture_id) if item.carry_forward_lecture_id else None
            pid = uuid.UUID(v["professor_id"])
            lec = Lecture(teaching_plan_id=plan.id, sequence=(last_seq or 0) + 1, lecture_no=(last_no or 0) + 1,
                          lecture_type=v["lecture_type"], unit_no=source.unit_no if source else None,
                          blooms_taxonomy=source.blooms_taxonomy if source else None, content_topic=v["content_topic"],
                          professor_id=None if pid == plan.professor_id else pid,
                          origin=LectureOrigin.CARRY_FORWARD if source else LectureOrigin.SPRINT_ADDED,
                          carried_from_lecture_id=source.id if source else None)
            lec.subtopics = [LectureSubtopic(position=i, title=t) for i, t in enumerate(v["subtopics"], start=1)]
            lec.schedule = LectureSchedule(planned_date=date.fromisoformat(v["planned_date"]),
                                           planned_start_time=time.fromisoformat(v["planned_start_time"]),
                                           planned_end_time=time.fromisoformat(v["planned_end_time"]) if v["planned_end_time"] else None,
                                           room=v["room"])
            db.add(lec)
            db.flush()
            item.lecture_id = lec.id
            if source:
                decision = db.scalar(select(CarryForwardItem).where(CarryForwardItem.source_lecture_id == source.id))
                if not decision:
                    decision = CarryForwardItem(source_lecture_id=source.id, decided_by_id=admin.id, decided_at=now,
                                                status=CarryForwardStatus.SCHEDULED)
                    db.add(decision)
                decision.status, decision.target_lecture_id = CarryForwardStatus.SCHEDULED, lec.id
                decision.decided_by_id, decision.decided_at = admin.id, now
            affected[pid] += 1
            audit_service.record(
                db, actor=admin, action="sprint.topic_carried_forward" if source else "sprint.lecture_added", entity_type="lecture",
                entity_id=lec.id, new=v | {"reason": reason, "revision": label}, scope_type="teaching_plan", scope_id=plan.id,
                summary=(f"Carried “{v['content_topic']}” forward from Lecture {source.lecture_no} to {subject} Lecture {lec.lecture_no}"
                         if source else f"Added {subject} Lecture {lec.lecture_no} “{v['content_topic']}”") + f" on {v['planned_date']} ({label}).")
            continue

        lec = db.scalar(select(Lecture).where(Lecture.id == item.lecture_id).with_for_update(of=Lecture))
        locked = lock_reason(lec)
        if locked:
            raise Conflict(f"{subject} Lecture {lec.lecture_no} can no longer be changed: {locked} Remove this change and publish again.",
                           code="LECTURE_LOCKED", details={"item_id": str(item.id), "lecture_id": str(lec.id)})
        current = lecture_values(lec)
        old_prof = lec.effective_professor_id
        if lec.master_snapshot is None:
            lec.master_snapshot = current | {"lecture_no": lec.lecture_no}  # the semester master plan's values, kept forever
        if item.change_type == ChangeType.CANCEL:
            lec.is_cancelled, lec.cancel_reason = True, f"{reason}{f': {item.remarks}' if item.remarks else ''}"
            affected[old_prof] += 1
            audit_service.record(db, actor=admin, action="sprint.lecture_cancelled", entity_type="lecture", entity_id=lec.id,
                                 summary=f"Cancelled {subject} Lecture {lec.lecture_no} ({label}). Reason: {reason}.",
                                 old=item.old_values, new={"is_cancelled": True, "reason": reason, "revision": label},
                                 scope_type="teaching_plan", scope_id=plan.id)
            continue
        new = {k: v for k, v in item.new_values.items() if current.get(k) != v}
        _clean(db, current | new)
        item.old_values = {k: current[k] for k in new}  # the diff as of publishing, not as of drafting
        item.new_values = new
        _apply_values(lec, new)
        affected[old_prof] += 1
        if "professor_id" in new:
            affected[uuid.UUID(new["professor_id"])] += 1
        fields = ", ".join(FIELD_LABELS[k].lower() for k in new) or "nothing"
        audit_service.record(db, actor=admin, action="sprint.lecture_changed", entity_type="lecture", entity_id=lec.id,
                             summary=f"Changed {fields} of {subject} Lecture {lec.lecture_no} ({label}). Reason: {reason}.",
                             old=item.old_values, new=new | {"reason": reason, "revision": label},
                             scope_type="teaching_plan", scope_id=plan.id)

    # Publishing a week releases every class in it: from now on professors, CL/CH and OM see them.
    db.flush()
    released = 0
    for lec in _week_lectures(db, rev.week_start, rev.week_end):
        if not lec.is_released and not lec.is_cancelled:
            lec.is_released = True
            released += 1
            affected[lec.effective_professor_id] += 1
    rev.status, rev.revision_number, rev.published_by_id, rev.published_at = RevisionStatus.PUBLISHED, number, admin.id, now
    audit_service.record(db, actor=admin, action="sprint.revision_published", entity_type="sprint_revision", entity_id=rev.id,
                         summary=f"Published sprint revision {label} with {len(rev.items)} change(s)"
                                 + (f" and {released} class(es) released to professors." if released else "."),
                         new={"revision_number": number, "changes": len(rev.items), "released": released, "meeting_notes": rev.meeting_notes})
    week_label = f"{rev.week_start:%d %b} – {rev.week_start + timedelta(days=5):%d %b %Y}"
    for pid, count in affected.items():  # one consolidated notification per professor, not one per field
        notification_service.notify(
            db, pid, kind="sprint.updated", title="Sprint Plan Updated",
            body=f"Your Sprint Plan for {week_label} has been updated (v{number}). {count} lecture schedule{'s were' if count != 1 else ' was'} changed.",
            link=f"/professor/sprint-plan?week={rev.week_start.isoformat()}&changes={rev.id}")
    db.commit()
    db.expire_all()
    return changes(db, rev.id)


def publish_week(db: Session, admin: User, week_start: date) -> dict:
    """PUBLISH for a week: opens the week's draft if there is none and publishes it as it stands."""
    start, end = week_bounds(week_start)
    if end < clock.today():
        raise BusinessRuleViolation("This week is over and can no longer be published.", code="WEEK_OVER")
    draft = _draft_for(db, start)
    if not draft:
        draft = SprintRevision(week_start=start, week_end=end, status=RevisionStatus.DRAFT, created_by_id=admin.id, meeting_date=clock.today())
        db.add(draft)
        db.commit()
    publish(db, admin, draft.id, rq.SprintPublish())
    return admin_week(db, start)


def history(db: Session, *, limit: int = 200) -> list[dict]:
    revs = db.scalars(select(SprintRevision).where(SprintRevision.status != RevisionStatus.DISCARDED)
                      .order_by(SprintRevision.week_start.desc(), SprintRevision.revision_number.desc().nullsfirst()).limit(limit)).unique()
    return [revision_brief(r) | {"week": week_info(db, r.week_start)} for r in revs]


# ------------------------------------------------------------------ professor views (published data only)

def professor_week(db: Session, professor: User, week_start: date | None) -> dict:
    start, end = week_bounds(week_start)
    lectures = _week_lectures(db, start, end, professor_id=professor.id, released_only=True)
    latest_items = _latest_published_items(db, [l.id for l in lectures])
    names = _names(db, [i.old_values for i in latest_items.values()] + [i.new_values for i in latest_items.values()])
    published = _published_for(db, start)
    today = clock.today()
    rows = []
    for lec in lectures:
        if lec.is_cancelled:
            continue
        row = lecture_row(lec)
        item = latest_items.get(lec.id)
        pr = lec.progress
        delivered = row["execution_status"] in DELIVERED
        row |= {
            "revised": item_view(item, names) if item else None,
            "needs_update": bool(not delivered and row["execution_status"] != ExecutionStatus.NOT_CONDUCTED and lec.schedule.planned_date < today),
            "needs_submission": bool(delivered and pr and pr.submission_status in (SubmissionStatus.DRAFT, SubmissionStatus.CORRECTION_REQUIRED)),
        }
        rows.append(row)

    delivered_rows = [r for r in rows if r["execution_status"] in DELIVERED]
    completed = sum(1 for r in rows if r["execution_status"] == ExecutionStatus.COMPLETED)
    today_open = sum(1 for r in rows if r["date"] == today.isoformat() and r["execution_status"] not in DELIVERED)
    upcoming = sum(1 for r in rows if r["date"] > today.isoformat())
    pending = sum(1 for r in rows if r["needs_update"] or r["needs_submission"])

    from app.services import report_service  # local import: report_service is imported by many services
    courses = []
    for plan_id in dict.fromkeys(r["plan_id"] for r in rows):
        mine = [r for r in rows if r["plan_id"] == plan_id]
        done = sum(1 for r in mine if r["execution_status"] in DELIVERED)
        sem = report_service.summarize(report_service.facts(db, plan_id=uuid.UUID(plan_id), professor_id=professor.id))
        courses.append({"plan_id": plan_id, "subject": mine[0]["subject"], "section": mine[0]["section"],
                        "scheduled": len(mine), "delivered": done, "sprint_pct": round(done * 100 / len(mine)) if mine else 0,
                        "semester_pct": sem["execution_pct"], "semester_completed": sem["completed"], "semester_total": sem["total"]})
    return {
        "week": week_info(db, start), "today": today.isoformat(),
        "version": published[-1].revision_number if published else 1,
        "revision": revision_brief(published[-1]) if published else None,
        "changed_for_me": sum(1 for r in rows if r["revised"]),
        "metrics": {"total": len(rows), "completed": completed, "delivered": len(delivered_rows), "today_open": today_open,
                    "upcoming": upcoming, "pending_action": pending,
                    "verified": sum(1 for r in rows if r["submission_status"] == SubmissionStatus.FINAL_VERIFIED),
                    "pace_pct": round(len(delivered_rows) * 100 / len(rows)) if rows else 0},
        "days": _days(start, rows),
        "courses": courses,
    }


def professor_history(db: Session, professor: User) -> list[dict]:
    rows = db.execute(
        select(LectureSchedule.planned_date, LectureProgress.execution_status)
        .join(Lecture, LectureSchedule.lecture_id == Lecture.id).join(TeachingPlan, Lecture.teaching_plan_id == TeachingPlan.id)
        .outerjoin(LectureProgress, LectureProgress.lecture_id == Lecture.id)
        .where(TeachingPlan.status == PlanStatus.PUBLISHED, Lecture.is_cancelled.is_(False), LectureSchedule.planned_date.is_not(None),
               Lecture.is_released.is_(True),
               func.coalesce(Lecture.professor_id, TeachingPlan.professor_id) == professor.id)).all()
    weeks: dict[date, list] = defaultdict(list)
    for d, status in rows:
        weeks[monday(d)].append(status)
    versions = dict(db.execute(select(SprintRevision.week_start, func.max(SprintRevision.revision_number))
                               .where(SprintRevision.status == RevisionStatus.PUBLISHED).group_by(SprintRevision.week_start)).all())
    return [{"week": week_info(db, start), "lectures": len(statuses), "delivered": sum(1 for s in statuses if s in DELIVERED),
             "version": versions.get(start, 1)}
            for start, statuses in sorted(weeks.items(), reverse=True)]


def professor_changes(db: Session, professor: User, revision_id: uuid.UUID) -> dict:
    rev = db.get(SprintRevision, revision_id)
    if not rev or rev.status != RevisionStatus.PUBLISHED:  # a draft is never shown to a professor
        raise NotFound("Sprint revision not found.")
    me = str(professor.id)
    mine = [i for i in rev.items if me in ((i.old_values or {}).get("professor_id"), (i.new_values or {}).get("professor_id"))
            or (i.lecture and i.lecture.effective_professor_id == professor.id)]
    names = _names(db, [i.old_values for i in mine] + [i.new_values for i in mine])
    return {"revision": revision_brief(rev) | {"change_count": len(mine)}, "week": week_info(db, rev.week_start),
            "changes": [item_view(i, names, revision=rev) for i in mine]}


# ------------------------------------------------------------------ the same sprint plan, seen by CL/CH, OM and Admin

def sheet_week(db: Session, viewer: User, week_start: date | None, *, professor_id: uuid.UUID | None = None,
               subject_id: uuid.UUID | None = None) -> dict:
    """One week of the published Sprint Plan as a single sheet: planning, execution, CL/CH, OM, final status.

    Admin sees every row; CL/CH and OM see the rows inside their scope. Nothing here is editable - the
    planning columns belong to the Admin's sprint meeting and the execution columns to the professor.
    """
    from app.core.enums import MaterialType, VerificationLevel
    from app.services import operations_service, scope_service

    start, end = week_bounds(week_start)
    extra = list(scope_service.plan_filter(viewer))
    if subject_id:
        extra.append(TeachingPlan.subject_id == subject_id)
    lectures = _week_lectures(db, start, end, professor_id=professor_id, extra=extra, released_only=True)
    published = _published_for(db, start)
    my_level = {Role.CL_CH: VerificationLevel.CL_CH, Role.OM: VerificationLevel.OM}.get(viewer.role_code)
    rows = []
    for lec in lectures:
        if lec.is_cancelled:
            continue
        pr = lec.progress
        ops = operations_service.class_row(lec)
        chain = ops["verification"]
        steps = {st["level"]: st for st in chain["steps"]}
        current = [v for v in (pr.verifications if pr else []) if v.round == pr.submission_count and v.status == VerificationStatus.PENDING]
        mine = next((v for v in current if my_level and v.verification_level == my_level), None)
        anyv = next(iter(sorted((pr.verifications if pr else []), key=lambda v: v.created_at, reverse=True)), None)
        materials = pr.materials if pr else []
        covered_ids = {s.subtopic_id for s in (pr.subtopic_progress if pr else []) if s.is_covered}
        rows.append(lecture_row(lec) | {
            "blooms_taxonomy": lec.blooms_taxonomy,
            "covered_topics": [s.title for s in lec.subtopics if s.id in covered_ids],
            "remaining_topics": [s.title for s in lec.subtopics if s.id not in covered_ids] if pr else [],
            "notes": [{"title": m.title, "url": m.file_url} for m in materials if m.material_type == MaterialType.LECTURE_NOTES],
            "assignment": None if not pr or not pr.assignment else {"title": pr.assignment.title, "url": pr.assignment.link_url},
            "evidence_count": sum(1 for m in materials if m.material_type in (MaterialType.CLASS_EVIDENCE, MaterialType.CHECKIN_IMAGE)),
            "shared_with_students": pr.shared_with_students if pr else None,
            "professor_remarks": pr.remarks if pr else None,
            "recording_url": pr.recording_url if pr else None, "additional_topics": pr.additional_topics if pr else None,
            "submitted_at": ser._iso(pr.submitted_at) if pr else None,
            "clch": {"status": chain["levels"]["CL_CH"], "remarks": (steps.get("CL_CH") or {}).get("remarks"),
                     "by": ((steps.get("CL_CH") or {}).get("verifier") or {}).get("full_name"),
                     "at": (steps.get("CL_CH") or {}).get("verified_at")},
            "om": {"status": chain["levels"]["OM"], "remarks": (steps.get("OM") or {}).get("remarks"),
                   "by": ((steps.get("OM") or {}).get("verifier") or {}).get("full_name"),
                   "at": (steps.get("OM") or {}).get("verified_at"),
                   "entry_time": ops["entry_time"], "exit_time": ops["exit_time"], "timing_status": ops["timing_status"],
                   "delay_minutes": ops["delay_minutes"], "state": ops["state"]},
            "final_status": "FINAL_VERIFIED" if pr and pr.submission_status == SubmissionStatus.FINAL_VERIFIED else (
                "CORRECTION_REQUIRED" if pr and pr.submission_status == SubmissionStatus.CORRECTION_REQUIRED else "PENDING"),
            "waiting_for": chain["waiting_for"],
            # The step waiting for the signed-in verifier, if any -> "Review" opens it directly.
            "my_verification_id": str(mine.id) if mine else None,
            "latest_verification_id": str(anyv.id) if anyv else None,
        })
    summary = {
        "total": len(rows),
        "submitted": sum(1 for r in rows if r["submission_status"] in ("SUBMITTED", "RESUBMITTED", "FINAL_VERIFIED")),
        "clch_pending": sum(1 for r in rows if r["clch"]["status"] == VerificationStatus.PENDING),
        "clch_verified": sum(1 for r in rows if r["clch"]["status"] == VerificationStatus.VERIFIED),
        "om_pending": sum(1 for r in rows if r["om"]["status"] == VerificationStatus.PENDING),
        "final_verified": sum(1 for r in rows if r["final_status"] == "FINAL_VERIFIED"),
        "correction_required": sum(1 for r in rows if r["final_status"] == "CORRECTION_REQUIRED"),
    }
    return {"week": week_info(db, start), "today": clock.today().isoformat(),
            "version": published[-1].revision_number if published else 1,
            "scope": scope_service.describe(db, viewer), "role": viewer.role_code.value,
            "summary": summary, "rows": rows, "days": _days(start, rows)}
