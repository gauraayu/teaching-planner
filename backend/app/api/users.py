"""Admin user management. Every route needs users.manage - the role is read from the database."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require
from app.core.enums import MANAGED_ROLES, ROLE_LABELS, Role
from app.core.errors import AppError
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import User
from app.schemas import requests as rq
from app.services import user_service as svc

router = APIRouter(prefix="/admin/users", tags=["users"])
MANAGE = require(Permission.USERS_MANAGE)


@router.get("")
def list_users(role: Role | None = None, status: str | None = None, q: str | None = None,
               department_id: uuid.UUID | None = None, subject_id: uuid.UUID | None = None,
               db: Session = Depends(get_db), user: User = Depends(MANAGE)):
    """`?role=PROFESSOR&status=ACTIVE` is what every professor dropdown loads. `subject_id` keeps only eligible professors."""
    if status and status not in ("ACTIVE", "INACTIVE"):
        raise AppError("status must be ACTIVE or INACTIVE.")
    items = svc.list_users(db, role=role, status=status, q=q, department_id=department_id, subject_id=subject_id)
    return {"items": items, "total": len(items),
            "roles": [{"value": r.value, "label": ROLE_LABELS[r.value]} for r in MANAGED_ROLES]}


@router.post("", status_code=201)
def create_user(body: rq.UserCreate, db: Session = Depends(get_db), user: User = Depends(MANAGE)):
    return svc.create_user(db, user, body)


@router.get("/{user_id}")
def get_user(user_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(MANAGE)):
    return svc.detail(db, user_id)


@router.patch("/{user_id}")
def update_user(user_id: uuid.UUID, body: rq.UserUpdate, db: Session = Depends(get_db), user: User = Depends(MANAGE)):
    """Also used to activate / deactivate (`is_active`) and to change the verification or operations scope."""
    return svc.update_user(db, user, user_id, body)


@router.post("/{user_id}/password")
def reset_password(user_id: uuid.UUID, body: rq.PasswordReset, db: Session = Depends(get_db), user: User = Depends(MANAGE)):
    return svc.reset_password(db, user, user_id, body)
