import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ExecutionStatus, MaterialType, SubmissionStatus, sql_in
from app.db.base import Base, Timestamps, UTCDateTime, UUIDPk, Uuid


class LectureProgress(UUIDPk, Timestamps, Base):
    """Execution data owned by the professor. One row per lecture, created lazily on first save."""

    __tablename__ = "lecture_progress"
    __table_args__ = (
        CheckConstraint(f"execution_status IN ({sql_in(ExecutionStatus)})", name="execution_status_valid"),
        CheckConstraint(f"submission_status IN ({sql_in(SubmissionStatus)})", name="submission_status_valid"),
        CheckConstraint(
            "(shared_with_students IS NULL OR shared_with_students <> 0) OR length(trim(coalesce(not_shared_reason, ''))) > 0",
            name="not_shared_needs_reason",
        ),
        Index("ix_lecture_progress_professor_status", "professor_id", "execution_status"),
        Index("ix_lecture_progress_submission_status", "submission_status"),
    )

    lecture_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("lectures.id", ondelete="CASCADE"), nullable=False, unique=True)
    professor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)

    execution_status: Mapped[str] = mapped_column(String(24), nullable=False, default=ExecutionStatus.SCHEDULED)
    submission_status: Mapped[str] = mapped_column(String(24), nullable=False, default=SubmissionStatus.DRAFT)
    actual_completion_date: Mapped[date | None] = mapped_column(Date)
    rescheduled_to: Mapped[date | None] = mapped_column(Date)  # proposed new date; planned_date stays untouched
    remarks: Mapped[str | None] = mapped_column(Text)

    shared_with_students: Mapped[bool | None] = mapped_column(Boolean)
    shared_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    not_shared_reason: Mapped[str | None] = mapped_column(Text)

    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    submission_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    final_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    # The professor's own Start Class / End Class clicks (server time). Deliberately separate
    # from class_sessions.entry_at / exit_at, which are the OM's official observation.
    professor_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    professor_ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    checkin_mode: Mapped[str | None] = mapped_column(String(16))  # TIME | IMAGE | SKIPPED
    recording_url: Mapped[str | None] = mapped_column(Text)       # optional link; the video itself is never stored here
    additional_topics: Mapped[str | None] = mapped_column(Text)   # anything taught beyond the planned subtopics

    lecture = relationship("Lecture", back_populates="progress", lazy="joined")
    professor = relationship("User", lazy="joined")
    subtopic_progress: Mapped[list["LectureSubtopicProgress"]] = relationship(back_populates="progress", cascade="all, delete-orphan")
    materials: Mapped[list["LectureMaterial"]] = relationship(back_populates="progress", cascade="all, delete-orphan", order_by="LectureMaterial.created_at")
    assignment: Mapped["Assignment | None"] = relationship(back_populates="progress", uselist=False, cascade="all, delete-orphan")
    verifications = relationship("Verification", back_populates="progress", order_by="Verification.created_at")


class LectureSubtopicProgress(UUIDPk, Timestamps, Base):
    __tablename__ = "lecture_subtopic_progress"
    __table_args__ = (UniqueConstraint("lecture_progress_id", "subtopic_id"),)

    lecture_progress_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("lecture_progress.id", ondelete="CASCADE"), nullable=False, index=True)
    subtopic_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("lecture_subtopics.id", ondelete="CASCADE"), nullable=False)
    is_covered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    progress: Mapped[LectureProgress] = relationship(back_populates="subtopic_progress")


class LectureMaterial(UUIDPk, Timestamps, Base):
    """Metadata only - binaries live in object storage, never in the database."""

    __tablename__ = "lecture_materials"
    __table_args__ = (CheckConstraint(f"material_type IN ({sql_in(MaterialType)})", name="material_type_valid"),)

    lecture_progress_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("lecture_progress.id", ondelete="CASCADE"), nullable=False, index=True)
    material_type: Mapped[str] = mapped_column(String(24), nullable=False, default=MaterialType.LECTURE_NOTES)
    title: Mapped[str | None] = mapped_column(String(200))
    caption: Mapped[str | None] = mapped_column(String(300))
    file_name: Mapped[str | None] = mapped_column(String(255))
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(512))  # set when the file is in our bucket
    content_type: Mapped[str | None] = mapped_column(String(100))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    progress: Mapped[LectureProgress] = relationship(back_populates="materials")


class Assignment(UUIDPk, Timestamps, Base):
    __tablename__ = "assignments"
    __table_args__ = (
        CheckConstraint(
            "(shared_with_students IS NULL OR shared_with_students <> 0) OR length(trim(coalesce(not_shared_reason, ''))) > 0",
            name="not_shared_needs_reason",
        ),
    )

    lecture_progress_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("lecture_progress.id", ondelete="CASCADE"), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    link_url: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date | None] = mapped_column(Date)
    shared_with_students: Mapped[bool | None] = mapped_column(Boolean)
    shared_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    not_shared_reason: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    progress: Mapped[LectureProgress] = relationship(back_populates="assignment")