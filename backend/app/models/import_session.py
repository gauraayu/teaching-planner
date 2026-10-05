import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ImportMode, ImportStatus, sql_in
from app.db.base import Base, JSONB, Timestamps, UTCDateTime, UUIDPk, Uuid


class ImportSession(UUIDPk, Timestamps, Base):
    """Temporary, resumable workspace for one teaching-plan import.

    JSONB holds only in-flight draft data. On commit, rows are written into the
    normalized lecture tables and this session becomes a historical record.
    """

    __tablename__ = "import_sessions"
    __table_args__ = (
        CheckConstraint(f"import_mode IS NULL OR import_mode IN ({sql_in(ImportMode)})", name="mode_valid"),
        CheckConstraint(f"status IN ({sql_in(ImportStatus)})", name="status_valid"),
    )

    admin_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    teaching_plan_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("teaching_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False)
    semester_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("semesters.id", ondelete="RESTRICT"), nullable=False)
    section_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("sections.id", ondelete="RESTRICT"), nullable=False)
    faculty_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    import_mode: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=ImportStatus.DRAFT, index=True)
    current_step: Mapped[str | None] = mapped_column(String(32))
    source_name: Mapped[str | None] = mapped_column(String(255))

    draft_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    column_mapping: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    validation_result: Mapped[dict | None] = mapped_column(JSONB)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # bumps on every draft change
    validated_revision: Mapped[int | None] = mapped_column(Integer)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    committed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    failure_reason: Mapped[str | None] = mapped_column(Text)

    teaching_plan = relationship("TeachingPlan", lazy="joined")
