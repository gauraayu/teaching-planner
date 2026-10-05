import uuid
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import User
from app.schemas import requests as rq
from app.services import sprint_service as svc

router = APIRouter(tags=["sprint-plan"])
ADMIN = require(Permission.PLANS_MANAGE)
PROF = require(Permission.TASKS_READ_OWN)

# ------------------------------------------------------------------ admin: weekly sprint meeting


@router.get("/admin/sprint-plan/week")
def admin_week(week_start: date | None = None, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    """One Monday-Saturday week: the published schedule, the draft overlay if a meeting is in progress, and carry-forward items."""
    return svc.admin_week(db, week_start)


@router.post("/admin/sprint-plan/generate")
def generate_week(body: rq.SprintGenerate, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    """MAKE WEEKLY SPRINT PLAN: map carry-forward work and the next pending topics onto the published timetable's
    slots for the week. The result is a draft - professors see it only after Publish."""
    return svc.generate_week(db, user, body)


@router.post("/admin/sprint-plan/weeks/publish")
def publish_week(body: rq.WeekPublish, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    """Publish a week as it stands (with its draft changes, if any). From then on professors, CL/CH and OM see it."""
    return svc.publish_week(db, user, body.week_start)


@router.post("/admin/sprint-plan/revisions")
def start_meeting(body: rq.SprintMeetingStart, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    """Start Sprint Meeting Update: creates (or reopens) the week's draft. Nothing is visible to professors yet."""
    return svc.start_meeting(db, user, body)


@router.patch("/admin/sprint-plan/revisions/{revision_id}")
def update_meeting(revision_id: uuid.UUID, body: rq.SprintMeetingUpdate, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return svc.update_meeting(db, user, revision_id, body)


@router.delete("/admin/sprint-plan/revisions/{revision_id}")
def discard(revision_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return svc.discard(db, user, revision_id)


@router.patch("/admin/sprint-plan/revisions/{revision_id}/lectures/{lecture_id}")
def edit_lecture(revision_id: uuid.UUID, lecture_id: uuid.UUID, body: rq.SprintLectureEdit, db: Session = Depends(get_db),
                 user: User = Depends(ADMIN)):
    return svc.edit_lecture(db, user, revision_id, lecture_id, body)


@router.post("/admin/sprint-plan/revisions/{revision_id}/lectures/{lecture_id}/cancel")
def cancel_lecture(revision_id: uuid.UUID, lecture_id: uuid.UUID, body: rq.SprintCancel, db: Session = Depends(get_db),
                   user: User = Depends(ADMIN)):
    return svc.cancel_lecture(db, user, revision_id, lecture_id, body)


@router.post("/admin/sprint-plan/revisions/{revision_id}/lectures")
def add_lecture(revision_id: uuid.UUID, body: rq.SprintLectureAdd, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    """Add a replacement lecture, or place a carry-forward item (carry_forward_lecture_id) into the week."""
    return svc.add_lecture(db, user, revision_id, body)


@router.delete("/admin/sprint-plan/revisions/{revision_id}/items/{item_id}")
def remove_item(revision_id: uuid.UUID, item_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return svc.remove_item(db, user, revision_id, item_id)


@router.get("/admin/sprint-plan/revisions/{revision_id}/changes")
def changes(revision_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return svc.changes(db, revision_id)


@router.post("/admin/sprint-plan/revisions/{revision_id}/publish")
def publish(revision_id: uuid.UUID, body: rq.SprintPublish, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return svc.publish(db, user, revision_id, body)


@router.get("/admin/sprint-plan/history")
def history(db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    items = svc.history(db)
    return {"items": items, "total": len(items)}


@router.post("/admin/sprint-plan/carry-forward/{lecture_id}")
def decide_carry_forward(lecture_id: uuid.UUID, body: rq.CarryForwardDecision, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return svc.decide_carry_forward(db, user, lecture_id, body)


# ------------------------------------------------------------------ professor: published schedule only


@router.get("/professor/sprint-plan")
def professor_week(week_start: date | None = None, db: Session = Depends(get_db), user: User = Depends(PROF)):
    return svc.professor_week(db, user, week_start)


@router.get("/professor/sprint-plan/history")
def professor_history(db: Session = Depends(get_db), user: User = Depends(PROF)):
    items = svc.professor_history(db, user)
    return {"items": items, "total": len(items)}


@router.get("/professor/sprint-plan/{revision_id}/changes")
def professor_changes(revision_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(PROF)):
    return svc.professor_changes(db, user, revision_id)


# ------------------------------------------------------------------ the same published plan for CL/CH, OM and Admin (read-only)


@router.get("/sprint-plan/sheet")
def sheet(week_start: date | None = None, professor_id: uuid.UUID | None = None, subject_id: uuid.UUID | None = None,
          db: Session = Depends(get_db), user: User = Depends(require(Permission.VERIFICATION_READ))):
    """One week as a single sheet. Rows are limited to the signed-in user's scope; nothing is taken from a role parameter."""
    return svc.sheet_week(db, user, week_start, professor_id=professor_id, subject_id=subject_id)
