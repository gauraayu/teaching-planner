"""Academic structure: years, semesters, departments, branches, sections, subjects, faculty mapping."""
import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.enums import Role
from app.core.errors import BusinessRuleViolation, Conflict, NotFound
from app.models import (
    AcademicYear, Branch, Department, FacultySubjectAssignment, RoleModel, Section, Semester, Subject, User,
)
from app.schemas import requests as rq
from app.services import audit_service

ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]


def _get(db: Session, model, id_: uuid.UUID, label: str):
    obj = db.get(model, id_)
    if not obj:
        raise NotFound(f"{label} not found.")
    return obj


def _exists(db: Session, stmt, message: str) -> None:
    if db.scalar(stmt) is not None:
        raise Conflict(message, code="DUPLICATE")


# ---------------------------------------------------------------- academic years

def list_years(db: Session):
    return list(db.scalars(select(AcademicYear).order_by(AcademicYear.start_date.desc())))


def save_year(db: Session, actor: User, data: rq.AcademicYearIn, year_id: uuid.UUID | None = None) -> AcademicYear:
    if data.end_date <= data.start_date:
        raise BusinessRuleViolation("The academic year must end after it starts.")
    year = _get(db, AcademicYear, year_id, "Academic year") if year_id else AcademicYear()
    _exists(db, select(AcademicYear.id).where(AcademicYear.name == data.name, AcademicYear.id != year.id if year_id else True),
            f"Academic year {data.name} already exists.")
    if data.is_current:
        db.execute(update(AcademicYear).values(is_current=False))
    for k, v in data.model_dump().items():
        setattr(year, k, v)
    db.add(year)
    db.flush()
    audit_service.record(db, actor=actor, action="academic_year.saved", entity_type="academic_year", entity_id=year.id,
                         summary=f"Saved academic year {year.name}.", new=data.model_dump())
    db.commit()
    return year


# ---------------------------------------------------------------- semesters

def list_semesters(db: Session, academic_year_id: uuid.UUID | None = None):
    stmt = select(Semester).join(AcademicYear).order_by(AcademicYear.start_date.desc(), Semester.number)
    if academic_year_id:
        stmt = stmt.where(Semester.academic_year_id == academic_year_id)
    return list(db.scalars(stmt))


def save_semester(db: Session, actor: User, data: rq.SemesterIn, semester_id: uuid.UUID | None = None) -> Semester:
    year = _get(db, AcademicYear, data.academic_year_id, "Academic year")
    if data.end_date <= data.start_date:
        raise BusinessRuleViolation("The semester must end after it starts.")
    if data.start_date < year.start_date or data.end_date > year.end_date:
        raise BusinessRuleViolation(f"Semester dates must fall within academic year {year.name}.")
    sem = _get(db, Semester, semester_id, "Semester") if semester_id else Semester()
    _exists(db, select(Semester.id).where(Semester.academic_year_id == year.id, Semester.number == data.number,
                                          Semester.id != sem.id if semester_id else True),
            f"Semester {ROMAN[data.number]} already exists in {year.name}.")
    if data.is_current:
        db.execute(update(Semester).values(is_current=False))
    values = data.model_dump()
    values["name"] = values.get("name") or f"Semester {ROMAN[data.number]}"
    for k, v in values.items():
        setattr(sem, k, v)
    db.add(sem)
    db.flush()
    audit_service.record(db, actor=actor, action="semester.saved", entity_type="semester", entity_id=sem.id,
                         summary=f"Saved {sem.name} ({year.name}).", new=values)
    db.commit()
    return sem


# ---------------------------------------------------------------- departments / branches

def list_departments(db: Session):
    return list(db.scalars(select(Department).order_by(Department.name)))


def save_department(db: Session, actor: User, data: rq.DepartmentIn, dept_id: uuid.UUID | None = None) -> Department:
    dept = _get(db, Department, dept_id, "Department") if dept_id else Department()
    _exists(db, select(Department.id).where((Department.code == data.code) | (Department.name == data.name),
                                            Department.id != dept.id if dept_id else True),
            "A department with this code or name already exists.")
    dept.code, dept.name = data.code.upper(), data.name
    db.add(dept)
    db.flush()
    audit_service.record(db, actor=actor, action="department.saved", entity_type="department", entity_id=dept.id,
                         summary=f"Saved department {dept.name}.", new=data.model_dump())
    db.commit()
    return dept


def list_branches(db: Session, department_id: uuid.UUID | None = None):
    stmt = select(Branch).order_by(Branch.name)
    if department_id:
        stmt = stmt.where(Branch.department_id == department_id)
    return list(db.scalars(stmt))


def save_branch(db: Session, actor: User, data: rq.BranchIn, branch_id: uuid.UUID | None = None) -> Branch:
    _get(db, Department, data.department_id, "Department")
    br = _get(db, Branch, branch_id, "Branch") if branch_id else Branch()
    _exists(db, select(Branch.id).where(Branch.department_id == data.department_id, Branch.code == data.code.upper(),
                                        Branch.id != br.id if branch_id else True),
            "A branch with this code already exists in the department.")
    br.department_id, br.code, br.name = data.department_id, data.code.upper(), data.name
    db.add(br)
    db.flush()
    audit_service.record(db, actor=actor, action="branch.saved", entity_type="branch", entity_id=br.id,
                         summary=f"Saved branch {br.name}.", new=data.model_dump())
    db.commit()
    return br


# ---------------------------------------------------------------- sections

def list_sections(db: Session, *, semester_id: uuid.UUID | None = None, branch_id: uuid.UUID | None = None):
    stmt = select(Section).order_by(Section.name)
    if semester_id:
        stmt = stmt.where(Section.semester_id == semester_id)
    if branch_id:
        stmt = stmt.where(Section.branch_id == branch_id)
    return list(db.scalars(stmt))


def save_section(db: Session, actor: User, data: rq.SectionIn, section_id: uuid.UUID | None = None) -> Section:
    _get(db, Branch, data.branch_id, "Branch")
    _get(db, Semester, data.semester_id, "Semester")
    sec = _get(db, Section, section_id, "Section") if section_id else Section()
    name = data.name.upper()
    _exists(db, select(Section.id).where(Section.branch_id == data.branch_id, Section.semester_id == data.semester_id,
                                         Section.name == name, Section.id != sec.id if section_id else True),
            f"Section {name} already exists for this branch and semester.")
    sec.branch_id, sec.semester_id, sec.name, sec.student_count = data.branch_id, data.semester_id, name, data.student_count
    db.add(sec)
    db.flush()
    audit_service.record(db, actor=actor, action="section.saved", entity_type="section", entity_id=sec.id,
                         summary=f"Saved section {name}.", new=data.model_dump())
    db.commit()
    return sec


# ---------------------------------------------------------------- subjects

def list_subjects(db: Session, *, branch_id: uuid.UUID | None = None, semester_number: int | None = None, q: str | None = None):
    stmt = select(Subject).order_by(Subject.semester_number, Subject.code)
    if branch_id:
        stmt = stmt.where(Subject.branch_id == branch_id)
    if semester_number:
        stmt = stmt.where(Subject.semester_number == semester_number)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where((Subject.name.ilike(like)) | (Subject.code.ilike(like)))
    return list(db.scalars(stmt))


def save_subject(db: Session, actor: User, data: rq.SubjectIn, subject_id: uuid.UUID | None = None) -> Subject:
    _get(db, Branch, data.branch_id, "Branch")
    sub = _get(db, Subject, subject_id, "Subject") if subject_id else Subject()
    code = data.code.upper()
    _exists(db, select(Subject.id).where(Subject.code == code, Subject.id != sub.id if subject_id else True),
            f"Subject code {code} already exists.")
    values = data.model_dump() | {"code": code}
    old = {k: getattr(sub, k, None) for k in values} if subject_id else None
    for k, v in values.items():
        setattr(sub, k, v)
    db.add(sub)
    db.flush()
    audit_service.record(db, actor=actor, action="subject.saved", entity_type="subject", entity_id=sub.id,
                         summary=f"Saved subject {code} {sub.name}.", old=old, new=values)
    db.commit()
    return sub


# ---------------------------------------------------------------- users & faculty mapping

def list_users(db: Session, role: Role | None = None):
    stmt = select(User).join(RoleModel).order_by(RoleModel.code, User.full_name)
    if role:
        stmt = stmt.where(RoleModel.code == role.value)
    return list(db.scalars(stmt))


def list_assignments(db: Session, *, semester_id: uuid.UUID | None = None, professor_id: uuid.UUID | None = None):
    stmt = select(FacultySubjectAssignment)
    if semester_id:
        stmt = stmt.where(FacultySubjectAssignment.semester_id == semester_id)
    if professor_id:
        stmt = stmt.where(FacultySubjectAssignment.professor_id == professor_id)
    return list(db.scalars(stmt))


def create_assignment(db: Session, actor: User, data: rq.FacultyAssignmentIn) -> FacultySubjectAssignment:
    prof = _get(db, User, data.professor_id, "Professor")
    if prof.role_code != Role.PROFESSOR:
        raise BusinessRuleViolation(f"{prof.full_name} is not a professor.", code="INVALID_FACULTY")
    subject = _get(db, Subject, data.subject_id, "Subject")
    section = _get(db, Section, data.section_id, "Section")
    if subject.branch_id != section.branch_id:
        raise BusinessRuleViolation("The subject is not offered to this section's branch.", code="INVALID_ASSIGNMENT")
    _exists(db, select(FacultySubjectAssignment.id).where(
        FacultySubjectAssignment.professor_id == prof.id, FacultySubjectAssignment.subject_id == subject.id,
        FacultySubjectAssignment.section_id == section.id), "This professor is already mapped to the subject and section.")
    a = FacultySubjectAssignment(professor_id=prof.id, subject_id=subject.id, section_id=section.id, semester_id=section.semester_id)
    db.add(a)
    db.flush()
    audit_service.record(db, actor=actor, action="faculty.assigned", entity_type="faculty_assignment", entity_id=a.id,
                         summary=f"Mapped {prof.full_name} to {subject.code} Section {section.name}.")
    db.commit()
    return a
