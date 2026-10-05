import uuid
from datetime import date, datetime, time

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import DelayReason, TimingStatus, sql_in
from app.db.base import Base, Timestamps, UTCDateTime, UUIDPk, Uuid


class ClassSession(UUIDPk, Timestamps, Base):
    """What actually happened at the classroom door, recorded by the Operations Manager.

    Third kind of execution data next to the professor's `lecture_progress`:
    the professor says WHAT was taught, the OM records WHEN the class really ran.
    One row per lecture, created when the entry time is first recorded. The
    scheduled slot is copied in so a later schedule correction never rewrites history.
    """

    __tablename__ = "class_sessions"
    __table_args__ = (
        CheckConstraint(f"timing_status IN ({sql_in(TimingStatus)})", name="timing_status_valid"),
        CheckConstraint(f"delay_reason IS NULL OR delay_reason IN ({sql_in(DelayReason)})", name="delay_reason_valid"),
        CheckConstraint("exit_at IS NULL OR exit_at > entry_at", name="exit_after_entry"),
        CheckConstraint("entry_delay_minutes >= 0", name="delay_not_negative"),
        # A delayed entry always carries a reason; "Other" always carries remarks.
        CheckConstraint("timing_status <> 'DELAYED' OR delay_reason IS NOT NULL", name="delayed_needs_reason"),
        CheckConstraint("(delay_reason IS NULL OR delay_reason <> 'OTHER') OR length(trim(coalesce(delay_remarks, ''))) > 0",
                        name="other_reason_needs_remarks"),
        Index("ix_class_sessions_date_status", "session_date", "timing_status"),
    )

    lecture_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("lectures.id", ondelete="CASCADE"), nullable=False, unique=True)
    professor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)

    session_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    scheduled_start: Mapped[time] = mapped_column(Time, nullable=False)
    scheduled_end: Mapped[time | None] = mapped_column(Time)
    room: Mapped[str | None] = mapped_column(String(40))

    entry_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    exit_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    entry_delay_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    timing_status: Mapped[str] = mapped_column(String(16), nullable=False, default=TimingStatus.ON_TIME)
    delay_reason: Mapped[str | None] = mapped_column(String(32))
    delay_remarks: Mapped[str | None] = mapped_column(Text)
    early_exit_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    early_exit_reason: Mapped[str | None] = mapped_column(Text)

    entry_recorded_by_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    exit_recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))

    lecture = relationship("Lecture", back_populates="class_session", lazy="joined")
    professor = relationship("User", foreign_keys=[professor_id], lazy="joined")