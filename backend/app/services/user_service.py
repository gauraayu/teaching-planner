"""Accounts: sign-in, and the administrator's user management.

The administrator creates every Professor, CL/CH and OM account. A new account gets a
temporary password and is asked to change it at first sign-in. Accounts are deactivated,
never deleted, so lectures, verifications and audit entries keep pointing at a real person.
"""
from __future__ import annotations

import time
import uuid
from collections import defaultdict

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.enums import MANAGED_ROLES, ROLE_LABELS, PlanStatus, Role, ScopeMode
from app.core.errors import AppError, BusinessRuleViolation, Conflict, NotAuthenticated, NotFound
from app.core.security import burn_password_check, hash_password, verify_password
from app.models import (
    ClassSession, Department, Lecture, LectureProgress, LectureSchedule, RoleModel, Subject, TeachingPlan, User, UserScope,
    Verification,
)
from app.schemas import requests as rq
from app.services import audit_service, scope_service
from app.services import serializers as ser

# ------------------------------------------------------------------ sign-in

MAX_FAILURES, LOCK_SECONDS = 8, 300
_failures: dict[str, list[float]] = defaultdict(list)  # per process; enough to slow guessing on a single-instance deployment


def _throttle(key: str) -> None:
    now = time.monotonic()
    recent = [t for t in _failures[key] if now - t < LOCK_SECONDS]
    _failures[key] = recent
    if len(recent) >= MAX_FAILURES:
        raise AppError("Too many failed sign-in attempts. Try again in a few minutes.", code="TOO_MANY_ATTEMPTS", status_code=429)


def find_by_identifier(db: Session, identifier: str) -> User | None:
    ident = identifier.strip().lower()
    if not ident:
        return None
    return db.scalar(select(User).where(or_(func.lower(User.email) == ident, func.lower(User.username) == ident,
                                            func.lower(User.employee_code) == ident)))


def authenticate(db: Session, identifier: str, password: str) -> User:
    user = find_by_identifier(db, identifier)
    # One counter per account, whichever identifier (email, username, employee ID) is typed.
    key = f"user:{user.id}" if user else f"unknown:{identifier.strip().lower()[:120]}"
    _throttle(key)
    ok = verify_password(password, user.password_hash) if user else (burn_password_check(password) or False)
    if not ok:
        _failures[key].append(time.monotonic())
        raise NotAuthenticated("Incorrect username or password.", code="INVALID_CREDENTIALS")
    if not user.is_active:
        raise NotAuthenticated("This account is inactive. Contact the administrator.", code="ACCOUNT_INACTIVE")
    _failures.pop(key, None)
    user.last_login_at = clock.now_utc()
    audit_service.record(db, actor=user, action="auth.login", entity_type="user", entity_id=user.id,
                         summary=f"{user.full_name} signed in ({ROLE_LABELS[user.role.code]}).")
    db.commit()
    return user


def change_password(db: Session, user: User, data: rq.ChangePassword) -> None:
    if not verify_password(data.current_password, user.password_hash):
        raise BusinessRuleViolation("The current password is not correct.", code="WRONG_PASSWORD")
    if data.new_password == data.current_password:
        raise BusinessRuleViolation("Choose a password different from the current one.", code="SAME_PASSWORD")
    user.password_hash, user.must_change_password = hash_password(data.new_password), False
    audit_service.record(db, actor=user, action="auth.password_changed", entity_type="user", entity_id=user.id,
                         summary=f"{user.full_name} changed their password.")
    db.commit()


# ------------------------------------------------------------------ serialisation

def _workload(db: Session, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    """Per professor: live plans, distinct subjects and upcoming lectures (their own or as substitute)."""
    if not user_ids:
        return {}
    prof = func.coalesce(Lecture.professor_id, TeachingPlan.professor_id)
    rows = db.execute(
        select(prof, func.count(func.distinct(TeachingPlan.subject_id)), func.count(func.distinct(TeachingPlan.id)),
               func.count(Lecture.id).filter(LectureSchedule.planned_date >= clock.today(), Lecture.is_cancelled.is_(False),
                                             TeachingPlan.status == PlanStatus.PUBLISHED))
        .select_from(Lecture).join(TeachingPlan, Lecture.teaching_plan_id == TeachingPlan.id)
        .outerjoin(LectureSchedule, LectureSchedule.lecture_id == Lecture.id)
        .where(TeachingPlan.status != PlanStatus.ARCHIVED, prof.in_(user_ids)).group_by(prof)).all()
    out = {pid: {"subjects": s, "plans": p, "upcoming_lectures": u} for pid, s, p, u in rows}
    # A plan with no lectures yet still counts as an allocation.
    for pid, subjects, plans in db.execute(
            select(TeachingPlan.professor_id, func.count(func.distinct(TeachingPlan.subject_id)), func.count(TeachingPlan.id))
            .where(TeachingPlan.status != PlanStatus.ARCHIVED, TeachingPlan.professor_id.in_(user_ids))
            .group_by(TeachingPlan.professor_id)):
        cur = out.setdefault(pid, {"subjects": 0, "plans": 0, "upcoming_lectures": 0})
        cur["subjects"], cur["plans"] = max(cur["subjects"], subjects), max(cur["plans"], plans)
    return out


def user_admin(db: Session, u: User, *, workload: dict | None = None, subject_names: dict[str, str] | None = None) -> dict:
    role = u.role_code
    scope = scope_service.describe(db, u, subject_names=subject_names)
    w = (workload or {}).get(u.id)
    if role == Role.PROFESSOR:
        n = w["subjects"] if w else 0
        scope_label = f"{n} subject{'s' if n != 1 else ''}" if n else "No classes allocated"
    else:
        scope_label = scope["label"]
    return {
        "id": str(u.id), "full_name": u.full_name, "employee_id": u.employee_code, "email": u.email, "username": u.username,
        "role": role.value, "role_label": ROLE_LABELS[role.value], "designation": u.designation, "phone": u.phone,
        "department": ser.department(u.department) if u.department else None,
        "is_active": u.is_active, "status": "ACTIVE" if u.is_active else "INACTIVE",
        "last_login_at": ser._iso(u.last_login_at), "must_change_password": u.must_change_password,
        "can_sign_in": bool(u.password_hash), "created_at": ser._iso(u.created_at),
        "scope": scope, "scope_label": scope_label,
        "workload": w or ({"subjects": 0, "plans": 0, "upcoming_lectures": 0} if role == Role.PROFESSOR else None),
    }


def _subject_names(db: Session) -> dict[str, str]:
    return {str(i): c for i, c in db.execute(select(Subject.id, Subject.code))}


def list_users(db: Session, *, role: Role | None = None, status: str | None = None, q: str | None = None,
               department_id: uuid.UUID | None = None, subject_id: uuid.UUID | None = None) -> list[dict]:
    stmt = select(User).join(RoleModel).order_by(User.full_name)
    if role:
        stmt = stmt.where(RoleModel.code == role.value)
    if status in ("ACTIVE", "INACTIVE"):
        stmt = stmt.where(User.is_active.is_(status == "ACTIVE"))
    if department_id:
        stmt = stmt.where(User.department_id == department_id)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(User.full_name).like(like), func.lower(User.email).like(like),
                              func.lower(func.coalesce(User.employee_code, "")).like(like),
                              func.lower(func.coalesce(User.username, "")).like(like)))
    users = list(db.scalars(stmt).unique())
    if subject_id:  # professors eligible to teach this subject
        users = [u for u in users if scope_service.eligible_professor(u, subject_id)]
    workload = _workload(db, [u.id for u in users if u.role_code == Role.PROFESSOR])
    names = _subject_names(db)
    return [user_admin(db, u, workload=workload, subject_names=names) for u in users]


def get_user(db: Session, user_id: uuid.UUID) -> User:
    u = db.get(User, user_id)
    if not u:
        raise NotFound("User not found.")
    return u


def detail(db: Session, user_id: uuid.UUID) -> dict:
    u = get_user(db, user_id)
    return user_admin(db, u, workload=_workload(db, [u.id])) | {"has_history": has_history(db, u)}


# ------------------------------------------------------------------ create / update

def _role_row(db: Session, role: Role) -> RoleModel:
    row = db.scalar(select(RoleModel).where(RoleModel.code == role.value))
    if not row:
        row = RoleModel(code=role.value, name=ROLE_LABELS[role.value])
        db.add(row)
        db.flush()
    return row


def _check_unique(db: Session, *, email: str | None, employee_id: str | None, username: str | None, exclude: uuid.UUID | None) -> None:
    def taken(col, value) -> bool:
        stmt = select(User.id).where(func.lower(col) == value.lower())
        if exclude:
            stmt = stmt.where(User.id != exclude)
        return db.scalar(stmt) is not None

    problems = {}
    if email and taken(User.email, email):
        problems["email"] = "Another account already uses this email."
    if employee_id and taken(User.employee_code, employee_id):
        problems["employee_id"] = "Another account already uses this employee ID."
    if username and taken(User.username, username):
        problems["username"] = "This username is already taken."
    # A username must not collide with someone else's email or employee ID either, or sign-in becomes ambiguous.
    if username and "username" not in problems and (taken(User.email, username) or taken(User.employee_code, username)):
        problems["username"] = "This username is already used as another account's email or employee ID."
    if employee_id and "employee_id" not in problems and (taken(User.email, employee_id) or taken(User.username, employee_id)):
        problems["employee_id"] = "This employee ID is already used as another account's email or username."
    if problems:
        raise Conflict(" ".join(problems.values()), code="DUPLICATE_USER", details={"fields": problems})


def _apply_scope(db: Session, user: User, role: Role, data: rq.ScopeIn | None) -> None:
    if data is None:
        return
    if role == Role.ADMIN:
        user.scope = None
        return
    if data.department_id and not db.get(Department, data.department_id):
        raise NotFound("Department not found.")
    subject_ids = [str(s) for s in data.subject_ids]
    if subject_ids:
        known = {str(i) for i in db.scalars(select(Subject.id).where(Subject.id.in_(data.subject_ids)))}
        if set(subject_ids) - known:
            raise NotFound("One of the selected subjects no longer exists.")
    if role == Role.PROFESSOR:  # only the eligibility list is meaningful for a professor
        mode, dept, sems, secs = ScopeMode.ALL, None, [], []
    else:
        mode, dept, sems, secs = data.mode, data.department_id, data.semester_numbers, data.section_names
        if mode == ScopeMode.SELECTED and not (dept or sems or secs or subject_ids):
            raise BusinessRuleViolation("Choose at least a department, semester, section or subject for a selected scope, "
                                        "or switch the scope to All.", code="SCOPE_EMPTY")
        if mode == ScopeMode.ALL:
            dept, sems, secs, subject_ids = None, [], [], []
    sc = user.scope or UserScope()
    sc.mode, sc.department_id, sc.semester_numbers, sc.section_names, sc.subject_ids = mode.value, dept, sems, secs, subject_ids
    user.scope = sc


def _scope_snapshot(db: Session, user: User) -> dict:
    d = scope_service.describe(db, user)
    return {"scope": d["label"], "scope_mode": d["mode"]}


def create_user(db: Session, admin: User, data: rq.UserCreate) -> dict:
    # Any role can be created here, administrators included: only an administrator reaches this function.
    if data.department_id and not db.get(Department, data.department_id):
        raise NotFound("Department not found.")
    _check_unique(db, email=data.email, employee_id=data.employee_id, username=data.username, exclude=None)
    user = User(full_name=data.full_name, email=data.email.lower(), employee_code=data.employee_id, username=data.username,
                role_id=_role_row(db, data.role).id, department_id=data.department_id, designation=data.designation or None,
                phone=data.phone or None, is_active=data.is_active, is_demo=False,
                password_hash=hash_password(data.password), must_change_password=True)
    db.add(user)
    db.flush()
    db.refresh(user)
    _apply_scope(db, user, data.role, data.scope or rq.ScopeIn())
    db.flush()
    audit_service.record(db, actor=admin, action="user.created", entity_type="user", entity_id=user.id,
                         summary=f"Created {ROLE_LABELS[data.role.value]} account for {user.full_name} ({user.employee_code}).",
                         new={"full_name": user.full_name, "email": user.email, "employee_id": user.employee_code,
                              "role": data.role.value, "is_active": user.is_active} | _scope_snapshot(db, user))
    db.commit()
    return detail(db, user.id)


def has_history(db: Session, user: User) -> bool:
    """True once the account is referenced by teaching, verification or operations records."""
    checks = (
        select(TeachingPlan.id).where(TeachingPlan.professor_id == user.id),
        select(Lecture.id).where(Lecture.professor_id == user.id),
        select(LectureProgress.id).where(LectureProgress.professor_id == user.id),
        select(Verification.id).where(Verification.verifier_id == user.id),
        select(ClassSession.id).where(or_(ClassSession.entry_recorded_by_id == user.id, ClassSession.exit_recorded_by_id == user.id)),
    )
    return any(db.scalar(stmt.limit(1)) is not None for stmt in checks)


def _active_admins(db: Session) -> int:
    return db.scalar(select(func.count(User.id)).join(RoleModel).where(RoleModel.code == Role.ADMIN.value, User.is_active.is_(True))) or 0


def update_user(db: Session, admin: User, user_id: uuid.UUID, data: rq.UserUpdate) -> dict:
    user = get_user(db, user_id)
    fields = data.model_dump(exclude_unset=True)
    current_role = user.role_code
    before = {"full_name": user.full_name, "email": user.email, "employee_id": user.employee_code, "username": user.username,
              "role": current_role.value, "department": user.department.code if user.department else None,
              "designation": user.designation, "phone": user.phone, "is_active": user.is_active} | _scope_snapshot(db, user)

    _check_unique(db, email=fields.get("email"), employee_id=fields.get("employee_id"), username=fields.get("username"), exclude=user.id)

    new_role = fields.get("role") or current_role
    if new_role != current_role:
        if current_role == Role.ADMIN or new_role == Role.ADMIN:
            raise BusinessRuleViolation("An administrator account cannot be converted to or from another role.", code="ROLE_CHANGE_BLOCKED")
        if has_history(db, user):
            raise Conflict(
                f"{user.full_name} already has {ROLE_LABELS[current_role.value]} records (lectures, verifications or class timings). "
                "Changing the role would break that history. Deactivate this account and create a new one for the new role.",
                code="ROLE_CHANGE_BLOCKED")
        user.role_id = _role_row(db, new_role).id
        user.scope = None
        db.flush()
        db.refresh(user)

    if "is_active" in fields and fields["is_active"] is False and user.is_active:
        if user.id == admin.id:
            raise BusinessRuleViolation("You cannot deactivate your own account.", code="SELF_DEACTIVATE")
        if current_role == Role.ADMIN and _active_admins(db) <= 1:
            raise BusinessRuleViolation("At least one administrator account must stay active.", code="LAST_ADMIN")

    if "department_id" in fields and fields["department_id"] and not db.get(Department, fields["department_id"]):
        raise NotFound("Department not found.")
    for key, attr in (("full_name", "full_name"), ("employee_id", "employee_code"), ("username", "username"),
                      ("department_id", "department_id"), ("designation", "designation"), ("phone", "phone"), ("is_active", "is_active")):
        if key in fields:
            value = fields[key]
            if key in ("full_name", "employee_id", "is_active") and value is None:
                continue
            setattr(user, attr, value or None if isinstance(value, str) else value)
    if fields.get("email"):
        user.email = fields["email"].lower()
    if data.scope is not None or new_role != current_role:
        _apply_scope(db, user, new_role, data.scope or rq.ScopeIn())
    db.flush()
    db.refresh(user)

    after = {"full_name": user.full_name, "email": user.email, "employee_id": user.employee_code, "username": user.username,
             "role": user.role_code.value, "department": user.department.code if user.department else None,
             "designation": user.designation, "phone": user.phone, "is_active": user.is_active} | _scope_snapshot(db, user)
    old, new = audit_service.diff(before, after)
    if new:
        if set(new) == {"is_active"}:
            action = "user.activated" if user.is_active else "user.deactivated"
            summary = f"{'Activated' if user.is_active else 'Deactivated'} {user.full_name}'s account."
        else:
            action = "user.updated"
            summary = f"Updated {user.full_name}'s account ({', '.join(sorted(k.replace('_', ' ') for k in new))})."
        audit_service.record(db, actor=admin, action=action, entity_type="user", entity_id=user.id, summary=summary, old=old, new=new)
    db.commit()
    return detail(db, user.id)


def reset_password(db: Session, admin: User, user_id: uuid.UUID, data: rq.PasswordReset) -> dict:
    user = get_user(db, user_id)
    user.password_hash, user.must_change_password = hash_password(data.password), user.id != admin.id
    audit_service.record(db, actor=admin, action="user.password_reset", entity_type="user", entity_id=user.id,
                         summary=f"Set a new temporary password for {user.full_name}.")  # the password itself is never logged
    db.commit()
    return detail(db, user.id)
