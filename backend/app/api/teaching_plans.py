import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require
from app.core.errors import NotFound
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import Lecture, TeachingPlan, User
from app.schemas import requests as rq
from app.services import professor_service, scope_service
from app.services import serializers as ser
from app.services import teaching_plan_service as svc

router = APIRouter(tags=["teaching-plans"])


@router.get("/teaching-plans")
def list_plans(status: str | None = None, semester_id: uuid.UUID | None = None, academic_year_id: uuid.UUID | None = None,
               branch_id: uuid.UUID | None = None, section_id: uuid.UUID | None = None, subject_id: uuid.UUID | None = None,
               professor_id: uuid.UUID | None = None, q: str | None = None, db: Session = Depends(get_db),
               user: User = Depends(require(Permission.PLANS_READ_ALL))):
    """Administrators see every plan; CL/CH and OM accounts the plans inside their scope."""
    items = svc.list_plans(db, status=status, semester_id=semester_id, academic_year_id=academic_year_id, branch_id=branch_id,
                           section_id=section_id, subject_id=subject_id, professor_id=professor_id, q=q)
    visible = {str(p.id) for p in db.scalars(select(TeachingPlan).where(TeachingPlan.id.in_([uuid.UUID(i["id"]) for i in items])))
               if scope_service.covers(user, p)} if items else set()
    items = [i for i in items if i["id"] in visible]
    return {"items": items, "total": len(items)}


def _plan_for(db: Session, user: User, plan_id: uuid.UUID):
    plan = svc.get_plan(db, plan_id)
    scope_service.require(user, plan, "This plan")
    return plan


@router.post("/teaching-plans", status_code=201)
def create_plan(body: rq.TeachingPlanCreate, db: Session = Depends(get_db), user: User = Depends(require(Permission.PLANS_MANAGE))):
    return ser.plan_brief(svc.create_plan(db, user, body))


@router.get("/teaching-plans/check-duplicate", dependencies=[Depends(require(Permission.PLANS_MANAGE))])
def check_duplicate(subject_id: uuid.UUID, section_id: uuid.UUID, semester_id: uuid.UUID, db: Session = Depends(get_db)):
    dup = svc.find_duplicate(db, subject_id=subject_id, section_id=section_id, semester_id=semester_id)
    return {"duplicate": ser.plan_brief(dup) if dup else None}


@router.get("/teaching-plans/{plan_id}")
def get_plan(plan_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require(Permission.PLANS_READ_ALL))):
    return svc.plan_detail(db, _plan_for(db, user, plan_id))


@router.get("/teaching-plans/{plan_id}/lectures")
def plan_lectures(plan_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require(Permission.PLANS_READ_ALL))):
    _plan_for(db, user, plan_id)
    items = [ser.lecture(l) for l in svc.plan_lectures(db, plan_id)]
    return {"items": items, "total": len(items)}


@router.get("/teaching-plans/{plan_id}/activity")
def plan_activity(plan_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require(Permission.PLANS_READ_ALL))):
    _plan_for(db, user, plan_id)
    items = [ser.audit_entry(a) for a in svc.activity(db, plan_id)]
    return {"items": items, "total": len(items)}


@router.post("/teaching-plans/{plan_id}/status")
def change_plan_status(plan_id: uuid.UUID, body: rq.PlanStatusChange, db: Session = Depends(get_db),
                       user: User = Depends(require(Permission.PLANS_PUBLISH))):
    return ser.plan_brief(svc.change_status(db, user, svc.get_plan(db, plan_id), body))


@router.get("/lectures/{lecture_id}")
def get_lecture(lecture_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Professors see only their own lectures; Admin reads any; CL/CH and OM only inside their scope (enforced in the service)."""
    return professor_service.lecture_detail(db, user, lecture_id)


@router.patch("/lectures/{lecture_id}")
def correct_lecture(lecture_id: uuid.UUID, body: rq.LectureCorrection, db: Session = Depends(get_db),
                    user: User = Depends(require(Permission.PLANS_MANAGE))):
    """Master-data correction. Admin only - professors receive 403 here."""
    lecture = db.get(Lecture, lecture_id)
    if not lecture:
        raise NotFound("Lecture not found.")
    return ser.lecture(svc.correct_lecture(db, user, lecture, body))


@router.patch("/teaching-plans/{plan_id}/allocation")
def set_allocation(plan_id: uuid.UUID, body: rq.PlanAllocation, db: Session = Depends(get_db),
                   user: User = Depends(require(Permission.PLANS_MANAGE))):
    """Subject allocation: classes and labs per week and room preference. Used by Generate Schedule."""
    return ser.plan_brief(svc.set_allocation(db, user, plan_id, body))
