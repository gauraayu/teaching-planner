import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, SmallInteger, String, Text, Time, UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ClassType, RoomType, SlotType, TimetableStatus, sql_in
from app.db.base import Base, JSONB, Timestamps, UTCDateTime, UUIDPk, Uuid


class TimingTemplate(UUIDPk, Timestamps, Base):
    """A day structure for one year group: its lecture periods and ITS OWN lunch.

    The institution runs two of them (First Year, Second-Fourth Year). They overlap in clock time
    but number their lectures differently, so a lecture number only means something inside a template.
    `semester_numbers` is the configurable mapping "which semesters follow this template".
    """

    __tablename__ = "timing_templates"

    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    short_name: Mapped[str] = mapped_column(String(24), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    semester_numbers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    display_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    slots: Mapped[list["TimingSlot"]] = relationship(back_populates="template", order_by="TimingSlot.display_order",
                                                     cascade="all, delete-orphan", lazy="selectin")


class TimingSlot(UUIDPk, Timestamps, Base):
    __tablename__ = "timing_slots"
    __table_args__ = (
        CheckConstraint(f"slot_type IN ({sql_in(SlotType)})", name="slot_type_valid"),
        CheckConstraint("end_time > start_time", name="times_ordered"),
        UniqueConstraint("timing_template_id", "display_order"),
    )

    timing_template_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("timing_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    slot_type: Mapped[str] = mapped_column(String(12), nullable=False, default=SlotType.LECTURE)
    lecture_number: Mapped[int | None] = mapped_column(SmallInteger)  # NULL for lunch / break
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    display_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_teaching_slot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    template: Mapped[TimingTemplate] = relationship(back_populates="slots")


class Room(UUIDPk, Timestamps, Base):
    """A bookable room. Timetable entries and lecture schedules store the room name, so history never breaks."""

    __tablename__ = "rooms"
    __table_args__ = (CheckConstraint(f"room_type IN ({sql_in(RoomType)})", name="room_type_valid"),)

    name: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    room_type: Mapped[str] = mapped_column(String(12), nullable=False, default=RoomType.CLASSROOM)
    capacity: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class Holiday(UUIDPk, Timestamps, Base):
    __tablename__ = "holidays"

    date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)


class TimetableVersion(UUIDPk, Timestamps, Base):
    """One state of the institution's recurring weekly timetable.

    Exactly one DRAFT may exist (the admin's working copy, produced by Generate or by Edit) and one
    PUBLISHED (what every role sees). Publishing archives the previous version instead of overwriting it.
    """

    __tablename__ = "timetable_versions"
    __table_args__ = (
        CheckConstraint(f"status IN ({sql_in(TimetableStatus)})", name="status_valid"),
        Index("uq_timetable_versions_one_draft", "status", unique=True, postgresql_where=text("status = 'DRAFT'"), sqlite_where=text("status = 'DRAFT'")),
        Index("uq_timetable_versions_one_published", "status", unique=True, postgresql_where=text("status = 'PUBLISHED'"), sqlite_where=text("status = 'PUBLISHED'")),
    )

    status: Mapped[str] = mapped_column(String(12), nullable=False, default=TimetableStatus.DRAFT)
    version_number: Mapped[int | None] = mapped_column(Integer)  # assigned at publish
    note: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    published_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    entries: Mapped[list["TimetableEntry"]] = relationship(back_populates="version", cascade="all, delete-orphan")
    published_by = relationship("User", foreign_keys=[published_by_id], lazy="joined")


class TimetableEntry(UUIDPk, Timestamps, Base):
    """One recurring class: this subject-section (teaching plan) meets every <weekday> from start to end.

    Clock times are stored, never just a lecture number - a lab simply has a longer interval, and every
    clash check compares real intervals. The professor is the plan's professor unless overridden here.
    """

    __tablename__ = "timetable_entries"
    __table_args__ = (
        CheckConstraint("end_time > start_time", name="times_ordered"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint(f"class_type IN ({sql_in(ClassType)})", name="class_type_valid"),
        Index("ix_timetable_entries_version_day", "version_id", "weekday"),
    )

    version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("timetable_versions.id", ondelete="CASCADE"), nullable=False)
    teaching_plan_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("teaching_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    professor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    weekday: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 0 = Monday
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    room: Mapped[str | None] = mapped_column(String(40))
    class_type: Mapped[str] = mapped_column(String(12), nullable=False, default=ClassType.THEORY)

    version: Mapped[TimetableVersion] = relationship(back_populates="entries")
    teaching_plan = relationship("TeachingPlan", lazy="joined")
    professor_override = relationship("User", foreign_keys=[professor_id], lazy="joined")

    @property
    def effective_professor(self):
        return self.professor_override or self.teaching_plan.professor
