import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require
from app.core import clock
from app.core.enums import DelayReason, TimingStatus
from app.core.errors import AppError
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import User
from app.schemas import requests as rq
from app.services import operations_service as svc

router = APIRouter(prefix="/om", tags=["operations"])
READER = require(Permission.OPERATIONS_READ)
RECORDER = require(Permission.OPERATIONS_RECORD)


def _range(date_from: date | None, date_to: date | None, default_days: int) -> tuple[date, date]:
    end = date_to or clock.today()
    start = date_from or end - timedelta(days=default_days)
    if start > end:
        raise AppError("The start date must be on or before the end date.")
    if (end - start).days > 185:
        raise AppError("Choose a range of 6 months or less.")
    return start, end


@router.get("/dashboard")
def dashboard(on: date | None = None, db: Session = Depends(get_db), user: User = Depends(READER)):
    """Classes of one day (default today) with live state, timings and the CL/CH → OM chain."""
    return svc.dashboard(db, on, viewer=user)


@router.get("/classes")
def classes(date_from: date | None = None, date_to: date | None = None, professor_id: uuid.UUID | None = None,
            db: Session = Depends(get_db), user: User = Depends(READER)):
    start = date_from or clock.today()
    end = date_to or start
    if (end - start).days > 45:
        raise AppError("Choose a range of 45 days or less.")
    items = svc.classes(db, start, end, professor_id=professor_id, viewer=user)
    return {"items": items, "total": len(items), "date_from": start.isoformat(), "date_to": end.isoformat()}


@router.get("/delay-reasons")
def delay_reasons(user: User = Depends(READER)):
    return {"items": [{"value": r.value, "label": svc.DELAY_REASON_LABELS[r]} for r in DelayReason],
            "tolerance_minutes": svc.tolerance()}


@router.get("/classes/{lecture_id}")
def class_detail(lecture_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(READER)):
    return svc.class_detail(db, lecture_id, viewer=user)


@router.post("/classes/{lecture_id}/entry")
def record_entry(lecture_id: uuid.UUID, body: rq.EntryRecord, db: Session = Depends(get_db), user: User = Depends(RECORDER)):
    """422 DELAY_REASON_REQUIRED (with delay_minutes) when the entry is past the tolerance and no reason was sent."""
    return svc.record_entry(db, user, lecture_id, body)


@router.post("/classes/{lecture_id}/exit")
def record_exit(lecture_id: uuid.UUID, body: rq.ExitRecord, db: Session = Depends(get_db), user: User = Depends(RECORDER)):
    return svc.record_exit(db, user, lecture_id, body)


@router.get("/records")
def records(date_from: date | None = None, date_to: date | None = None, professor_id: uuid.UUID | None = None,
            subject_id: uuid.UUID | None = None, timing: TimingStatus | None = None, q: str | None = None,
            db: Session = Depends(get_db), user: User = Depends(READER)):
    start, end = _range(date_from, date_to, 30)
    items = svc.records(db, start, end, professor_id=professor_id, subject_id=subject_id,
                        timing=timing.value if timing else None, q=q, viewer=user)
    return {"items": items, "total": len(items), "date_from": start.isoformat(), "date_to": end.isoformat()}


@router.get("/faculty")
def faculty(date_from: date | None = None, date_to: date | None = None, db: Session = Depends(get_db), user: User = Depends(READER)):
    start, end = _range(date_from, date_to, 30)
    items = svc.faculty_records(db, start, end, viewer=user)
    return {"items": items, "total": len(items), "date_from": start.isoformat(), "date_to": end.isoformat()}


@router.get("/reports/summary")
def report(date_from: date | None = None, date_to: date | None = None, db: Session = Depends(get_db), user: User = Depends(READER)):
    start, end = _range(date_from, date_to, 30)
    return svc.report(db, start, end, viewer=user)
