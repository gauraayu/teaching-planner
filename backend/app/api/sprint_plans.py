import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import User
from app.schemas import requests as rq
from app.services import sprint_plan_service as svc

router = APIRouter(tags=["semester-sprint-plan"])
ADMIN = require(Permission.PLANS_MANAGE)


@router.get("/sprint-plans")
def list_sprint_plans(db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    items = svc.list_plans(db)
    return {"items": items, "total": len(items)}


@router.get("/admin/sprint-overview")
def overview(db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    """Dashboard strip: active sprint, current week, completion, carry-forward and at-risk subjects."""
    return svc.overview(db)


@router.post("/sprint-plans", status_code=201)
def create(body: rq.SprintPlanIn, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return svc.create(db, user, body)


@router.get("/sprint-plans/{sp_id}")
def get(sp_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    """Dates, calendar arithmetic, subjects with pace / at-risk, and every week of the semester."""
    return svc.detail(db, sp_id)


@router.put("/sprint-plans/{sp_id}")
def update(sp_id: uuid.UUID, body: rq.SprintPlanIn, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return svc.update(db, user, sp_id, body)


@router.post("/sprint-plans/{sp_id}/subjects")
def attach(sp_id: uuid.UUID, body: rq.SprintPlanSubject, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return svc.attach(db, user, sp_id, body.teaching_plan_id)


@router.post("/sprint-plans/{sp_id}/generate")
def generate(sp_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    """GENERATE SEMESTER SPRINT: every topic gets a date, time and room between today and the end date."""
    return svc.generate(db, user, sp_id)


@router.post("/sprint-plans/{sp_id}/duplicate", status_code=201)
def duplicate(sp_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return svc.duplicate(db, user, sp_id)


@router.post("/sprint-plans/{sp_id}/archive")
def archive(sp_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return svc.archive(db, user, sp_id)


@router.delete("/sprint-plans/{sp_id}", status_code=204)
def delete(sp_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    """Only an unused draft can be deleted. 409 SPRINT_PLAN_IN_USE otherwise - archive it instead."""
    svc.delete(db, user, sp_id)
