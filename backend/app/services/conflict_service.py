"""Schedule clashes: one professor, or one room, in two classes at the same time.

A professor clash blocks publishing - a person cannot teach two classes at once.
A room clash is reported as a warning: rooms are free text and two sections may
legitimately share a hall, so the administrator decides.

Only published, non-cancelled lectures count as "already allocated".
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, time

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.enums import PlanStatus
from app.models import Lecture, LectureSchedule, TeachingPlan


@dataclass(frozen=True)
class Slot:
    """One class occupying a professor and (maybe) a room for a period on a day."""
    on: date
    start: time
    end: time | None
    professor_id: uuid.UUID | None
    professor_name: str
    room: str | None
    label: str                      # "DSA Lecture 4 (Sem V-A)"
    lecture_id: uuid.UUID | None = None
    plan_id: uuid.UUID | None = None


DEFAULT_MINUTES = 60


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def overlaps(a: Slot, b: Slot) -> bool:
    if a.on != b.on:
        return False
    # A class without an end time is taken to last one hour - long enough to catch a real clash.
    a_end = _minutes(a.end) if a.end else _minutes(a.start) + DEFAULT_MINUTES
    b_end = _minutes(b.end) if b.end else _minutes(b.start) + DEFAULT_MINUTES
    return _minutes(a.start) < b_end and _minutes(b.start) < a_end


def _span(s: Slot) -> str:
    return f"{s.start:%H:%M}–{s.end:%H:%M}" if s.end else f"{s.start:%H:%M}"


def lecture_slot(lec: Lecture) -> Slot | None:
    sch = lec.schedule
    if not sch or not sch.planned_date or not sch.planned_start_time:
        return None
    plan = lec.teaching_plan
    prof = lec.effective_professor
    return Slot(on=sch.planned_date, start=sch.planned_start_time, end=sch.planned_end_time,
                professor_id=prof.id, professor_name=prof.full_name, room=(sch.room or plan.room or "").strip() or None,
                label=f"{plan.subject.short_name or plan.subject.code} Lecture {lec.lecture_no} "
                      f"({plan.semester.name.replace('Semester', 'Sem')}-{plan.section.name})",
                lecture_id=lec.id, plan_id=plan.id)


def published_slots(db: Session, start: date, end: date, *, exclude_plan_id: uuid.UUID | None = None,
                    exclude_lecture_ids: set[uuid.UUID] | None = None) -> list[Slot]:
    stmt = (select(Lecture).join(TeachingPlan, Lecture.teaching_plan_id == TeachingPlan.id)
            .join(LectureSchedule, LectureSchedule.lecture_id == Lecture.id)
            .where(TeachingPlan.status == PlanStatus.PUBLISHED, Lecture.is_cancelled.is_(False),
                   LectureSchedule.planned_date.between(start, end), LectureSchedule.planned_start_time.is_not(None))
            .options(selectinload(Lecture.schedule), selectinload(Lecture.teaching_plan)))
    if exclude_plan_id:
        stmt = stmt.where(TeachingPlan.id != exclude_plan_id)
    out = []
    for lec in db.scalars(stmt).unique():
        if exclude_lecture_ids and lec.id in exclude_lecture_ids:
            continue
        slot = lecture_slot(lec)
        if slot:
            out.append(slot)
    return out


def clashes(candidate: Slot, others: list[Slot]) -> list[dict]:
    """Every clash between one class and a list of already-allocated classes."""
    out = []
    for o in others:
        if o.lecture_id and o.lecture_id == candidate.lecture_id:
            continue
        if not overlaps(candidate, o):
            continue
        if candidate.professor_id and candidate.professor_id == o.professor_id:
            out.append({"kind": "PROFESSOR", "level": "ERROR", "date": candidate.on.isoformat(),
                        "lecture_id": str(candidate.lecture_id) if candidate.lecture_id else None,
                        "message": f"{candidate.professor_name} already has an overlapping class: {o.label}, {_span(o)} "
                                   f"on {o.on:%d %b %Y} (this class: {candidate.label}, {_span(candidate)})."})
        if candidate.room and o.room and candidate.room.lower() == o.room.lower():
            out.append({"kind": "ROOM", "level": "WARNING", "date": candidate.on.isoformat(),
                        "lecture_id": str(candidate.lecture_id) if candidate.lecture_id else None,
                        "message": f"Room {candidate.room} is already allocated to {o.label}, {_span(o)} on {o.on:%d %b %Y} "
                                   f"(this class: {candidate.label}, {_span(candidate)})."})
    return out


def within(slots: list[Slot]) -> list[dict]:
    """Clashes inside one set of classes (each pair reported once)."""
    out = []
    ordered = sorted(slots, key=lambda s: (s.on, s.start))
    for i, a in enumerate(ordered):
        out.extend(clashes(a, [b for b in ordered[i + 1:] if b.on == a.on]))
    return out


def plan_conflicts(db: Session, plan: TeachingPlan) -> list[dict]:
    """A plan about to be published, checked against itself and against everything already published."""
    mine = [s for s in (lecture_slot(l) for l in plan.lectures if not l.is_cancelled) if s]
    if not mine:
        return []
    others = published_slots(db, min(s.on for s in mine), max(s.on for s in mine), exclude_plan_id=plan.id)
    out = within(mine)
    for s in mine:
        out.extend(clashes(s, others))
    return out


def blocking(conflicts: list[dict]) -> list[dict]:
    return [c for c in conflicts if c["level"] == "ERROR"]
