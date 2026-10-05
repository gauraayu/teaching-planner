import uuid

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import Role, ScopeMode, sql_in
from app.db.base import Base, JSONB, Timestamps, UTCDateTime, UUIDPk, Uuid


class RoleModel(UUIDPk, Base):
    __tablename__ = "roles"
    __table_args__ = (CheckConstraint(f"code IN ({sql_in(Role)})", name="code_valid"),)

    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))


class User(UUIDPk, Timestamps, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    designation: Mapped[str | None] = mapped_column(String(120))
    role_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False, index=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("departments.id", ondelete="SET NULL"))
    employee_code: Mapped[str | None] = mapped_column(String(40), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    username: Mapped[str | None] = mapped_column(String(60), unique=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    # scrypt hash (see app/core/security.py). The password itself is never stored. NULL = cannot sign in.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    # True while the user still has the temporary password an administrator set.
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    role: Mapped[RoleModel] = relationship(lazy="joined")
    department = relationship("Department", lazy="joined")
    scope: Mapped["UserScope | None"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan", lazy="joined")

    @property
    def role_code(self) -> Role:
        return Role(self.role.code)


class UserScope(UUIDPk, Timestamps, Base):
    """What a user's role applies to. One row per user, set by the administrator.

    CL/CH  which professors' submissions they verify
    OM     which classes they see, record and final verify
    PROFESSOR  `subject_ids` lists the subjects the professor may be allocated (eligibility)

    mode ALL ignores the lists. With SELECTED, an empty list means "no restriction on that
    dimension", so "CSE, Semester V, sections A and B, all subjects" needs no subject list.
    No row at all behaves like ALL.
    """

    __tablename__ = "user_scopes"
    __table_args__ = (CheckConstraint(f"mode IN ({sql_in(ScopeMode)})", name="mode_valid"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default=ScopeMode.ALL, server_default=ScopeMode.ALL.value)
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("departments.id", ondelete="SET NULL"))
    semester_numbers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")  # [5, 6]
    section_names: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")     # ["A", "B"]
    subject_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")       # [uuid, ...]

    user: Mapped[User] = relationship(back_populates="scope")
    department = relationship("Department", lazy="joined")
