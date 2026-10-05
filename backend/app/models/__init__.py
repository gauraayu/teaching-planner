"""Import every model so Base.metadata is complete (the store and the tests rely on this)."""
from app.models.academic import (  # noqa: F401
    AcademicYear, Branch, Department, FacultySubjectAssignment, Section, Semester, Subject,
)
from app.models.audit import AuditLog, Notification  # noqa: F401
from app.models.import_session import ImportSession  # noqa: F401
from app.models.operations import ClassSession  # noqa: F401
from app.models.progress import (  # noqa: F401
    Assignment, LectureMaterial, LectureProgress, LectureSubtopicProgress,
)
from app.models.sprint import CarryForwardItem, SemesterSprintPlan, SprintRevision, SprintRevisionItem  # noqa: F401
from app.models.teaching_plan import Lecture, LectureSchedule, LectureSubtopic, TeachingPlan  # noqa: F401
from app.models.timetable import Holiday, Room, TimetableEntry, TimetableVersion, TimingSlot, TimingTemplate  # noqa: F401
from app.models.user import RoleModel, User, UserScope  # noqa: F401
from app.models.verification import Verification  # noqa: F401
