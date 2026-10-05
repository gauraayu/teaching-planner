import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import CarryForwardStatus, ChangeReason, ChangeType, RevisionStatus, SprintPlanStatus, sql_in
from app.db.base import Base, JSONB, Timestamps, UTCDateTime, UUIDPk, Uuid


class SprintRevision(UUIDPk, Timestamps, Base):
    """One weekly sprint meeting outcome.

    MASTER PLAN + published revisions = effective schedule. A revision is a DRAFT while
    the meeting is in progress (invisible to professors, changes nothing), and becomes
    v2, v3... for its week when published. v1 is always the semester master plan itself.
    Published revisions are never edited or deleted.
    """

    __tablename__ = "sprint_revisions"
    __table_args__ = (
        CheckConstraint(f"status IN ({sql_in(RevisionStatus)})", name="status_valid"),
        CheckConstraint("week_end > week_start", name="week_ordered"),
        # Only one meeting can be in progress for a week.
        Index("uq_sprint_revisions_one_draft", "week_start", unique=True, postgresql_where=text("status = 'DRAFT'"), sqlite_where=text("status = 'DRAFT'")),
        Index("ix_sprint_revisions_week_status", "week_start", "status"),
    )

    week_start: Mapped[date] = mapped_column(Date, nullable=False)  # Monday
    week_end: Mapped[date] = mapped_column(Date, nullable=False)    # Sunday
    revision_number: Mapped[int | None] = mapped_column(Integer)    # assigned at publish (2, 3, ...)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=RevisionStatus.DRAFT)
    meeting_date: Mapped[date | None] = mapped_column(Date)
    meeting_notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    published_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    created_by = relationship("User", foreign_keys=[created_by_id], lazy="joined")
    published_by = relationship("User", foreign_keys=[published_by_id], lazy="joined")
    items: Mapped[list["SprintRevisionItem"]] = relationship(back_populates="revision", cascade="all, delete-orphan",
                                                             order_by="SprintRevisionItem.created_at")


class SprintRevisionItem(UUIDPk, Timestamps, Base):
    """One changed lecture inside a revision, stored as a before/after diff."""

    __tablename__ = "sprint_revision_items"
    __table_args__ = (
        CheckConstraint(f"change_type IN ({sql_in(ChangeType)})", name="change_type_valid"),
        CheckConstraint(f"reason IN ({sql_in(ChangeReason)})", name="reason_valid"),
        CheckConstraint("reason <> 'OTHER' OR length(trim(coalesce(remarks, ''))) > 0", name="other_needs_remarks"),
        CheckConstraint("change_type = 'ADD' OR lecture_id IS NOT NULL", name="change_needs_lecture"),
        UniqueConstraint("revision_id", "lecture_id"),
    )

    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("sprint_revisions.id", ondelete="CASCADE"), nullable=False, index=True)
    # For ADD items this is filled when the revision is published and the lecture is created.
    lecture_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("lectures.id", ondelete="CASCADE"), index=True)
    teaching_plan_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("teaching_plans.id", ondelete="CASCADE"), nullable=False)
    change_type: Mapped[str] = mapped_column(String(8), nullable=False)
    old_values: Mapped[dict | None] = mapped_column(JSONB)  # only the fields that changed
    new_values: Mapped[dict | None] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text)
    carry_forward_lecture_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("lectures.id", ondelete="SET NULL"))

    revision: Mapped[SprintRevision] = relationship(back_populates="items")
    lecture = relationship("Lecture", foreign_keys=[lecture_id], lazy="joined")
    teaching_plan = relationship("TeachingPlan", lazy="joined")


class CarryForwardItem(UUIDPk, Timestamps, Base):
    """The admin's decision about remaining work from an earlier lecture.

    Candidates themselves are derived from execution data (partial / not conducted);
    a row exists only once the admin has decided something.
    """

    __tablename__ = "carry_forward_items"
    __table_args__ = (CheckConstraint(f"status IN ({sql_in(CarryForwardStatus)})", name="status_valid"),)

    source_lecture_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("lectures.id", ondelete="CASCADE"), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    target_lecture_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("lectures.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(Text)
    decided_by_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class SemesterSprintPlan(UUIDPk, Timestamps, Base):
    """The one plan an admin sets up at the start of a semester: its dates, working days and subjects.

    Subjects are teaching plans (subject + section + professor + weekly sessions + curriculum) that point here.
    Generating the semester sprint spreads every topic over the dates; each week is then published on its own,
    and only published weeks reach professors. There is no separate timetable to maintain.
    """

    __tablename__ = "semester_sprint_plans"
    __table_args__ = (
        CheckConstraint(f"status IN ({sql_in(SprintPlanStatus)})", name="status_valid"),
        CheckConstraint("end_date > start_date", name="dates_ordered"),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    academic_year_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("academic_years.id", ondelete="RESTRICT"), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    working_days: Mapped[list] = mapped_column(JSONB, nullable=False, default=lambda: [0, 1, 2, 3, 4, 5], server_default="[0, 1, 2, 3, 4, 5]")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=SprintPlanStatus.DRAFT, server_default=SprintPlanStatus.DRAFT.value)
    generated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_by_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    academic_year = relationship("AcademicYear", lazy="joined")
    plans = relationship("TeachingPlan", back_populates="sprint_plan", order_by="TeachingPlan.created_at")
