"""Progress metrics and reports.

Metric definitions (shown verbatim in the UI so nobody has to guess):
  Completed            execution status COMPLETED
  Partial              execution status PARTIALLY_COMPLETED
  Delayed              not completed/partial and the ORIGINAL planned date is before today
  Pending              everything else (scheduled today or later, or not yet scheduled)
  Execution completion Completed / Total planned lectures
  Verified completion  Final-verified (CL/CH and OM) lectures / Total planned lectures
  On-time completion   Completed on or before the planned date / Completed
These four buckets (Completed, Partial, Delayed, Pending) always add up to Total.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, time

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.enums import ExecutionStatus, PlanStatus, SubmissionStatus
from app.models import Lecture, LectureProgress, LectureSchedule, Section, Semester, Subject, TeachingPlan, User

METRIC_DEFINITIONS = {
    "completed": "Lectures whose execution status is Completed.",
    "partial": "Lectures marked Partially Completed.",
    "delayed": "Not completed or partial, and the original planned date has passed.",
    "pending": "Scheduled for today or later, or not yet scheduled.",
    "execution_pct": "Completed ÷ total planned lectures.",
    "verified_pct": "Lectures final-verified by CL/CH and OM ÷ total planned lectures.",
    "on_time_pct": "Lectures completed on or before their planned date ÷ completed lectures.",
}


@dataclass
class Fact:
    lecture_id: uuid.UUID
    plan_id: uuid.UUID
    plan_name: str
    subject_id: uuid.UUID
    subject_code: str
    subject_name: str
    subject_short: str | None
    section: str
    semester: str
    professor_id: uuid.UUID
    professor_name: str
    unit_no: int | None
    lecture_no: int
    topic: str
    planned_date: date | None
    planned_start: object
    execution_status: str
    submission_status: str | None
    actual_date: date | None
    progress_id: uuid.UUID | None

    @property
    def bucket(self) -> str:
        if self.execution_status == ExecutionStatus.COMPLETED:
            return "completed"
        if self.execution_status == ExecutionStatus.PARTIALLY_COMPLETED:
            return "partial"
        if self.planned_date and self.planned_date < clock.today():
            return "delayed"
        return "pending"

    @property
    def verified(self) -> bool:
        return self.submission_status == SubmissionStatus.FINAL_VERIFIED

    @property
    def on_time(self) -> bool:
        return self.bucket == "completed" and bool(self.actual_date and self.planned_date and self.actual_date <= self.planned_date)

    @property
    def delay_days(self) -> int | None:
        if self.actual_date and self.planned_date:
            return (self.actual_date - self.planned_date).days
        if self.bucket == "delayed":
            return (clock.today() - self.planned_date).days
        return None


def facts(db: Session, *, academic_year_id=None, semester_id=None, branch_id=None, section_id=None, subject_id=None,
          professor_id=None, plan_id=None, unit_no=None, date_from=None, date_to=None,
          statuses: tuple[str, ...] = (PlanStatus.PUBLISHED,), viewer=None) -> list[Fact]:
    """`viewer` (a CL/CH or OM account) limits the facts to that account's scope; None = no scope filter."""
    stmt = (
        select(
            Lecture.id, TeachingPlan.id, TeachingPlan.name, Subject.id, Subject.code, Subject.name, Subject.short_name,
            Section.name, Semester.name, User.id, User.full_name, Lecture.unit_no, Lecture.lecture_no, Lecture.content_topic,
            # a class in a week that is not published yet has no date as far as progress is concerned (never "delayed")
            case((Lecture.is_released, LectureSchedule.planned_date), else_=None), LectureSchedule.planned_start_time,
            LectureProgress.execution_status, LectureProgress.submission_status, LectureProgress.actual_completion_date,
            LectureProgress.id,
        )
        .join(TeachingPlan, Lecture.teaching_plan_id == TeachingPlan.id)
        .join(Subject, TeachingPlan.subject_id == Subject.id)
        .join(Section, TeachingPlan.section_id == Section.id)
        .join(Semester, TeachingPlan.semester_id == Semester.id)
        # effective professor: a sprint revision can assign one lecture to a substitute
        .join(User, User.id == func.coalesce(Lecture.professor_id, TeachingPlan.professor_id))
        .outerjoin(LectureSchedule, LectureSchedule.lecture_id == Lecture.id)
        .outerjoin(LectureProgress, LectureProgress.lecture_id == Lecture.id)
        .where(TeachingPlan.status.in_(statuses), Lecture.is_cancelled.is_(False))
        .order_by(Subject.code, Lecture.sequence)
    )
    for col, val in ((TeachingPlan.academic_year_id, academic_year_id), (TeachingPlan.semester_id, semester_id),
                     (TeachingPlan.branch_id, branch_id), (TeachingPlan.section_id, section_id),
                     (TeachingPlan.subject_id, subject_id),
                     (func.coalesce(Lecture.professor_id, TeachingPlan.professor_id), professor_id),
                     (TeachingPlan.id, plan_id), (Lecture.unit_no, unit_no)):
        if val is not None:
            stmt = stmt.where(col == val)
    if date_from:
        stmt = stmt.where(LectureSchedule.planned_date >= date_from)
    if date_to:
        stmt = stmt.where(LectureSchedule.planned_date <= date_to)
    if viewer is not None:
        from app.services import scope_service
        stmt = stmt.where(*scope_service.plan_filter(viewer))
    out = []
    for row in db.execute(stmt):
        r = list(row)
        r[16] = r[16] or ExecutionStatus.SCHEDULED.value
        out.append(Fact(*r))
    return out


def _pct(n: int, d: int) -> int:
    return round(n * 100 / d) if d else 0


def summarize(items: list[Fact]) -> dict:
    total = len(items)
    buckets = defaultdict(int)
    for f in items:
        buckets[f.bucket] += 1
    verified = sum(1 for f in items if f.verified)
    on_time = sum(1 for f in items if f.on_time)
    awaiting = sum(1 for f in items if f.submission_status in (SubmissionStatus.SUBMITTED, SubmissionStatus.RESUBMITTED))
    corrections = sum(1 for f in items if f.submission_status == SubmissionStatus.CORRECTION_REQUIRED)
    return {
        "total": total, "completed": buckets["completed"], "partial": buckets["partial"],
        "delayed": buckets["delayed"], "pending": buckets["pending"], "verified": verified,
        "awaiting_verification": awaiting, "correction_required": corrections,
        "execution_pct": _pct(buckets["completed"], total),
        "verified_pct": _pct(verified, total),
        "on_time_pct": _pct(on_time, buckets["completed"]),
    }


def _group(items: list[Fact], key) -> dict:
    groups: dict = defaultdict(list)
    for f in items:
        groups[key(f)].append(f)
    return groups


def subject_progress(items: list[Fact]) -> list[dict]:
    rows = []
    for plan_id, group in _group(items, lambda f: f.plan_id).items():
        f0 = group[0]
        rows.append({
            "plan_id": str(plan_id), "plan_name": f0.plan_name, "subject_code": f0.subject_code, "subject_name": f0.subject_name,
            "subject_short": f0.subject_short, "section": f0.section, "semester": f0.semester,
            "professor": {"id": str(f0.professor_id), "full_name": f0.professor_name},
            **summarize(group),
        })
    return sorted(rows, key=lambda r: (r["subject_code"], r["section"]))


def faculty_progress(items: list[Fact]) -> list[dict]:
    rows = []
    for prof_id, group in _group(items, lambda f: f.professor_id).items():
        rows.append({
            "professor": {"id": str(prof_id), "full_name": group[0].professor_name},
            "subjects": sorted({f"{f.subject_code} · {f.section}" for f in group}),
            **summarize(group),
        })
    return sorted(rows, key=lambda r: r["professor"]["full_name"])


def unit_progress(items: list[Fact]) -> list[dict]:
    rows = []
    for unit, group in sorted(_group(items, lambda f: f.unit_no).items(), key=lambda kv: (kv[0] is None, kv[0] or 0)):
        rows.append({"unit_no": unit, "first_topic": group[0].topic, **summarize(group)})
    return rows


def fact_row(f: Fact) -> dict:
    return {
        "lecture_id": str(f.lecture_id), "plan_id": str(f.plan_id), "subject_code": f.subject_code, "subject_name": f.subject_name,
        "subject_short": f.subject_short, "section": f.section, "professor": f.professor_name, "unit_no": f.unit_no,
        "lecture_no": f.lecture_no, "topic": f.topic,
        "planned_date": f.planned_date.isoformat() if f.planned_date else None,
        "planned_start_time": f.planned_start.strftime("%H:%M") if f.planned_start else None,
        "actual_date": f.actual_date.isoformat() if f.actual_date else None,
        "execution_status": f.execution_status, "submission_status": f.submission_status,
        "bucket": f.bucket, "delay_days": f.delay_days, "on_time": f.on_time,
    }


def lecture_list(items: list[Fact], kind: str) -> list[dict]:
    today = clock.today()
    if kind == "delayed":
        chosen = sorted((f for f in items if f.bucket == "delayed"), key=lambda f: f.planned_date)
    elif kind == "pending":
        chosen = sorted((f for f in items if f.bucket == "pending"), key=lambda f: (f.planned_date is None, f.planned_date or today))
    elif kind == "planned_vs_actual":
        chosen = sorted((f for f in items if f.actual_date), key=lambda f: f.actual_date, reverse=True)
    elif kind == "upcoming":
        chosen = sorted((f for f in items if f.planned_date and f.planned_date >= today and f.bucket == "pending"),
                        key=lambda f: (f.planned_date, f.planned_start or time.min))
    elif kind == "completion":
        chosen = items
    else:
        chosen = []
    return [fact_row(f) for f in chosen]


def schedule_adherence(items: list[Fact]) -> dict:
    completed = [f for f in items if f.actual_date and f.planned_date]
    early = sum(1 for f in completed if f.actual_date < f.planned_date)
    same = sum(1 for f in completed if f.actual_date == f.planned_date)
    late = [f for f in completed if f.actual_date > f.planned_date]
    return {
        "delivered": len(completed), "early": early, "on_day": same, "late": len(late),
        "average_delay_days": round(sum((f.actual_date - f.planned_date).days for f in late) / len(late), 1) if late else 0,
        "adherence_pct": _pct(early + same, len(completed)),
    }
