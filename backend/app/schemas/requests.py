"""Request bodies. `extra="forbid"` everywhere: unknown fields are rejected, which is
how a professor is prevented from smuggling master-plan fields into an execution update."""
import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.core.enums import (
    CarryForwardStatus, ChangeReason, ClassType, DelayReason, ExecutionStatus, ImportMode, PlanStatus, Role, RoomType, ScopeMode, SlotType,
)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ------------------------------------------------------------------ auth

class LoginRequest(Strict):
    identifier: str = Field(min_length=1, max_length=255, description="Email, username or employee ID")
    password: str = Field(min_length=1, max_length=200)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)  # a password may start or end with a space


class ChangePassword(Strict):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


# ------------------------------------------------------------------ user management (admin)

class ScopeIn(Strict):
    mode: ScopeMode = ScopeMode.ALL
    department_id: uuid.UUID | None = None
    semester_numbers: list[int] = Field(default_factory=list, max_length=12)
    section_names: list[str] = Field(default_factory=list, max_length=30)
    subject_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)

    @field_validator("semester_numbers")
    @classmethod
    def _semesters(cls, v):
        if any(n < 1 or n > 12 for n in v):
            raise ValueError("Semester numbers must be between 1 and 12.")
        return sorted(set(v))

    @field_validator("section_names")
    @classmethod
    def _sections(cls, v):
        return sorted({s.strip().upper() for s in v if s and s.strip()})


EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
USERNAME = r"^[A-Za-z0-9._-]{3,60}$"


class UserCreate(Strict):
    full_name: str = Field(min_length=2, max_length=120)
    employee_id: str = Field(min_length=1, max_length=40)
    email: str = Field(max_length=255, pattern=EMAIL)
    username: str | None = Field(default=None, pattern=USERNAME)
    role: Role
    department_id: uuid.UUID | None = None
    designation: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=20)
    password: str = Field(min_length=8, max_length=200, description="Temporary password; the user is asked to change it")
    is_active: bool = True
    scope: ScopeIn | None = None


class UserUpdate(Strict):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    employee_id: str | None = Field(default=None, min_length=1, max_length=40)
    email: str | None = Field(default=None, max_length=255, pattern=EMAIL)
    username: str | None = Field(default=None, pattern=USERNAME)
    role: Role | None = None
    department_id: uuid.UUID | None = None
    designation: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=20)
    is_active: bool | None = None
    scope: ScopeIn | None = None


class PasswordReset(Strict):
    password: str = Field(min_length=8, max_length=200)


# ------------------------------------------------------------------ academic

class AcademicYearIn(Strict):
    name: str = Field(min_length=4, max_length=20)
    start_date: date
    end_date: date
    is_current: bool = False


class SemesterIn(Strict):
    academic_year_id: uuid.UUID
    number: int = Field(ge=1, le=12)
    name: str | None = Field(default=None, max_length=40)
    start_date: date
    end_date: date
    is_current: bool = False


class DepartmentIn(Strict):
    code: str = Field(min_length=1, max_length=16)
    name: str = Field(min_length=2, max_length=120)


class BranchIn(Strict):
    department_id: uuid.UUID
    code: str = Field(min_length=1, max_length=16)
    name: str = Field(min_length=2, max_length=120)


class SectionIn(Strict):
    branch_id: uuid.UUID
    semester_id: uuid.UUID
    name: str = Field(min_length=1, max_length=10)
    student_count: int | None = Field(default=None, ge=0, le=1000)


class SubjectIn(Strict):
    code: str = Field(min_length=2, max_length=20)
    name: str = Field(min_length=2, max_length=160)
    short_name: str | None = Field(default=None, max_length=20)
    branch_id: uuid.UUID
    semester_number: int = Field(ge=1, le=12)
    credits: int | None = Field(default=None, ge=0, le=12)


class FacultyAssignmentIn(Strict):
    professor_id: uuid.UUID
    subject_id: uuid.UUID
    section_id: uuid.UUID


# ------------------------------------------------------------------ plans

class TeachingPlanCreate(Strict):
    academic_year_id: uuid.UUID
    semester_id: uuid.UUID
    department_id: uuid.UUID
    branch_id: uuid.UUID
    section_id: uuid.UUID
    subject_id: uuid.UUID
    professor_id: uuid.UUID
    name: str | None = Field(default=None, max_length=200)
    room: str | None = Field(default=None, max_length=40)  # default classroom, shown to the Operations Manager
    classes_per_week: int = Field(default=0, ge=0, le=12)   # subject allocation: what Generate Schedule places
    labs_per_week: int = Field(default=0, ge=0, le=6)       # each lab takes two consecutive periods
    lab_room: str | None = Field(default=None, max_length=40)
    sprint_plan_id: uuid.UUID | None = None  # the semester sprint plan this subject is part of


class PlanAllocation(Strict):
    """Weekly load of one subject-section. Changing it never touches lectures or the published timetable."""

    classes_per_week: int = Field(ge=0, le=12)
    labs_per_week: int = Field(default=0, ge=0, le=6)
    room: str | None = Field(default=None, max_length=40)
    lab_room: str | None = Field(default=None, max_length=40)


class PlanStatusChange(Strict):
    status: Literal[PlanStatus.PUBLISHED, PlanStatus.ARCHIVED]
    reason: str | None = Field(default=None, max_length=500)


class LectureCorrection(Strict):
    """Controlled admin edit of a published lecture. A reason is mandatory and audited."""

    reason: str = Field(min_length=5, max_length=500)
    content_topic: str | None = Field(default=None, min_length=1)
    unit_no: int | None = Field(default=None, ge=1, le=20)
    blooms_taxonomy: Literal["K1", "K2", "K3", "K4", "K5", "K6"] | None = None
    lecture_type: str | None = None
    planned_date: date | None = None
    planned_start_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    planned_end_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    subtopics: list[str] | None = None
    # Allocation: who teaches this one lecture and where. Sending the plan's own professor clears the override.
    professor_id: uuid.UUID | None = None
    room: str | None = Field(default=None, max_length=40)


# ------------------------------------------------------------------ imports

class ImportSessionCreate(Strict):
    teaching_plan_id: uuid.UUID
    resume: bool = True


class ImportModeIn(Strict):
    import_mode: ImportMode


class FullTablePaste(Strict):
    # Never strip: a leading tab is an empty first cell, and removing it would shift every column.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    raw_text: str = Field(min_length=1, max_length=5_000_000)
    has_header: bool | None = None


class HeaderToggle(Strict):
    has_header: bool


class ColumnPaste(Strict):
    field: str
    raw_text: str = Field(min_length=1, max_length=2_000_000)
    order: int | None = Field(default=None, ge=1, le=50)
    replace_key: str | None = None
    on_mismatch: Literal["PAD", "EXTEND"] | None = None

    # Never strip: leading blank lines are real (empty) rows and must keep their index.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class MappingUpdate(Strict):
    field: str | None = None
    ignore: bool = False
    confirm: bool = False
    fill_down: bool | None = None
    order: int | None = Field(default=None, ge=1, le=50)


class MappingUpdateRequest(Strict):
    columns: dict[str, MappingUpdate]


class RowEdit(Strict):
    values: dict[str, str | list[str] | None]


class RowRemoval(Strict):
    removed: bool = True


class ImportCommit(Strict):
    publish: bool = True
    confirm: bool = Field(description="Must be true - mirrors the confirmation dialog")

    @field_validator("confirm")
    @classmethod
    def _must_confirm(cls, v):
        if not v:
            raise ValueError("Confirm the summary before publishing.")
        return v


# ------------------------------------------------------------------ professor

class MaterialIn(Strict):
    id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=200)
    file_url: HttpUrl


class AssignmentIn(Strict):
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    link_url: HttpUrl | None = None
    due_date: date | None = None
    shared_with_students: bool | None = None
    not_shared_reason: str | None = Field(default=None, max_length=1000)


class ProgressUpdate(Strict):
    execution_status: ExecutionStatus
    actual_completion_date: date | None = None
    rescheduled_to: date | None = None
    covered_subtopic_ids: list[uuid.UUID] = Field(default_factory=list)
    remarks: str | None = Field(default=None, max_length=4000)
    shared_with_students: bool | None = None
    not_shared_reason: str | None = Field(default=None, max_length=1000)
    notes: list[MaterialIn] = Field(default_factory=list, max_length=10)
    assignment: AssignmentIn | None = None
    recording_url: HttpUrl | None = None
    additional_topics: str | None = Field(default=None, max_length=1000)


# ------------------------------------------------------------------ verification

class VerifyRequest(Strict):
    remarks: str | None = Field(default=None, max_length=2000)


class CorrectionRequest(Strict):
    remarks: str = Field(min_length=5, max_length=2000)


# ------------------------------------------------------------------ classroom operations (OM)

class EntryRecord(Strict):
    """Professor's actual entry into the classroom.

    Clock In sends no time: the server's clock is used. `time` (wall-clock, on the class date) is only for
    correcting a record afterwards."""

    time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    delay_reason: DelayReason | None = None
    delay_remarks: str | None = Field(default=None, max_length=500)


class ExitRecord(Strict):
    time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    early_exit_reason: str | None = Field(default=None, max_length=500)


# ------------------------------------------------------------------ weekly sprint plan (admin)

HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class SprintMeetingStart(Strict):
    week_start: date
    meeting_date: date | None = None
    meeting_notes: str | None = Field(default=None, max_length=4000)


class SprintMeetingUpdate(Strict):
    meeting_date: date | None = None
    meeting_notes: str | None = Field(default=None, max_length=4000)


class SprintLectureEdit(Strict):
    """Only the fields that are sent are considered; unchanged values are dropped server-side."""

    planned_date: date | None = None
    planned_start_time: str | None = Field(default=None, pattern=HHMM)
    planned_end_time: str | None = Field(default=None, pattern=HHMM)
    room: str | None = Field(default=None, max_length=40)
    professor_id: uuid.UUID | None = None
    content_topic: str | None = Field(default=None, max_length=500)
    subtopics: list[str] | None = Field(default=None, max_length=20)
    lecture_type: str | None = None
    reason: ChangeReason
    remarks: str | None = Field(default=None, max_length=1000)


class SprintCancel(Strict):
    reason: ChangeReason
    remarks: str | None = Field(default=None, max_length=1000)


class SprintLectureAdd(Strict):
    teaching_plan_id: uuid.UUID
    content_topic: str = Field(min_length=2, max_length=500)
    subtopics: list[str] = Field(default_factory=list, max_length=20)
    planned_date: date
    planned_start_time: str = Field(pattern=HHMM)
    planned_end_time: str | None = Field(default=None, pattern=HHMM)
    room: str | None = Field(default=None, max_length=40)
    professor_id: uuid.UUID | None = None
    lecture_type: str = "THEORY"
    reason: ChangeReason
    remarks: str | None = Field(default=None, max_length=1000)
    carry_forward_lecture_id: uuid.UUID | None = None


class SprintPublish(Strict):
    meeting_notes: str | None = Field(default=None, max_length=4000)


class CarryForwardDecision(Strict):
    status: Literal[CarryForwardStatus.DEFERRED, CarryForwardStatus.RESOLVED, CarryForwardStatus.OPEN]
    note: str | None = Field(default=None, max_length=500)


# ------------------------------------------------------------------ live class (professor)

class StartClass(Strict):
    checkin: Literal["TIME", "IMAGE", "SKIPPED"] = "SKIPPED"


# ------------------------------------------------------------------ weekly sprint plan from the timetable

class SprintGenerate(Strict):
    """MAKE WEEKLY SPRINT PLAN. Without a week it plans next week. Always produces a draft."""

    week_start: date | None = None
    replace: bool = False  # a draft with changes already exists: replace them


# ------------------------------------------------------------------ timing templates, rooms, holidays, master timetable

class TimingSlotIn(Strict):
    slot_type: SlotType = SlotType.LECTURE
    start_time: str = Field(pattern=HHMM)
    end_time: str = Field(pattern=HHMM)

    @field_validator("end_time")
    @classmethod
    def ordered(cls, v, info):
        if info.data.get("start_time") and v <= info.data["start_time"]:
            raise ValueError("End time must be after start time.")
        return v


class TimingTemplateIn(Strict):
    name: str = Field(min_length=2, max_length=80)
    short_name: str = Field(min_length=1, max_length=24)
    description: str | None = Field(default=None, max_length=255)
    semester_numbers: list[int] = Field(default_factory=list, max_length=12)
    slots: list[TimingSlotIn] = Field(min_length=1, max_length=20)

    @field_validator("semester_numbers")
    @classmethod
    def valid_numbers(cls, v):
        if any(n < 1 or n > 12 for n in v):
            raise ValueError("Semester numbers are 1 to 12.")
        return sorted(set(v))


class RoomIn(Strict):
    name: str = Field(min_length=1, max_length=40)
    room_type: RoomType = RoomType.CLASSROOM
    capacity: int | None = Field(default=None, ge=1, le=2000)
    is_active: bool = True


class HolidayIn(Strict):
    date: date
    name: str = Field(min_length=2, max_length=120)


class TimetableEntryIn(Strict):
    teaching_plan_id: uuid.UUID
    weekday: int = Field(ge=0, le=6)
    start_time: str = Field(pattern=HHMM)
    end_time: str = Field(pattern=HHMM)
    room: str | None = Field(default=None, max_length=40)
    class_type: ClassType = ClassType.THEORY
    professor_id: uuid.UUID | None = None  # only when someone other than the plan's professor takes this class


class TimetableGenerate(Strict):
    days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], max_length=7)
    replace: bool = True  # False keeps the classes already in the timetable and only places what is missing

    @field_validator("days")
    @classmethod
    def valid_days(cls, v):
        if not v or any(d < 0 or d > 6 for d in v):
            raise ValueError("Choose at least one working day (0 = Monday ... 6 = Sunday).")
        return v


class TimetablePublish(Strict):
    note: str | None = Field(default=None, max_length=1000)


# ------------------------------------------------------------------ semester sprint plan

class SprintPlanIn(Strict):
    name: str = Field(min_length=3, max_length=200)
    academic_year_id: uuid.UUID
    start_date: date
    end_date: date
    working_days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5], min_length=1, max_length=7)

    @field_validator("working_days")
    @classmethod
    def valid_days(cls, v):
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("Working days are 0 (Monday) to 6 (Sunday).")
        return sorted(set(v))


class SprintPlanSubject(Strict):
    teaching_plan_id: uuid.UUID


class WeekPublish(Strict):
    week_start: date
