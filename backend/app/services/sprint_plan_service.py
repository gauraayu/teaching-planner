"""Semester sprint plan: the one schedule the institution runs on.

    CREATE SPRINT PLAN (dates, working days)
        -> add subjects (subject + section + professor + weekly sessions) and import their curriculum
        -> GENERATE SEMESTER SPRINT   every topic gets a date, time and room inside the semester
        -> weeks are published one by one; only a published week reaches professors, CL/CH and OM
        -> MAKE WEEKLY SPRINT PLAN    next week's draft from what was actually taught (see sprint_service)

There is no separate timetable to maintain. The recurring weekly pattern (which periods a subject meets in) is
derived here from the weekly-session requirements and kept internally; conflicts are always checked on real
start and end times, and each year group follows its own timing template and its own lunch.

Lectures that are not released yet are a projection: they are re-flowed freely whenever the plan is generated
again or a week is made, and nothing a professor has seen or recorded is ever moved that way.
"""
from __future__ import annotations

import math
import uuid
from collections import defaultdict
from datetime import date, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core import clock
from app.core.enums import ExecutionStatus, LectureType, PlanStatus, SprintPlanStatus
from app.core.errors import BusinessRuleViolation, Conflict, NotFound
from app.models import (
    AcademicYear, ClassSession, Holiday, Lecture, LectureProgress, LectureSchedule, LectureSubtopic, SemesterSprintPlan,
    TeachingPlan, TimetableEntry, User,
)
from app.schemas import requests as rq
from app.services import audit_service
from app.services import serializers as ser
from app.services import timetable_service as tt

DELIVERED = (ExecutionStatus.COMPLETED, ExecutionStatus.PARTIALLY_COMPLETED)
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


# ------------------------------------------------------------------ calendar

def _holidays(db: Session, start: date, end: date) -> dict[date, str]:
    return {h.date: h.name for h in db.scalars(select(Holiday).where(Holiday.date.between(start, end)))}


def teaching_days(sp: SemesterSprintPlan, holidays: dict[date, str], start: date | None = None) -> list[date]:
    days, d = [], max(start or sp.start_date, sp.start_date)
    working = set(sp.working_days or [])
    while d <= sp.end_date:
        if d.weekday() in working and d not in holidays:
            days.append(d)
        d += timedelta(days=1)
    return days


def calendar(db: Session, sp: SemesterSprintPlan) -> dict:
    holidays = _holidays(db, sp.start_date, sp.end_date)
    working = set(sp.working_days or [])
    all_working = [sp.start_date + timedelta(days=i) for i in range((sp.end_date - sp.start_date).days + 1)
                   if (sp.start_date + timedelta(days=i)).weekday() in working]
    teach = [d for d in all_working if d not in holidays]
    weeks = sorted({monday(d) for d in all_working})
    return {
        "calendar_days": (sp.end_date - sp.start_date).days + 1, "total_weeks": len(weeks),
        "working_weeks": len({monday(d) for d in teach}), "working_days": len(all_working),
        "holidays": [{"date": d.isoformat(), "name": n} for d, n in sorted(holidays.items()) if d.weekday() in working],
        "teaching_days": len(teach),
    }


# ------------------------------------------------------------------ re-flow: topics onto dated slots

def pattern(db: Session, plan_id: uuid.UUID) -> list[TimetableEntry]:
    return sorted((e for e in tt.published_entries(db) if e.teaching_plan_id == plan_id), key=lambda e: (e.weekday, e.start_time))


def _lectures(db: Session, plan_id: uuid.UUID) -> list[Lecture]:
    return list(db.scalars(select(Lecture).where(Lecture.teaching_plan_id == plan_id, Lecture.is_cancelled.is_(False))
                           .order_by(Lecture.sequence)
                           .options(selectinload(Lecture.schedule), selectinload(Lecture.progress), selectinload(Lecture.subtopics),
                                    selectinload(Lecture.class_session))).unique())


def pick(types: list[str], lab_slot: bool, typed: bool) -> int:
    """Which waiting item a slot takes. When a subject has both lab and class slots, a lab slot takes the next
    practical and a class slot the next non-practical; otherwise simply the next in order."""
    if typed:
        return next((i for i, t in enumerate(types) if (t == LectureType.PRACTICAL) == lab_slot), 0)
    return 0


def reflow(db: Session, plan: TeachingPlan, start: date, *, reserve: list[str] | None = None,
           holidays: dict[date, str] | None = None) -> dict:
    """Give every not-yet-released topic of one subject its next free slot from `start` to the semester end, in
    curriculum order. `reserve` (lecture types) keeps the first slots free for carry-forward work and returns them.
    Published classes keep their place; topics that do not fit before the end date are left undated."""
    sp = plan.sprint_plan
    entries = pattern(db, plan.id)
    holidays = holidays if holidays is not None else _holidays(db, sp.start_date, sp.end_date)
    lectures = _lectures(db, plan.id)
    pending = [l for l in lectures if not l.is_released and not (l.progress and l.progress.execution_status in DELIVERED)]
    fixed = [(l.schedule.planned_date, l.schedule.planned_start_time, l.schedule.planned_end_time) for l in lectures
             if l.is_released and l.schedule and l.schedule.planned_date and l.schedule.planned_date >= start and l.schedule.planned_start_time]
    # ... and so does carry-forward work an open weekly draft has already put on a slot.
    from app.models import SprintRevision, SprintRevisionItem
    for item in db.scalars(select(SprintRevisionItem).join(SprintRevision).where(
            SprintRevision.status == "DRAFT", SprintRevisionItem.teaching_plan_id == plan.id, SprintRevisionItem.change_type == "ADD")):
        v = item.new_values or {}
        if v.get("planned_date") and v.get("planned_start_time") and date.fromisoformat(v["planned_date"]) >= start:
            fixed.append((date.fromisoformat(v["planned_date"]), time.fromisoformat(v["planned_start_time"]),
                          time.fromisoformat(v["planned_end_time"]) if v.get("planned_end_time") else None))
    typed = any(e.class_type == "LAB" for e in entries) and any(e.class_type != "LAB" for e in entries)
    queue: list[tuple[str, Lecture | int]] = [(t, i) for i, t in enumerate(reserve or [])] + [(l.lecture_type, l) for l in pending]
    reserved: dict[int, tuple[date, TimetableEntry]] = {}  # index in `reserve` -> the slot kept free for it
    last: date | None = None
    scheduled = 0
    for d in teaching_days(sp, holidays, start):
        if not queue:
            break
        for e in (e for e in entries if e.weekday == d.weekday()):
            if not queue:
                break
            if any(fd == d and fs < e.end_time and e.start_time < (fe or e.end_time) for fd, fs, fe in fixed):
                continue  # a published class of this subject already sits here
            kind, lec = queue.pop(pick([q[0] for q in queue], e.class_type == "LAB", typed))
            if isinstance(lec, int):
                reserved[lec] = (d, e)
                continue
            sch = lec.schedule or LectureSchedule(lecture_id=lec.id)
            lec.schedule = sch
            sch.planned_date, sch.planned_start_time, sch.planned_end_time, sch.room = d, e.start_time, e.end_time, e.room or plan.room
            lec.professor_id = e.professor_id if e.professor_id and e.professor_id != plan.professor_id else None
            scheduled, last = scheduled + 1, d
    left = [lec for _, lec in queue if not isinstance(lec, int)]
    for lec in left:  # does not fit before the semester ends: undated, reported as at risk
        if lec.schedule:
            lec.schedule.planned_date = lec.schedule.planned_start_time = lec.schedule.planned_end_time = None
    db.flush()
    return {"scheduled": scheduled, "unscheduled": len(left), "last_date": last, "reserved": reserved}


# ------------------------------------------------------------------ views

def _plan(db: Session, plan_id: uuid.UUID) -> SemesterSprintPlan:
    sp = db.get(SemesterSprintPlan, plan_id)
    if not sp:
        raise NotFound("Sprint plan not found.")
    return sp


def _active_plans(sp: SemesterSprintPlan) -> list[TeachingPlan]:
    return [p for p in sp.plans if p.status != PlanStatus.ARCHIVED or sp.status == SprintPlanStatus.ARCHIVED]


def subject_stats(db: Session, sp: SemesterSprintPlan, plan: TeachingPlan, holidays: dict[date, str], tmap: dict) -> dict:
    today = clock.today()
    lectures = _lectures(db, plan.id)
    status = lambda l: l.progress.execution_status if l.progress else ExecutionStatus.SCHEDULED.value  # noqa: E731
    completed = [l for l in lectures if status(l) == ExecutionStatus.COMPLETED]
    partial = [l for l in lectures if status(l) == ExecutionStatus.PARTIALLY_COMPLETED]
    # What still has to be taught: everything not delivered. (Unfinished subtopics come back as carry-forward classes.)
    remaining = [l for l in lectures if status(l) not in DELIVERED]
    undated = [l for l in remaining if not (l.schedule and l.schedule.planned_date)]
    dated = [l.schedule.planned_date for l in lectures if l.schedule and l.schedule.planned_date]
    weekly = plan.classes_per_week + plan.labs_per_week
    left_days = teaching_days(sp, holidays, max(today, sp.start_date))
    weeks_left = len({monday(d) for d in left_days})
    pace = round(len(remaining) / weeks_left, 2) if weeks_left else (float(len(remaining)) if remaining else 0.0)
    generated = sp.status == SprintPlanStatus.ACTIVE
    at_risk = bool(remaining) and (pace > weekly + 1e-9 or (generated and bool(undated)))
    extra = max(0, math.ceil(pace - 1e-9) - weekly) if at_risk else 0
    tpl = tmap.get(plan.semester.number)
    return {
        "plan_id": str(plan.id), "status": plan.status,
        "subject": {"id": str(plan.subject_id), "code": plan.subject.code, "name": plan.subject.name, "short_name": plan.subject.short_name},
        "semester": plan.semester.name, "semester_number": plan.semester.number, "section": plan.section.name,
        "year_group": tpl.name if tpl else None, "template": tpl.code if tpl else None,
        "professor": ser.user_brief(plan.professor), "room": plan.room, "lab_room": plan.lab_room,
        "classes_per_week": plan.classes_per_week, "labs_per_week": plan.labs_per_week, "weekly_sessions": weekly,
        "topics": len(lectures), "subtopics": sum(len(l.subtopics) for l in lectures),
        "completed": len(completed), "partially_completed": len(partial), "remaining": len(remaining),
        "scheduled": len(remaining) - len(undated), "unscheduled": len(undated) if generated else 0,
        "published": sum(1 for l in lectures if l.is_released and l.schedule and l.schedule.planned_date),
        "weeks_left": weeks_left, "required_pace": pace,
        "projected_completion": max(dated).isoformat() if dated and not undated else None,
        "at_risk": at_risk, "extra_sessions_needed": extra,
        "risk_message": (f"At the current pace this subject may not complete before {sp.end_date:%d %b %Y}. "
                         + (f"{extra} additional session{'s' if extra != 1 else ''}/week required." if extra else
                            f"{len(undated)} topic{'s' if len(undated) != 1 else ''} do not fit before the end date.")) if at_risk else None,
        "completion_pct": round(len(completed) * 100 / len(lectures)) if lectures else 0,
    }


def week_rows(db: Session, sp: SemesterSprintPlan) -> list[dict]:
    """Every week of the semester with how many classes it holds and whether it has been published."""
    from app.models import SprintRevision
    today = clock.today()
    ids = [p.id for p in _active_plans(sp)]
    counts: dict[date, list[int]] = defaultdict(lambda: [0, 0, 0])
    if ids:
        rows = db.execute(select(LectureSchedule.planned_date, Lecture.is_released, LectureProgress.execution_status)
                          .join(Lecture, LectureSchedule.lecture_id == Lecture.id)
                          .outerjoin(LectureProgress, LectureProgress.lecture_id == Lecture.id)
                          .where(Lecture.teaching_plan_id.in_(ids), Lecture.is_cancelled.is_(False),
                                 LectureSchedule.planned_date.is_not(None)))
        for d, released, status in rows:
            c = counts[monday(d)]
            c[0] += 1
            c[1] += bool(released)
            c[2] += status in DELIVERED
    drafts = set(db.scalars(select(SprintRevision.week_start).where(SprintRevision.status == "DRAFT")))
    out = []
    first, n = monday(sp.start_date), 0
    while first + timedelta(days=7 * n) <= sp.end_date:
        ws = first + timedelta(days=7 * n)
        n += 1
        total, released, delivered = counts.get(ws, [0, 0, 0])
        state = "EMPTY" if not total else "PUBLISHED" if released == total and ws not in drafts else "DRAFT"
        out.append({"number": n, "start": max(ws, sp.start_date).isoformat(), "end": min(ws + timedelta(days=5), sp.end_date).isoformat(),
                    "week_start": ws.isoformat(), "classes": total, "published": released, "delivered": delivered, "status": state,
                    "has_draft": ws in drafts, "is_current": ws == monday(today), "is_past": ws + timedelta(days=6) < today})
    return out


def brief(db: Session, sp: SemesterSprintPlan) -> dict:
    plans = _active_plans(sp)
    return {
        "id": str(sp.id), "name": sp.name, "status": sp.status,
        "academic_year": {"id": str(sp.academic_year_id), "name": sp.academic_year.name},
        "start_date": sp.start_date.isoformat(), "end_date": sp.end_date.isoformat(), "working_days": sorted(sp.working_days or []),
        "generated_at": ser._iso(sp.generated_at), "archived_at": ser._iso(sp.archived_at),
        "subject_count": len(plans), "in_use": in_use(db, sp),
        "is_current": sp.status == SprintPlanStatus.ACTIVE and sp.start_date <= clock.today() <= sp.end_date,
    }


def detail(db: Session, sp_id: uuid.UUID) -> dict:
    sp = _plan(db, sp_id)
    holidays = _holidays(db, sp.start_date, sp.end_date)
    tmap = tt.template_map(db)
    subjects = [subject_stats(db, sp, p, holidays, tmap) for p in _active_plans(sp)]
    subjects.sort(key=lambda s: (s["semester_number"], s["section"], s["subject"]["code"]))
    done = [s["projected_completion"] for s in subjects]
    remaining = sum(s["remaining"] for s in subjects)
    weeks_left = max((s["weeks_left"] for s in subjects), default=0)
    return brief(db, sp) | {
        "calendar": calendar(db, sp),
        "totals": {
            "topics": sum(s["topics"] for s in subjects), "subtopics": sum(s["subtopics"] for s in subjects),
            "planned_lectures": sum(s["scheduled"] + s["completed"] + s["partially_completed"] for s in subjects),
            "weekly_sessions": sum(s["weekly_sessions"] for s in subjects),
            "required_pace": round(remaining / weeks_left, 1) if weeks_left else 0,
            "remaining": remaining, "weeks_left": weeks_left,
            "completion_pct": round(sum(s["completed"] for s in subjects) * 100 / max(1, sum(s["topics"] for s in subjects))),
            "projected_completion": max(done) if subjects and all(done) else None,
            "at_risk": sum(1 for s in subjects if s["at_risk"]),
        },
        "subjects": subjects,
        "weeks": week_rows(db, sp),
        "ready": {"has_subjects": bool(subjects), "without_curriculum": [s["subject"]["code"] for s in subjects if not s["topics"]],
                  "without_sessions": [s["subject"]["code"] for s in subjects if not s["weekly_sessions"]]},
    }


def list_plans(db: Session, *, include_archived: bool = True) -> list[dict]:
    stmt = select(SemesterSprintPlan).order_by(SemesterSprintPlan.start_date.desc(), SemesterSprintPlan.created_at.desc())
    if not include_archived:
        stmt = stmt.where(SemesterSprintPlan.status != SprintPlanStatus.ARCHIVED.value)
    out = []
    for sp in db.scalars(stmt).unique():
        ids = [p.id for p in _active_plans(sp)]
        topics = db.scalar(select(func.count(Lecture.id)).where(Lecture.teaching_plan_id.in_(ids), Lecture.is_cancelled.is_(False))) if ids else 0
        out.append(brief(db, sp) | {"topics": topics or 0, "total_weeks": calendar(db, sp)["total_weeks"]})
    return out


def current(db: Session) -> SemesterSprintPlan | None:
    """The sprint plan the institution is running now (or the next one to start)."""
    today = clock.today()
    active = list(db.scalars(select(SemesterSprintPlan).where(SemesterSprintPlan.status == SprintPlanStatus.ACTIVE.value)
                             .order_by(SemesterSprintPlan.start_date)).unique())
    return next((s for s in active if s.start_date <= today <= s.end_date), None) or next((s for s in active if s.start_date > today), None) \
        or (active[-1] if active else None)


def overview(db: Session) -> dict:
    """Admin dashboard strip: all numbers straight from the database."""
    from app.services import sprint_service
    sp = current(db)
    if not sp:
        return {"sprint": None}
    d = detail(db, sp.id)
    today = clock.today()
    week = next((w for w in d["weeks"] if w["is_current"]), None)
    return {
        "sprint": {"id": d["id"], "name": d["name"], "start_date": d["start_date"], "end_date": d["end_date"]},
        "current_week": week and {"number": week["number"], "of": len(d["weeks"]), "classes": week["classes"], "delivered": week["delivered"],
                                  "status": week["status"], "week_start": week["week_start"]},
        "completion_pct": d["totals"]["completion_pct"], "topics": d["totals"]["topics"], "remaining": d["totals"]["remaining"],
        "carry_forward": len(sprint_service.carry_forward(db, monday(today) + timedelta(days=7))),
        "at_risk": [{"code": s["subject"]["code"], "name": s["subject"]["name"], "message": s["risk_message"]} for s in d["subjects"] if s["at_risk"]],
    }


# ------------------------------------------------------------------ create / edit

def _check(db: Session, data: rq.SprintPlanIn) -> None:
    if not db.get(AcademicYear, data.academic_year_id):
        raise NotFound("Academic year not found.")
    if data.end_date <= data.start_date:
        raise BusinessRuleViolation("The end date must be after the start date.", code="DATES_ORDERED")
    if (data.end_date - data.start_date).days > 370:
        raise BusinessRuleViolation("A sprint plan covers one semester: choose dates at most a year apart.", code="RANGE_TOO_LONG")


def create(db: Session, admin: User, data: rq.SprintPlanIn) -> dict:
    _check(db, data)
    sp = SemesterSprintPlan(name=data.name, academic_year_id=data.academic_year_id, start_date=data.start_date, end_date=data.end_date,
                            working_days=sorted(set(data.working_days)), created_by_id=admin.id)
    db.add(sp)
    db.flush()
    audit_service.record(db, actor=admin, action="sprint_plan.created", entity_type="sprint_plan", entity_id=sp.id,
                         summary=f"Created sprint plan {sp.name} ({sp.start_date:%d %b %Y} – {sp.end_date:%d %b %Y}).")
    db.commit()
    return detail(db, sp.id)


def update(db: Session, admin: User, sp_id: uuid.UUID, data: rq.SprintPlanIn) -> dict:
    sp = _plan(db, sp_id)
    if sp.status == SprintPlanStatus.ARCHIVED:
        raise Conflict("This sprint plan is archived.", code="SPRINT_PLAN_ARCHIVED")
    _check(db, data)
    before = {"name": sp.name, "start_date": sp.start_date, "end_date": sp.end_date, "working_days": sorted(sp.working_days or [])}
    sp.name, sp.academic_year_id, sp.start_date, sp.end_date = data.name, data.academic_year_id, data.start_date, data.end_date
    sp.working_days = sorted(set(data.working_days))
    after = {"name": sp.name, "start_date": sp.start_date, "end_date": sp.end_date, "working_days": sp.working_days}
    old, new = audit_service.diff(before, after)
    if new:
        audit_service.record(db, actor=admin, action="sprint_plan.updated", entity_type="sprint_plan", entity_id=sp.id,
                             summary=f"Updated sprint plan {sp.name}.", old=old, new=new)
    db.commit()
    return detail(db, sp.id) | {"needs_regeneration": bool(new) and sp.status == SprintPlanStatus.ACTIVE and bool({"start_date", "end_date", "working_days"} & set(new))}


def attach(db: Session, admin: User, sp_id: uuid.UUID, plan_id: uuid.UUID) -> dict:
    """Bring an existing subject plan (with its curriculum) into the sprint plan. Classes that have not happened and
    were not touched become part of the projection again; anything recorded stays as it is."""
    sp = _plan(db, sp_id)
    plan = db.get(TeachingPlan, plan_id)
    if not plan or plan.status == PlanStatus.ARCHIVED:
        raise NotFound("Choose a subject plan that is not archived.")
    if plan.sprint_plan_id and plan.sprint_plan_id != sp.id:
        raise Conflict("This subject already belongs to another sprint plan.", code="ALREADY_IN_SPRINT_PLAN")
    plan.sprint_plan_id = sp.id
    today = clock.today()
    for lec in _lectures(db, plan.id):
        d = lec.schedule.planned_date if lec.schedule else None
        if not lec.progress and not lec.class_session and (d is None or d > today):
            lec.is_released = False
    audit_service.record(db, actor=admin, action="sprint_plan.subject_added", entity_type="sprint_plan", entity_id=sp.id,
                         summary=f"Added {plan.name} to sprint plan {sp.name}.", scope_type="teaching_plan", scope_id=plan.id)
    db.commit()
    return detail(db, sp.id)


# ------------------------------------------------------------------ generate

def generate(db: Session, admin: User, sp_id: uuid.UUID, *, from_date: date | None = None) -> dict:
    """GENERATE SEMESTER SPRINT. Works out which periods each subject meets in every week (from its weekly sessions,
    its year group's timings, and professor / room / section availability), then gives every topic a date in
    curriculum order until the end date. Published weeks and recorded classes are never moved."""
    sp = db.scalar(select(SemesterSprintPlan).where(SemesterSprintPlan.id == sp_id).with_for_update(of=SemesterSprintPlan))
    if not sp:
        raise NotFound("Sprint plan not found.")
    if sp.status == SprintPlanStatus.ARCHIVED:
        raise Conflict("This sprint plan is archived.", code="SPRINT_PLAN_ARCHIVED")
    plans = [p for p in sp.plans if p.status != PlanStatus.ARCHIVED]
    if not plans:
        raise BusinessRuleViolation("Add at least one subject to the sprint plan first.", code="NO_SUBJECTS")
    if not sp.working_days:
        raise BusinessRuleViolation("Choose the working days first.", code="NO_WORKING_DAYS")
    holidays = _holidays(db, sp.start_date, sp.end_date)
    if not teaching_days(sp, holidays):
        raise BusinessRuleViolation("There is no teaching day between the start and end date.", code="NO_TEACHING_DAYS")
    counts = dict(db.execute(select(Lecture.teaching_plan_id, func.count(Lecture.id)).where(
        Lecture.teaching_plan_id.in_([p.id for p in plans]), Lecture.is_cancelled.is_(False)).group_by(Lecture.teaching_plan_id)).all())
    label = lambda p: f"{p.subject.short_name or p.subject.code} {p.semester.name.replace('Semester', 'Sem')}-{p.section.name}"  # noqa: E731
    notes: list[str] = []
    ready = []
    for p in plans:
        if not counts.get(p.id):
            notes.append(f"{label(p)}: no curriculum imported yet, so nothing was scheduled.")
        elif p.classes_per_week + p.labs_per_week == 0:
            notes.append(f"{label(p)}: weekly sessions are 0, so nothing was scheduled.")
        else:
            ready.append(p)
    if not ready:
        raise BusinessRuleViolation("No subject is ready: import the curriculum and set the weekly sessions first. " + " ".join(notes),
                                    code="NOTHING_TO_SCHEDULE")
    now = clock.now_utc()
    for p in ready:
        if p.status != PlanStatus.PUBLISHED:
            p.status, p.published_at, p.published_by_id = PlanStatus.PUBLISHED, now, admin.id
    db.flush()
    placed, unplaced = tt.rebuild_pattern(db, admin, ready, drop=[p.id for p in plans if p not in ready])
    for u in unplaced:
        notes.append(f"{u['label']}: {u['missing']} of its weekly sessions could not be placed. {u['reason']}")
    start = max(from_date or clock.today(), sp.start_date)
    total = left = 0
    for p in sorted(ready, key=lambda p: (p.semester.number, p.subject.code, p.section.name)):
        r = reflow(db, p, start, holidays=holidays)
        total, left = total + r["scheduled"], left + r["unscheduled"]
        if r["unscheduled"]:
            notes.append(f"{label(p)}: {r['unscheduled']} topic(s) do not fit before {sp.end_date:%d %b %Y} at "
                         f"{p.classes_per_week + p.labs_per_week} session(s) a week.")
    sp.status, sp.generated_at = SprintPlanStatus.ACTIVE.value, now
    audit_service.record(db, actor=admin, action="sprint_plan.generated", entity_type="sprint_plan", entity_id=sp.id,
                         summary=f"Generated the semester sprint for {sp.name}: {total} classes scheduled for {len(ready)} subject(s)"
                                 + (f", {left} topic(s) do not fit." if left else "."),
                         new={"scheduled": total, "unscheduled": left, "weekly_slots": placed, "from": start.isoformat()})
    db.commit()
    db.expire_all()
    return detail(db, sp.id) | {"generation": {"scheduled": total, "unscheduled": left, "subjects": len(ready), "notes": notes}}


# ------------------------------------------------------------------ duplicate / archive / delete

def in_use(db: Session, sp: SemesterSprintPlan) -> bool:
    """Has anyone seen or recorded anything? Published weeks, professor records and OM timings all count."""
    ids = [p.id for p in sp.plans]
    if not ids:
        return False
    if db.scalar(select(LectureProgress.id).join(Lecture, LectureProgress.lecture_id == Lecture.id).where(Lecture.teaching_plan_id.in_(ids)).limit(1)):
        return True
    if db.scalar(select(ClassSession.id).join(Lecture, ClassSession.lecture_id == Lecture.id).where(Lecture.teaching_plan_id.in_(ids)).limit(1)):
        return True
    return bool(db.scalar(select(Lecture.id).join(LectureSchedule, LectureSchedule.lecture_id == Lecture.id).where(
        Lecture.teaching_plan_id.in_(ids), Lecture.is_released.is_(True), LectureSchedule.planned_date.is_not(None)).limit(1)))


def archive(db: Session, admin: User, sp_id: uuid.UUID) -> dict:
    sp = _plan(db, sp_id)
    if sp.status == SprintPlanStatus.ARCHIVED:
        return detail(db, sp.id)
    now = clock.now_utc()
    plans = list(sp.plans)
    for p in plans:
        if p.status != PlanStatus.ARCHIVED:
            p.status, p.archived_at = PlanStatus.ARCHIVED, now
    db.flush()
    tt.rebuild_pattern(db, admin, [], drop=[p.id for p in plans])
    sp.status, sp.archived_at = SprintPlanStatus.ARCHIVED.value, now
    audit_service.record(db, actor=admin, action="sprint_plan.archived", entity_type="sprint_plan", entity_id=sp.id,
                         summary=f"Archived sprint plan {sp.name}. Its records are kept; nothing is scheduled from it any more.")
    db.commit()
    db.expire_all()
    return detail(db, sp.id)


def delete(db: Session, admin: User, sp_id: uuid.UUID) -> None:
    sp = _plan(db, sp_id)
    if in_use(db, sp):
        raise Conflict("This sprint plan has published weeks or recorded classes, so it cannot be deleted. Archive it instead: "
                       "the academic records stay intact.", code="SPRINT_PLAN_IN_USE")
    plans = list(sp.plans)
    name = sp.name
    audit_service.record(db, actor=admin, action="sprint_plan.deleted", entity_type="sprint_plan", entity_id=sp.id,
                         summary=f"Deleted unused sprint plan {name} with {len(plans)} subject(s).",
                         old={"subjects": [p.name for p in plans], "start_date": sp.start_date, "end_date": sp.end_date})
    if plans:
        tt.rebuild_pattern(db, admin, [], drop=[p.id for p in plans])
    for p in plans:
        db.delete(p)  # lectures, subtopics and import sessions go with it
    db.flush()
    db.delete(sp)
    db.commit()


def duplicate(db: Session, admin: User, sp_id: uuid.UUID) -> dict:
    """A new draft with the same dates and working days. Subjects and their curriculum are copied when the same
    subject-section is not still running in another plan (two live plans for one class would collide)."""
    from app.services import teaching_plan_service
    src = _plan(db, sp_id)
    sp = SemesterSprintPlan(name=f"{src.name} (copy)"[:200], academic_year_id=src.academic_year_id, start_date=src.start_date,
                            end_date=src.end_date, working_days=list(src.working_days or []), created_by_id=admin.id)
    db.add(sp)
    db.flush()
    copied, skipped = 0, []
    for p in src.plans:
        if teaching_plan_service.find_duplicate(db, subject_id=p.subject_id, section_id=p.section_id, semester_id=p.semester_id):
            skipped.append(p.subject.code)
            continue
        new = TeachingPlan(name=p.name, academic_year_id=p.academic_year_id, semester_id=p.semester_id, department_id=p.department_id,
                           branch_id=p.branch_id, section_id=p.section_id, subject_id=p.subject_id, professor_id=p.professor_id,
                           status=PlanStatus.DRAFT, created_by_id=admin.id, room=p.room, classes_per_week=p.classes_per_week,
                           labs_per_week=p.labs_per_week, lab_room=p.lab_room, sprint_plan_id=sp.id)
        db.add(new)
        db.flush()
        for l in sorted((l for l in p.lectures if l.origin == "MASTER"), key=lambda l: l.sequence):
            lec = Lecture(teaching_plan_id=new.id, sequence=l.sequence, serial_no=l.serial_no, lecture_no=l.lecture_no, lecture_type=l.lecture_type,
                          unit_no=l.unit_no, content_topic=(l.master_snapshot or {}).get("content_topic") or l.content_topic,
                          blooms_taxonomy=l.blooms_taxonomy, is_released=False)
            lec.subtopics = [LectureSubtopic(position=s.position, title=s.title) for s in l.subtopics]
            lec.schedule = LectureSchedule()
            db.add(lec)
        copied += 1
    audit_service.record(db, actor=admin, action="sprint_plan.duplicated", entity_type="sprint_plan", entity_id=sp.id,
                         summary=f"Duplicated sprint plan {src.name}: {copied} subject(s) copied"
                                 + (f", {len(skipped)} still running elsewhere and not copied." if skipped else "."))
    db.commit()
    return detail(db, sp.id) | {"duplicate": {"copied": copied, "skipped": skipped}}
