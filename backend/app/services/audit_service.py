"""Append-only audit trail. Called inside the same transaction as the change it records."""
import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import AuditLog, User


def _jsonable(value):
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    return value


def record(db: Session, *, actor: User | None, action: str, entity_type: str, entity_id: uuid.UUID | None,
           summary: str, old: dict | None = None, new: dict | None = None,
           scope_type: str | None = None, scope_id: uuid.UUID | None = None) -> AuditLog:
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        actor_role=actor.role_code.value if actor else None,
        action=action, entity_type=entity_type, entity_id=entity_id, summary=summary,
        old_values=_jsonable(old) if old else None, new_values=_jsonable(new) if new else None,
        scope_type=scope_type, scope_id=scope_id,
    )
    db.add(entry)
    return entry


def diff(old: dict, new: dict) -> tuple[dict, dict]:
    """Keep only the keys whose value changed."""
    changed = {k for k in set(old) | set(new) if old.get(k) != new.get(k)}
    return {k: old.get(k) for k in changed}, {k: new.get(k) for k in changed}
