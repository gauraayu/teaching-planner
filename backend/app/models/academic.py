import uuid
from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Integer, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPk, Uuid


class AcademicYear(UUIDPk, Timestamps, Base):
    __tablename__ = "academic_years"
    __table_args__ = (CheckConstraint("end_date > start_date", name="dates_ordered"),)

    name: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)  # "2026–27"
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

    semesters: Mapped[list["Semester"]] = relationship(back_populates="academic_year", order_by="Semester.number")


class Semester(UUIDPk, Timestamps, Base):
    __tablename__ = "semesters"
    __table_args__ = (
        UniqueConstraint("academic_year_id", "number"),
        CheckConstraint("number BETWEEN 1 AND 12", name="number_range"),
        CheckConstraint("end_date > start_date", name="dates_ordered"),
    )

    academic_year_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("academic_years.id", ondelete="RESTRICT"), nullable=False, index=True)
    number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(40), nullable=False)  # "Semester V"
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

    academic_year: Mapped[AcademicYear] = relationship(back_populates="semesters", lazy="joined")


class Department(UUIDPk, Timestamps, Base):
    __tablename__ = "departments"

    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)


class Branch(UUIDPk, Timestamps, Base):
    __tablename__ = "branches"
    __table_args__ = (UniqueConstraint("department_id", "code"),)

    department_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    department: Mapped[Department] = relationship(lazy="joined")


class Section(UUIDPk, Timestamps, Base):
    __tablename__ = "sections"
    __table_args__ = (UniqueConstraint("branch_id", "semester_id", "name"),)

    branch_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True)
    semester_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("semesters.id", ondelete="RESTRICT"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(10), nullable=False)  # "A"
    student_count: Mapped[int | None] = mapped_column(Integer)

    branch: Mapped[Branch] = relationship(lazy="joined")
    semester: Mapped[Semester] = relationship(lazy="joined")


class Subject(UUIDPk, Timestamps, Base):
    __tablename__ = "subjects"
    __table_args__ = (CheckConstraint("semester_number BETWEEN 1 AND 12", name="semester_number_range"),)

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(20))
    branch_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True)
    semester_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    credits: Mapped[int | None] = mapped_column(SmallInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)

    branch: Mapped[Branch] = relationship(lazy="joined")


class FacultySubjectAssignment(UUIDPk, Timestamps, Base):
    """Which professor teaches which subject to which section in a semester."""

    __tablename__ = "faculty_subject_assignments"
    __table_args__ = (UniqueConstraint("subject_id", "section_id", "semester_id", "professor_id"),)

    professor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    subject_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False, index=True)
    section_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("sections.id", ondelete="RESTRICT"), nullable=False)
    semester_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("semesters.id", ondelete="RESTRICT"), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)

    professor = relationship("User", lazy="joined")
    subject: Mapped[Subject] = relationship(lazy="joined")
    section: Mapped[Section] = relationship(lazy="joined")
