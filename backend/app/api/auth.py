from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.permissions import permissions_for
from app.core.security import issue_token
from app.db.session import get_db
from app.core.enums import ROLE_LABELS
from app.models import AcademicYear, Semester, User
from app.schemas import requests as rq
from app.services import scope_service, user_service
from app.services import serializers as ser

router = APIRouter(tags=["auth"])


def _session_payload(db: Session, user: User) -> dict:
    year = db.scalar(select(AcademicYear).where(AcademicYear.is_current.is_(True)))
    sem = db.scalar(select(Semester).where(Semester.is_current.is_(True)))
    return {
        "user": ser.user_full(user),
        "role": user.role.code,
        "role_label": ROLE_LABELS[user.role.code],
        "must_change_password": user.must_change_password,
        "scope": scope_service.describe(db, user),
        "timezone": get_settings().institution_timezone,
        "permissions": sorted(p.value for p in permissions_for(user.role_code)),
        "academic_session": {
            "academic_year": ser.academic_year(year) if year else None,
            "semester": ser.semester(sem) if sem else None,
        },
    }


# Development / demo sign-ins created by the seed scripts. Shown on the sign-in page only while DEMO_AUTH_ENABLED
# and only for accounts that really exist with the demo flag; the password is checked by the normal login API.
DEMO_ACCOUNTS = (
    ("ADMIN", "admin", "Admin@123"), ("PROFESSOR", "professor1", "Professor@123"), ("CL_CH", "clch1", "CLCH@123"), ("OM", "om1", "OM@123"),
    ("ADMIN", "admin.demo", "Demo@1234"), ("PROFESSOR", "professor.demo", "Demo@1234"), ("CL_CH", "clch.demo", "Demo@1234"),
    ("OM", "om.demo", "Demo@1234"),
)
DEMO_PASSWORD = "Demo@1234"


@router.get("/auth/config")
def auth_config(db: Session = Depends(get_db)):
    """What the sign-in page may show. Demo shortcuts appear only when enabled AND the seeded demo accounts exist."""
    demo: list[dict] = []
    if get_settings().show_demo_accounts:
        present = set(db.scalars(select(User.username).where(User.is_demo.is_(True), User.is_active.is_(True),
                                                             User.username.in_([u for _, u, _ in DEMO_ACCOUNTS]))))
        for role, username, password in DEMO_ACCOUNTS:
            if username in present and not any(d["role"] == role for d in demo):
                demo.append({"role": role, "username": username, "password": password})
    return {"demo_accounts": demo}


@router.post("/auth/login")
def login(body: rq.LoginRequest, db: Session = Depends(get_db)):
    """Email, username or employee ID + password. The role comes from the account, never from the request."""
    user = user_service.authenticate(db, body.identifier, body.password)
    token, exp = issue_token(user.id, user.password_hash)
    return {"access_token": token, "token_type": "bearer", "expires_at": exp} | _session_payload(db, user)


@router.post("/auth/change-password")
def change_password(body: rq.ChangePassword, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user_service.change_password(db, user, body)
    token, exp = issue_token(user.id, user.password_hash)  # every older token stopped working with the old password
    return {"access_token": token, "token_type": "bearer", "expires_at": exp} | _session_payload(db, user)


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _session_payload(db, user)
