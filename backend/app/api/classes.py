import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import current_user, require
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import User
from app.schemas import requests as rq
from app.services import class_service as svc

router = APIRouter(tags=["class"])
OWN = require(Permission.PROGRESS_UPDATE_OWN)


@router.post("/lectures/{lecture_id}/start")
def start_class(lecture_id: uuid.UUID, body: rq.StartClass, db: Session = Depends(get_db), user: User = Depends(OWN)):
    """Professor's Start Class. Server time is recorded; this is not the OM's official entry time."""
    return svc.start_class(db, user, lecture_id, body.checkin)


@router.post("/lectures/{lecture_id}/end")
def end_class(lecture_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(OWN)):
    return svc.end_class(db, user, lecture_id)


@router.post("/lectures/{lecture_id}/evidence")
async def upload_evidence(lecture_id: uuid.UUID, file: UploadFile = File(...), caption: str | None = Form(default=None),
                          kind: str = Form(default="CLASS_EVIDENCE"), db: Session = Depends(get_db), user: User = Depends(OWN)):
    """Optional class photo. JPG / PNG / WebP only, checked from the file's bytes; stored outside the database."""
    limit = get_settings().evidence_max_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise AppError(f"Images must be smaller than {get_settings().evidence_max_mb} MB.", code="FILE_TOO_LARGE")
    return svc.add_evidence(db, user, lecture_id, data=data, original_name=file.filename, caption=caption, kind=kind)


@router.delete("/lecture-evidence/{material_id}")
def remove_evidence(material_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(OWN)):
    return svc.remove_evidence(db, user, material_id)


@router.get("/schedule/today")
def today(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Today's classes for the signed-in professor or OM, with the server's current time. Other roles get an empty list."""
    return svc.today_schedule(db, user)


@router.post("/schedule/alerts/{lecture_id}")
def record_alert(lecture_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return svc.record_alert(db, user, lecture_id)
