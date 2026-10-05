"""In-app notifications.

`notify` writes an IN_APP row today. Future channels (email, push, WhatsApp)
plug in as dispatchers keyed by NotificationChannel without touching callers.
"""
import uuid
from collections.abc import Callable, Iterable

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.clock import now_utc
from app.core.enums import NotificationChannel, Role
from app.models import Notification, RoleModel, User

# Registry for future out-of-band delivery. Empty in V1 by design.
DISPATCHERS: dict[NotificationChannel, Callable[[Notification], None]] = {}


def notify(db: Session, user_id: uuid.UUID, *, kind: str, title: str, body: str | None = None, link: str | None = None) -> Notification:
    n = Notification(user_id=user_id, channel=NotificationChannel.IN_APP, kind=kind, title=title, body=body, link=link)
    db.add(n)
    return n


def notify_role(db: Session, role: Role, **kwargs) -> None:
    for uid in db.scalars(select(User.id).join(RoleModel).where(RoleModel.code == role.value, User.is_active.is_(True))):
        notify(db, uid, **kwargs)


def notify_many(db: Session, user_ids: Iterable[uuid.UUID], **kwargs) -> None:
    for uid in set(user_ids):
        notify(db, uid, **kwargs)


def list_for_user(db: Session, user_id: uuid.UUID, limit: int = 30) -> tuple[list[Notification], int]:
    items = list(db.scalars(
        select(Notification).where(Notification.user_id == user_id).order_by(Notification.created_at.desc()).limit(limit)
    ))
    unread = db.scalar(select(func.count()).select_from(Notification)
                       .where(Notification.user_id == user_id, Notification.is_read.is_(False)))
    return items, unread or 0


def mark_read(db: Session, user_id: uuid.UUID, notification_id: uuid.UUID | None = None) -> None:
    stmt = update(Notification).where(Notification.user_id == user_id, Notification.is_read.is_(False))
    if notification_id:
        stmt = stmt.where(Notification.id == notification_id)
    db.execute(stmt.values(is_read=True, read_at=now_utc()))
    db.commit()
