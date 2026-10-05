import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require
from app.core.enums import Role
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import User
from app.schemas import requests as rq
from app.services import academic_service as svc
from app.services import serializers as ser

router = APIRouter(tags=["academic"])
READ = Depends(require(Permission.ACADEMIC_READ))
MANAGE = require(Permission.ACADEMIC_MANAGE)


def _items(rows, fn):
    return {"items": [fn(r) for r in rows], "total": len(rows)}


@router.get("/academic-years", dependencies=[READ])
def academic_years(db: Session = Depends(get_db)):
    return _items(svc.list_years(db), ser.academic_year)


@router.post("/academic-years", status_code=201)
def create_year(body: rq.AcademicYearIn, db: Session = Depends(get_db), user: User = Depends(MANAGE)):
    return ser.academic_year(svc.save_year(db, user, body))


@router.put("/academic-years/{year_id}")
def update_year(year_id: uuid.UUID, body: rq.AcademicYearIn, db: Session = Depends(get_db), user: User = Depends(MANAGE)):
    return ser.academic_year(svc.save_year(db, user, body, year_id))


@router.get("/semesters", dependencies=[READ])
def semesters(academic_year_id: uuid.UUID | None = None, db: Session = Depends(get_db)):
    return _items(svc.list_semesters(db, academic_year_id), ser.semester)


@router.post("/semesters", status_code=201)
def create_semester(body: rq.SemesterIn, db: Session = Depends(get_db), user: User = Depends(MANAGE)):
    return ser.semester(svc.save_semester(db, user, body))


@router.put("/semesters/{semester_id}")
def update_semester(semester_id: uuid.UUID, body: rq.SemesterIn, db: Session = Depends(get_db), user: User = Depends(MANAGE)):
    return ser.semester(svc.save_semester(db, user, body, semester_id))


@router.get("/departments", dependencies=[READ])
def departments(db: Session = Depends(get_db)):
    return _items(svc.list_departments(db), ser.department)


@router.post("/departments", status_code=201)
def create_department(body: rq.DepartmentIn, db: Session = Depends(get_db), user: User = Depends(MANAGE)):
    return ser.department(svc.save_department(db, user, body))


@router.put("/departments/{dept_id}")
def update_department(dept_id: uuid.UUID, body: rq.DepartmentIn, db: Session = Depends(get_db), user: User = Depends(MANAGE)):
    return ser.department(svc.save_department(db, user, body, dept_id))


@router.get("/branches", dependencies=[READ])
def branches(department_id: uuid.UUID | None = None, db: Session = Depends(get_db)):
    return _items(svc.list_branches(db, department_id), ser.branch)


@router.post("/branches", status_code=201)
def create_branch(body: rq.BranchIn, db: Session = Depends(get_db), user: User = Depends(MANAGE)):
    return ser.branch(svc.save_branch(db, user, body))


@router.put("/branches/{branch_id}")
def update_branch(branch_id: uuid.UUID, body: rq.BranchIn, db: Session = Depends(get_db), user: User = Depends(MANAGE)):
    return ser.branch(svc.save_branch(db, user, body, branch_id))


@router.get("/sections", dependencies=[READ])
def sections(semester_id: uuid.UUID | None = None, branch_id: uuid.UUID | None = None, db: Session = Depends(get_db)):
    return _items(svc.list_sections(db, semester_id=semester_id, branch_id=branch_id), ser.section)


@router.post("/sections", status_code=201)
def create_section(body: rq.SectionIn, db: Session = Depends(get_db), user: User = Depends(MANAGE)):
    return ser.section(svc.save_section(db, user, body))


@router.put("/sections/{section_id}")
def update_section(section_id: uuid.UUID, body: rq.SectionIn, db: Session = Depends(get_db), user: User = Depends(MANAGE)):
    return ser.section(svc.save_section(db, user, body, section_id))


@router.get("/subjects", dependencies=[READ])
def subjects(branch_id: uuid.UUID | None = None, semester_number: int | None = None, q: str | None = None,
             db: Session = Depends(get_db)):
    return _items(svc.list_subjects(db, branch_id=branch_id, semester_number=semester_number, q=q), ser.subject)


@router.post("/subjects", status_code=201)
def create_subject(body: rq.SubjectIn, db: Session = Depends(get_db), user: User = Depends(MANAGE)):
    return ser.subject(svc.save_subject(db, user, body))


@router.put("/subjects/{subject_id}")
def update_subject(subject_id: uuid.UUID, body: rq.SubjectIn, db: Session = Depends(get_db), user: User = Depends(MANAGE)):
    return ser.subject(svc.save_subject(db, user, body, subject_id))


# Directory for filters: names and roles only (no email / employee ID). Full records live under /admin/users.
@router.get("/users", dependencies=[Depends(require(Permission.USERS_READ, Permission.PLANS_MANAGE, Permission.VERIFICATION_READ,
                                                    Permission.REPORTS_READ, any_of=True))])
def users(role: Role | None = None, db: Session = Depends(get_db)):
    return _items(svc.list_users(db, role), ser.user_brief)


@router.get("/faculty-assignments", dependencies=[Depends(require(Permission.PLANS_MANAGE))])
def faculty_assignments(semester_id: uuid.UUID | None = None, professor_id: uuid.UUID | None = None, db: Session = Depends(get_db)):
    return _items(svc.list_assignments(db, semester_id=semester_id, professor_id=professor_id), ser.faculty_assignment)


@router.post("/faculty-assignments", status_code=201)
def create_faculty_assignment(body: rq.FacultyAssignmentIn, db: Session = Depends(get_db), user: User = Depends(MANAGE)):
    return ser.faculty_assignment(svc.create_assignment(db, user, body))
