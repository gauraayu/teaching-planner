import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import User
from app.schemas import requests as rq
from app.services import serializers as ser
from app.services import timetable_service as svc

router = APIRouter(tags=["timetable"])
READER = require(Permission.ACADEMIC_READ)
ADMIN = require(Permission.PLANS_MANAGE)


def _room(r) -> dict:
    return {"id": str(r.id), "name": r.name, "room_type": r.room_type, "capacity": r.capacity, "is_active": r.is_active}


def _holiday(h) -> dict:
    return {"id": str(h.id), "date": h.date.isoformat(), "name": h.name}


# ------------------------------------------------------------------ timing templates (each year group's own day and lunch)

@router.get("/timing-templates")
def timing_templates(db: Session = Depends(get_db), user: User = Depends(READER)):
    items = [svc.template_view(t) for t in svc.templates(db, active_only=False)]
    return {"items": items, "total": len(items)}


@router.put("/timing-templates/{template_id}")
def save_template(template_id: uuid.UUID, body: rq.TimingTemplateIn, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return svc.save_template(db, user, template_id, body)


# ------------------------------------------------------------------ rooms & holidays

@router.get("/rooms")
def rooms(db: Session = Depends(get_db), user: User = Depends(READER)):
    items = [_room(r) for r in svc.list_rooms(db)]
    return {"items": items, "total": len(items)}


@router.post("/rooms", status_code=201)
def create_room(body: rq.RoomIn, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return _room(svc.save_room(db, user, body))


@router.put("/rooms/{room_id}")
def update_room(room_id: uuid.UUID, body: rq.RoomIn, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return _room(svc.save_room(db, user, body, room_id))


@router.get("/holidays")
def holidays(db: Session = Depends(get_db), user: User = Depends(READER)):
    items = [_holiday(h) for h in svc.list_holidays(db)]
    return {"items": items, "total": len(items)}


@router.post("/holidays", status_code=201)
def create_holiday(body: rq.HolidayIn, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return _holiday(svc.save_holiday(db, user, body))


@router.put("/holidays/{holiday_id}")
def update_holiday(holiday_id: uuid.UUID, body: rq.HolidayIn, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return _holiday(svc.save_holiday(db, user, body, holiday_id))


@router.delete("/holidays/{holiday_id}", status_code=204)
def delete_holiday(holiday_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    svc.delete_holiday(db, user, holiday_id)


# ------------------------------------------------------------------ the master timetable

@router.get("/timetable")
def timetable(draft: bool = False, db: Session = Depends(get_db), user: User = Depends(READER)):
    """The institution's recurring weekly timetable, limited to what the signed-in account may see:
    Admin everything, a professor their own classes, CL/CH and OM the classes in their scope."""
    return svc.view(db, user, draft=draft)


@router.get("/timetable/history")
def history(db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    items = svc.history(db)
    return {"items": items, "total": len(items)}


@router.post("/timetable/draft")
def start_draft(db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    """Edit Schedule: a working copy of the published timetable."""
    return svc.start_draft(db, user)


@router.delete("/timetable/draft")
def discard_draft(db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return svc.discard_draft(db, user)


@router.post("/timetable/generate")
def generate(body: rq.TimetableGenerate, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    """Generate Schedule: deterministic placement from the subject allocations. The result is always a draft."""
    return svc.generate(db, user, body)


@router.post("/timetable/entries")
def add_entry(body: rq.TimetableEntryIn, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return svc.save_entry(db, user, body)


@router.put("/timetable/entries/{entry_id}")
def update_entry(entry_id: uuid.UUID, body: rq.TimetableEntryIn, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return svc.save_entry(db, user, body, entry_id)


@router.delete("/timetable/entries/{entry_id}")
def delete_entry(entry_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return svc.delete_entry(db, user, entry_id)


@router.post("/timetable/publish")
def publish(body: rq.TimetablePublish, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    """409 SCHEDULE_CONFLICT while any professor, section, room or own-lunch conflict remains."""
    return svc.publish(db, user, body)
