"""Every controlled status/value in the system lives here.

Database CHECK constraints, Pydantic schemas and the frontend constants
are all derived from these enums - never write raw status strings elsewhere.
"""
from enum import StrEnum


class Role(StrEnum):
    ADMIN = "ADMIN"
    PROFESSOR = "PROFESSOR"
    CL_CH = "CL_CH"  # one academic verifier role, shown as "CL/CH"
    OM = "OM"  # Operations Manager: live class timings + final verification


# Display names. Code and database use the identifiers; people see the labels.
ROLE_LABELS: dict[str, str] = {"ADMIN": "Admin", "PROFESSOR": "Professor", "CL_CH": "CL/CH", "OM": "OM",
                               "CL": "CL (legacy)", "CH": "CH (legacy)"}

# CL and CH were separate roles until they were merged into CL_CH. No account holds them any more,
# but audit rows and old verification records still name them, so the database keeps accepting the values.
LEGACY_ROLES: tuple[str, ...] = ("CL", "CH")

# Roles an administrator can create accounts for.
MANAGED_ROLES: tuple[Role, ...] = (Role.PROFESSOR, Role.CL_CH, Role.OM)


def role_sql() -> str:
    return ", ".join(f"'{v}'" for v in [*(r.value for r in Role), *LEGACY_ROLES])


class ScopeMode(StrEnum):
    ALL = "ALL"            # every professor / every class
    SELECTED = "SELECTED"  # only the department / semesters / sections / subjects listed on the scope


class PlanStatus(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class LectureType(StrEnum):
    THEORY = "THEORY"
    PRACTICAL = "PRACTICAL"
    TUTORIAL = "TUTORIAL"
    REVISION = "REVISION"
    ASSESSMENT = "ASSESSMENT"
    OTHER = "OTHER"


class BloomLevel(StrEnum):
    K1 = "K1"  # Remember
    K2 = "K2"  # Understand
    K3 = "K3"  # Apply
    K4 = "K4"  # Analyse
    K5 = "K5"  # Evaluate
    K6 = "K6"  # Create


class ExecutionStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    COMPLETED = "COMPLETED"
    RESCHEDULED = "RESCHEDULED"
    NOT_CONDUCTED = "NOT_CONDUCTED"  # the class did not happen; its topic becomes a carry-forward item


class SubmissionStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    CORRECTION_REQUIRED = "CORRECTION_REQUIRED"
    RESUBMITTED = "RESUBMITTED"
    FINAL_VERIFIED = "FINAL_VERIFIED"


class VerificationStatus(StrEnum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    CORRECTION_REQUIRED = "CORRECTION_REQUIRED"
    SUPERSEDED = "SUPERSEDED"  # a pending row cancelled because the chain restarted


class VerificationLevel(StrEnum):
    CL_CH = "CL_CH"  # academic verification
    OM = "OM"        # operational + final verification
    # Legacy: a separate CH step existed before CL and CH were merged. Never created now;
    # kept so historical CH decisions stay readable in the audit trail.
    CH = "CH"


# Ordered verification chain: Professor submits -> CL/CH -> OM (final).
VERIFICATION_CHAIN: tuple[VerificationLevel, ...] = (VerificationLevel.CL_CH, VerificationLevel.OM)
LEVEL_LABELS: dict[str, str] = {"CL_CH": "CL/CH", "OM": "OM", "CH": "CH (legacy)"}

# Which role acts at which level.
LEVEL_ROLE: dict[VerificationLevel, Role] = {
    VerificationLevel.CL_CH: Role.CL_CH,
    VerificationLevel.OM: Role.OM,
}

# Where each level's verifier finds their queue in the UI (used in notification links).
LEVEL_QUEUE_LINK: dict[VerificationLevel, str] = {
    VerificationLevel.CL_CH: "/verification/pending",
    VerificationLevel.OM: "/om/final-verification",
}


class TimingStatus(StrEnum):
    """Professor's classroom entry against the scheduled start, judged by the configured tolerance."""
    ON_TIME = "ON_TIME"
    DELAYED = "DELAYED"


class DelayReason(StrEnum):
    PREVIOUS_CLASS_OVERRUN = "PREVIOUS_CLASS_OVERRUN"
    PROFESSOR_ARRIVED_LATE = "PROFESSOR_ARRIVED_LATE"
    DEPARTMENTAL_MEETING = "DEPARTMENTAL_MEETING"
    ADMINISTRATIVE_WORK = "ADMINISTRATIVE_WORK"
    TECHNICAL_ISSUE = "TECHNICAL_ISSUE"
    ROOM_ISSUE = "ROOM_ISSUE"
    EMERGENCY = "EMERGENCY"
    OTHER = "OTHER"


class ClassState(StrEnum):
    """Derived, never stored: where a scheduled class stands right now."""
    YET_TO_START = "YET_TO_START"    # scheduled start is still ahead
    ENTRY_DUE = "ENTRY_DUE"          # inside the scheduled slot, entry not recorded
    IN_CLASS = "IN_CLASS"            # entry recorded, exit not yet
    EXIT_MISSING = "EXIT_MISSING"    # entry recorded on an earlier day, exit never recorded
    COMPLETED = "COMPLETED"          # entry and exit recorded
    NOT_RECORDED = "NOT_RECORDED"    # slot is over and no entry was recorded


class ImportMode(StrEnum):
    FULL_TABLE = "FULL_TABLE"
    COLUMN_WISE = "COLUMN_WISE"
    EXCEL = "EXCEL"
    CSV = "CSV"


class ImportStatus(StrEnum):
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    READY = "READY"
    IMPORTED = "IMPORTED"
    FAILED = "FAILED"


class MappingStatus(StrEnum):
    MAPPED = "MAPPED"
    SUGGESTED = "SUGGESTED"  # high-confidence fuzzy match, awaiting admin confirmation
    NEEDS_REVIEW = "NEEDS_REVIEW"
    IGNORED = "IGNORED"


class MappingMethod(StrEnum):
    EXACT = "EXACT"
    ALIAS = "ALIAS"
    FUZZY = "FUZZY"
    MANUAL = "MANUAL"
    EXECUTION_COLUMN = "EXECUTION_COLUMN"  # spreadsheet execution columns are captured in-portal instead
    NONE = "NONE"


class RowValidation(StrEnum):
    VALID = "VALID"
    WARNING = "WARNING"
    ERROR = "ERROR"
    EMPTY = "EMPTY"


class MaterialType(StrEnum):
    LECTURE_NOTES = "LECTURE_NOTES"
    ATTACHMENT = "ATTACHMENT"
    CLASS_EVIDENCE = "CLASS_EVIDENCE"  # optional classroom / board / activity photo
    CHECKIN_IMAGE = "CHECKIN_IMAGE"    # optional photo attached when the professor starts the class


class LectureOrigin(StrEnum):
    MASTER = "MASTER"                # part of the semester master plan
    SPRINT_ADDED = "SPRINT_ADDED"    # replacement lecture added in a weekly sprint revision
    CARRY_FORWARD = "CARRY_FORWARD"  # remaining topic of an earlier lecture, placed by the admin


class SprintPlanStatus(StrEnum):
    DRAFT = "DRAFT"        # being set up: dates, subjects, curriculum
    ACTIVE = "ACTIVE"      # semester sprint generated; weeks are published one by one
    ARCHIVED = "ARCHIVED"  # kept for the record, no longer scheduled


class RevisionStatus(StrEnum):
    DRAFT = "DRAFT"          # sprint meeting in progress - never visible to professors
    PUBLISHED = "PUBLISHED"
    DISCARDED = "DISCARDED"


class ChangeType(StrEnum):
    UPDATE = "UPDATE"
    CANCEL = "CANCEL"
    ADD = "ADD"


class ChangeReason(StrEnum):
    SPRINT_MEETING_DECISION = "SPRINT_MEETING_DECISION"
    FACULTY_AVAILABILITY = "FACULTY_AVAILABILITY"
    PREVIOUS_TOPIC_INCOMPLETE = "PREVIOUS_TOPIC_INCOMPLETE"
    HOLIDAY_ADJUSTMENT = "HOLIDAY_ADJUSTMENT"
    ROOM_CHANGE = "ROOM_CHANGE"
    LAB_AVAILABILITY = "LAB_AVAILABILITY"
    ACADEMIC_REQUIREMENT = "ACADEMIC_REQUIREMENT"
    OTHER = "OTHER"


class CarryForwardStatus(StrEnum):
    OPEN = "OPEN"            # derived: remaining work nobody has decided on yet
    DEFERRED = "DEFERRED"    # admin chose "reschedule later"; shows again next meeting
    SCHEDULED = "SCHEDULED"  # placed into a published week
    RESOLVED = "RESOLVED"    # admin marked it as needing no further class time


class SlotType(StrEnum):
    """A period inside a timing template. Lunch / break belong to the template (a year group), never to the whole college."""
    LECTURE = "LECTURE"
    LUNCH = "LUNCH"
    BREAK = "BREAK"


class ClassType(StrEnum):
    """What a recurring timetable entry is. A LAB normally spans two consecutive lecture slots."""
    THEORY = "THEORY"
    LAB = "LAB"
    TUTORIAL = "TUTORIAL"
    REMEDIAL = "REMEDIAL"


class RoomType(StrEnum):
    CLASSROOM = "CLASSROOM"
    LAB = "LAB"


class TimetableStatus(StrEnum):
    DRAFT = "DRAFT"          # being generated / edited - invisible to everyone but the admin
    PUBLISHED = "PUBLISHED"  # the institution's current recurring timetable
    ARCHIVED = "ARCHIVED"    # an earlier published version, kept for history


class NotificationChannel(StrEnum):
    IN_APP = "IN_APP"
    EMAIL = "EMAIL"
    PUSH = "PUSH"
    WHATSAPP = "WHATSAPP"


def sql_in(enum_cls) -> str:
    """Render an enum as the body of a SQL `IN (...)` list for CHECK constraints."""
    return ", ".join(f"'{m.value}'" for m in enum_cls)
