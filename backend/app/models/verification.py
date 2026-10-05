import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import VerificationLevel, VerificationStatus, role_sql, sql_in
from app.db.base import Base, Timestamps, UTCDateTime, UUIDPk, Uuid


class Verification(UUIDPk, Timestamps, Base):
    """One row per verification step per submission round - never a boolean flag.

    Round 1: CL_CH PENDING -> CL_CH VERIFIED -> OM PENDING -> OM VERIFIED (final).
    A correction request closes the round; the resubmission opens round 2.
    """

    __tablename__ = "verifications"
    __table_args__ = (
        CheckConstraint(f"status IN ({sql_in(VerificationStatus)})", name="status_valid"),
        CheckConstraint(f"verification_level IN ({sql_in(VerificationLevel)})", name="level_valid"),
        CheckConstraint(f"verifier_role IS NULL OR verifier_role IN ({role_sql()})", name="verifier_role_valid"),
        CheckConstraint(
            "status <> 'CORRECTION_REQUIRED' OR length(trim(coalesce(remarks, ''))) > 0",
            name="correction_needs_remarks",
        ),
        # At most one open step per submission at any time.
        Index(
            "uq_verifications_one_pending", "lecture_progress_id",
            unique=True, postgresql_where=text("status = 'PENDING'"), sqlite_where=text("status = 'PENDING'"),
        ),
        Index("ix_verifications_level_status", "verification_level", "status"),
    )

    lecture_progress_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("lecture_progress.id", ondelete="CASCADE"), nullable=False, index=True)
    round: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    verification_level: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=VerificationStatus.PENDING, index=True)
    verifier_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    verifier_role: Mapped[str | None] = mapped_column(String(16))
    remarks: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    progress = relationship("LectureProgress", back_populates="verifications", lazy="joined")
    verifier = relationship("User", lazy="joined")
