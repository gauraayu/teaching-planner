"""Who may see which teaching plans.

One rule, used by every list and every action:

    ADMIN       everything (monitoring only - verification endpoints still refuse to act)
    PROFESSOR   never comes through here; professor queries filter on the lecture's professor
    CL/CH, OM   the plans matched by their `user_scopes` row (no row, or mode ALL = everything)

`plan_filter` gives SQL conditions on TeachingPlan for lists; `covers` answers the same
question for one plan already in memory. Both are derived from the signed-in user, never
from a request parameter.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Role, ScopeMode
from app.core.errors import NotFound
from app.models import Section, Semester, Subject, TeachingPlan, User, UserScope

SCOPED_ROLES = (Role.CL_CH, Role.OM)
ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]


def _selected(user: User) -> UserScope | None:
    """The user's scope if it actually restricts anything, else None."""
    if user.role_code not in SCOPED_ROLES:
        return None
    sc = user.scope
    if not sc or sc.mode != ScopeMode.SELECTED:
        return None
    return sc


def plan_filter(user: User) -> list:
    sc = _selected(user)
    if not sc:
        return []
    conds = []
    if sc.department_id:
        conds.append(TeachingPlan.department_id == sc.department_id)
    if sc.semester_numbers:
        conds.append(TeachingPlan.semester_id.in_(select(Semester.id).where(Semester.number.in_(sc.semester_numbers))))
    if sc.section_names:
        conds.append(TeachingPlan.section_id.in_(select(Section.id).where(Section.name.in_(sc.section_names))))
    if sc.subject_ids:
        conds.append(TeachingPlan.subject_id.in_([uuid.UUID(s) for s in sc.subject_ids]))
    return conds


def covers(user: User, plan: TeachingPlan) -> bool:
    sc = _selected(user)
    if not sc:
        return True
    if sc.department_id and plan.department_id != sc.department_id:
        return False
    if sc.semester_numbers and plan.semester.number not in sc.semester_numbers:
        return False
    if sc.section_names and plan.section.name not in sc.section_names:
        return False
    if sc.subject_ids and str(plan.subject_id) not in sc.subject_ids:
        return False
    return True


def require(user: User, plan: TeachingPlan, what: str = "This record") -> None:
    """404 rather than 403: a record outside the user's scope does not exist as far as they are concerned."""
    if not covers(user, plan):
        raise NotFound(f"{what} is outside your assigned scope.")


def users_covering(db: Session, role: Role, plan: TeachingPlan) -> list[uuid.UUID]:
    """Active users of a role whose scope includes this plan - the people a notification should reach."""
    from app.models import RoleModel
    users = db.scalars(select(User).join(RoleModel).where(RoleModel.code == role.value, User.is_active.is_(True))).unique()
    return [u.id for u in users if covers(u, plan)]


# ------------------------------------------------------------------ display

def describe(db: Session, user: User, *, subject_names: dict[str, str] | None = None) -> dict:
    """The scope as stored plus a one-line label for tables ("CSE · Sem V · A, B")."""
    sc = user.scope
    role = user.role_code
    data = {
        "mode": (sc.mode if sc else ScopeMode.ALL.value),
        "department_id": str(sc.department_id) if sc and sc.department_id else None,
        "semester_numbers": list(sc.semester_numbers) if sc else [],
        "section_names": list(sc.section_names) if sc else [],
        "subject_ids": list(sc.subject_ids) if sc else [],
    }
    if role == Role.ADMIN:
        return data | {"label": "Whole institution"}
    if role == Role.PROFESSOR:
        n = len(data["subject_ids"])
        return data | {"label": f"{n} subject{'s' if n != 1 else ''}" if n else "Any subject"}
    if data["mode"] == ScopeMode.ALL.value:
        return data | {"label": "All professors" if role == Role.CL_CH else "All classes"}
    parts = []
    if sc.department:
        parts.append(sc.department.code)
    if data["semester_numbers"]:
        parts.append("Sem " + ", ".join(ROMAN[n] if 0 < n < len(ROMAN) else str(n) for n in sorted(data["semester_numbers"])))
    if data["section_names"]:
        parts.append("Sec " + ", ".join(sorted(data["section_names"])))
    if data["subject_ids"]:
        names = subject_names if subject_names is not None else dict(
            (str(i), c) for i, c in db.execute(select(Subject.id, Subject.code).where(
                Subject.id.in_([uuid.UUID(s) for s in data["subject_ids"]]))))
        codes = [names[s] for s in data["subject_ids"] if s in names]
        parts.append(", ".join(codes) if len(codes) <= 2 else f"{len(codes)} subjects")
    return data | {"label": " · ".join(parts) if parts else ("All professors" if role == Role.CL_CH else "All classes")}


def eligible_professor(user: User, subject_id: uuid.UUID) -> bool:
    """A professor with an eligibility list may only be allocated those subjects; no list = any subject."""
    sc = user.scope
    return not sc or not sc.subject_ids or str(subject_id) in sc.subject_ids


__all__ = ["plan_filter", "covers", "require", "users_covering", "describe", "eligible_professor"]
