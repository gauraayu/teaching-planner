import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, SmallInteger, String, Text, Time,
    UniqueConstraint, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import BloomLevel, LectureType, PlanStatus, sql_in
from app.db.base import Base, JSONB, Timestamps, UTCDateTime, UUIDPk, Uuid


class TeachingPlan(UUIDPk, Timestamps, Base):
    __tablename__ = "teaching_plans"
    __table_args__ = (
        CheckConstraint(f"status IN ({sql_in(PlanStatus)})", name="status_valid"),
        # Hard backstop for duplicate protection: one live plan per subject/section/semester.
        Index(
            "uq_teaching_plans_live_subject_section",
            "subject_id", "section_id", "semester_id",
            unique=True,
            postgresql_where=text("status <> 'ARCHIVED'"), sqlite_where=text("status <> 'ARCHIVED'"),
        ),
        Index("ix_teaching_plans_professor_status", "professor_id", "status"),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    academic_year_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("academic_years.id", ondelete="RESTRICT"), nullable=False)
    semester_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("semesters.id", ondelete="RESTRICT"), nullable=False, index=True)
    department_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False)
    section_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("sections.id", ondelete="RESTRICT"), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False, index=True)
    professor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=PlanStatus.DRAFT, server_default=PlanStatus.DRAFT.value)
    # Default classroom for this plan's lectures; a lecture's own schedule.room overrides it.
    room: Mapped[str | None] = mapped_column(String(40))
    # Subject allocation for the timetable generator: how often this subject-section meets in a normal week.
    classes_per_week: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")
    labs_per_week: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")  # each lab = 2 consecutive lecture slots
    lab_room: Mapped[str | None] = mapped_column(String(40))
    # The semester sprint plan this subject belongs to. NULL = a stand-alone plan with its own imported dates.
    sprint_plan_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("semester_sprint_plans.id", ondelete="SET NULL"), index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    published_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    academic_year = relationship("AcademicYear", lazy="joined")
    semester = relationship("Semester", lazy="joined")
    department = relationship("Department", lazy="joined")
    branch = relationship("Branch", lazy="joined")
    section = relationship("Section", lazy="joined")
    subject = relationship("Subject", lazy="joined")
    professor = relationship("User", foreign_keys=[professor_id], lazy="joined")
    sprint_plan = relationship("SemesterSprintPlan", back_populates="plans")

    lectures: Mapped[list["Lecture"]] = relationship(
        back_populates="teaching_plan", order_by="Lecture.sequence", cascade="all, delete-orphan"
    )


class Lecture(UUIDPk, Timestamps, Base):
    __tablename__ = "lectures"
    __table_args__ = (
        UniqueConstraint("teaching_plan_id", "lecture_no"),
        CheckConstraint("lecture_no > 0", name="lecture_no_positive"),
        CheckConstraint("unit_no IS NULL OR unit_no > 0", name="unit_no_positive"),
        CheckConstraint(f"lecture_type IN ({sql_in(LectureType)})", name="lecture_type_valid"),
        CheckConstraint(f"blooms_taxonomy IS NULL OR blooms_taxonomy IN ({sql_in(BloomLevel)})", name="bloom_valid"),
        CheckConstraint("length(trim(content_topic)) > 0", name="topic_not_blank"),
    )

    teaching_plan_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("teaching_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    serial_no: Mapped[int | None] = mapped_column(Integer)
    lecture_no: Mapped[int] = mapped_column(Integer, nullable=False)
    lecture_type: Mapped[str] = mapped_column(String(16), nullable=False, default=LectureType.THEORY)
    unit_no: Mapped[int | None] = mapped_column(SmallInteger)
    content_topic: Mapped[str] = mapped_column(Text, nullable=False)
    blooms_taxonomy: Mapped[str | None] = mapped_column(String(2))
    import_row_index: Mapped[int | None] = mapped_column(Integer)  # traceability back to the source sheet row

    # --- weekly sprint revisions -------------------------------------------------
    # Substitute for this one lecture; NULL means the plan's professor teaches it.
    professor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    is_cancelled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # False = only a projection inside the semester sprint; professors, CL/CH and OM see a class once its week is published.
    is_released: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="MASTER", server_default="MASTER")
    carried_from_lecture_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("lectures.id", ondelete="SET NULL"))
    # The semester master plan's values for this lecture, captured the first time a weekly
    # revision changes it and never rewritten. NULL = the lecture still matches the master plan.
    master_snapshot: Mapped[dict | None] = mapped_column(JSONB)

    teaching_plan: Mapped[TeachingPlan] = relationship(back_populates="lectures")
    subtopics: Mapped[list["LectureSubtopic"]] = relationship(
        back_populates="lecture", order_by="LectureSubtopic.position", cascade="all, delete-orphan"
    )
    schedule: Mapped["LectureSchedule | None"] = relationship(back_populates="lecture", uselist=False, cascade="all, delete-orphan")
    progress = relationship("LectureProgress", back_populates="lecture", uselist=False)
    class_session = relationship("ClassSession", back_populates="lecture", uselist=False)
    substitute = relationship("User", foreign_keys=[professor_id], lazy="joined")

    @property
    def effective_professor_id(self) -> uuid.UUID:
        return self.professor_id or self.teaching_plan.professor_id

    @property
    def effective_professor(self):
        return self.substitute or self.teaching_plan.professor


class LectureSubtopic(UUIDPk, Timestamps, Base):
    __tablename__ = "lecture_subtopics"
    __table_args__ = (
        UniqueConstraint("lecture_id", "position"),
        CheckConstraint("length(trim(title)) > 0", name="title_not_blank"),
    )

    lecture_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("lectures.id", ondelete="CASCADE"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)

    lecture: Mapped[Lecture] = relationship(back_populates="subtopics")


class LectureSchedule(UUIDPk, Timestamps, Base):
    """The original, Admin-owned schedule. Never overwritten by execution data."""

    __tablename__ = "lecture_schedules"
    __table_args__ = (
        CheckConstraint(
            "planned_end_time IS NULL OR planned_start_time IS NULL OR planned_end_time > planned_start_time",
            name="times_ordered",
        ),
    )

    lecture_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("lectures.id", ondelete="CASCADE"), nullable=False, unique=True)
    planned_date: Mapped[date | None] = mapped_column(Date, index=True)
    planned_start_time: Mapped[time | None] = mapped_column(Time)
    planned_end_time: Mapped[time | None] = mapped_column(Time)
    room: Mapped[str | None] = mapped_column(String(40))

    lecture: Mapped[Lecture] = relationship(back_populates="schedule")
