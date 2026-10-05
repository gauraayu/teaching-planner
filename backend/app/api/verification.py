import uuid
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import User
from app.schemas import requests as rq
from app.services import verification_service as svc

router = APIRouter(prefix="/verifications", tags=["verification"])
READER = require(Permission.VERIFICATION_READ)
VERIFIER = require(Permission.VERIFY_CL_CH, Permission.VERIFY_OM, any_of=True)


@router.get("/metrics")
def metrics(db: Session = Depends(get_db), user: User = Depends(READER)):
    return svc.metrics(db, user)


@router.get("/queue/{view}")
def queue(view: str, professor_id: uuid.UUID | None = None, subject_id: uuid.UUID | None = None,
          section_id: uuid.UUID | None = None, semester_id: uuid.UUID | None = None,
          date_from: date | None = None, date_to: date | None = None, q: str | None = None,
          db: Session = Depends(get_db), user: User = Depends(READER)):
    """view: pending | verified | corrections | all. Each level sees only its own steps (OM after CL/CH has verified) and only inside its scope."""
    items = svc.queue(db, user, view=view, professor_id=professor_id, subject_id=subject_id, section_id=section_id,
                      semester_id=semester_id, date_from=date_from, date_to=date_to, q=q)
    return {"items": items, "total": len(items)}


@router.get("/pending")
def pending(db: Session = Depends(get_db), user: User = Depends(READER)):
    items = svc.queue(db, user, view="pending")
    return {"items": items, "total": len(items)}


@router.get("/{verification_id}")
def detail(verification_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(READER)):
    return svc.detail(db, user, verification_id)


@router.post("/{verification_id}/verify")
def verify(verification_id: uuid.UUID, body: rq.VerifyRequest, db: Session = Depends(get_db), user: User = Depends(VERIFIER)):
    return svc.verify(db, user, verification_id, body)


@router.post("/{verification_id}/request-correction")
def request_correction(verification_id: uuid.UUID, body: rq.CorrectionRequest, db: Session = Depends(get_db),
                       user: User = Depends(VERIFIER)):
    return svc.request_correction(db, user, verification_id, body)
