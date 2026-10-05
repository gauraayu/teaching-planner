import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require
from app.core import clock
from app.core.errors import AppError
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import User
from app.schemas import requests as rq
from app.services import professor_service as svc

router = APIRouter(tags=["professor"])
PROF = require(Permission.TASKS_READ_OWN)


@router.get("/professor/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(PROF)):
    return svc.dashboard(db, user)


@router.get("/professor/tasks/{category}")
def tasks(category: str, days: int = 14, db: Session = Depends(get_db), user: User = Depends(PROF)):
    """category: today | upcoming | overdue | completed | corrections - derived from schedule + progress."""
    items = svc.tasks(db, user, category, days=days)
    return {"items": items, "total": len(items)}


@router.get("/professor/courses")
def courses(db: Session = Depends(get_db), user: User = Depends(PROF)):
    return {"items": svc.dashboard(db, user)["courses"]}


@router.get("/professor/courses/{plan_id}")
def course(plan_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(PROF)):
    return svc.course_view(db, user, plan_id)


@router.get("/professor/schedule")
def schedule(date_from: date | None = None, date_to: date | None = None, db: Session = Depends(get_db), user: User = Depends(PROF)):
    start = date_from or clock.today() - timedelta(days=clock.today().weekday())
    end = date_to or start + timedelta(days=41)
    if (end - start).days > 120:
        raise AppError("Choose a range of 120 days or less.")
    items = svc.schedule(db, user, start, end)
    return {"items": items, "total": len(items), "date_from": start.isoformat(), "date_to": end.isoformat()}


@router.put("/lectures/{lecture_id}/progress")
def save_progress(lecture_id: uuid.UUID, body: rq.ProgressUpdate, db: Session = Depends(get_db),
                  user: User = Depends(require(Permission.PROGRESS_UPDATE_OWN))):
    """Save Draft. Creates the execution record on first save; master-plan fields are not accepted."""
    return svc.save_progress(db, user, lecture_id, body)


@router.post("/lecture-progress/{progress_id}/submit")
def submit(progress_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require(Permission.PROGRESS_SUBMIT_OWN))):
    return svc.submit(db, user, progress_id)
