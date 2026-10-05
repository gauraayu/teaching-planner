import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import NotificationChannel, role_sql, sql_in
from app.db.base import Base, JSONB, Timestamps, UTCDateTime, UUIDPk, Uuid, utcnow


class AuditLog(UUIDPk, Base):
    """Append-only. No update/delete endpoints exist for this table."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint(f"actor_role IS NULL OR actor_role IN ({role_sql()})", name="actor_role_valid"),
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_scope", "scope_type", "scope_id", "created_at"),
    )

    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    actor_role: Mapped[str | None] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(48), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    # Scope lets the plan Activity tab pull every event under a plan with one indexed query.
    scope_type: Mapped[str | None] = mapped_column(String(48))
    scope_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    old_values: Mapped[dict | None] = mapped_column(JSONB)
    new_values: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False, index=True)

    actor = relationship("User", lazy="joined")


class Notification(UUIDPk, Timestamps, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(f"channel IN ({sql_in(NotificationChannel)})", name="channel_valid"),
        Index("ix_notifications_user_unread", "user_id", "is_read", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False, default=NotificationChannel.IN_APP)
    kind: Mapped[str] = mapped_column(String(48), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(255))
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
