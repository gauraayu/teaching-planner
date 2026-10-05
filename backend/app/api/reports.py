import uuid
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import AuditLog, User
from app.services import dashboard_service, notification_service, report_service
from app.services import serializers as ser
from app.services import verification_service

router = APIRouter(tags=["reports"])
READER = require(Permission.REPORTS_READ)


def _filters(academic_year_id: uuid.UUID | None = None, semester_id: uuid.UUID | None = None, branch_id: uuid.UUID | None = None,
             section_id: uuid.UUID | None = None, subject_id: uuid.UUID | None = None, professor_id: uuid.UUID | None = None,
             unit_no: int | None = None, date_from: date | None = None, date_to: date | None = None) -> dict:
    return {k: v for k, v in locals().items() if v is not None}


@router.get("/admin/dashboard", dependencies=[Depends(require(Permission.PLANS_MANAGE))])
def admin_dashboard(filters: dict = Depends(_filters), db: Session = Depends(get_db)):
    """Institution-wide numbers: administrators only."""
    return dashboard_service.admin_dashboard(db, **filters)


@router.get("/reports/progress")
def progress(filters: dict = Depends(_filters), status: str | None = None, db: Session = Depends(get_db), user: User = Depends(READER)):
    """CL/CH and OM accounts get the report for their own scope; administrators for everything."""
    items = report_service.facts(db, **filters, viewer=user)
    if status:
        wanted = set(status.split(","))
        items = [f for f in items if f.bucket in wanted or f.execution_status in wanted]
    return {
        "summary": report_service.summarize(items),
        "definitions": report_service.METRIC_DEFINITIONS,
        "subjects": report_service.subject_progress(items),
        "faculty": report_service.faculty_progress(items),
        "units": report_service.unit_progress(items) if filters.get("subject_id") or filters.get("section_id") else [],
        "adherence": report_service.schedule_adherence(items),
    }


@router.get("/reports/lectures/{kind}")
def lectures(kind: str, filters: dict = Depends(_filters), db: Session = Depends(get_db), user: User = Depends(READER)):
    """kind: delayed | pending | planned_vs_actual | completion | upcoming"""
    items = report_service.lecture_list(report_service.facts(db, **filters, viewer=user), kind)
    return {"items": items, "total": len(items)}


@router.get("/reports/verification/{view}")
def verification_report(view: str, db: Session = Depends(get_db), user: User = Depends(READER)):
    """view: pending | corrections - across all levels, inside the caller's scope."""
    from app.core.enums import VerificationStatus
    from app.models import Lecture, LectureProgress, TeachingPlan, Verification
    from app.services import scope_service

    status = VerificationStatus.PENDING if view == "pending" else VerificationStatus.CORRECTION_REQUIRED
    rows = db.scalars(select(Verification).join(LectureProgress, Verification.lecture_progress_id == LectureProgress.id)
                      .join(Lecture, LectureProgress.lecture_id == Lecture.id).join(TeachingPlan, Lecture.teaching_plan_id == TeachingPlan.id)
                      .where(Verification.status == status, *scope_service.plan_filter(user))
                      .order_by(Verification.created_at.desc()).limit(300)).unique().all()
    items = [verification_service._queue_row(v) for v in rows]
    return {"items": items, "total": len(items)}


@router.get("/audit", dependencies=[Depends(require(Permission.AUDIT_READ))])
def audit(entity_type: str | None = None, limit: int = 100, db: Session = Depends(get_db)):
    """The institution-wide audit trail (who did what, including account changes): administrators only."""
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500))
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    items = [ser.audit_entry(a) for a in db.scalars(stmt)]
    return {"items": items, "total": len(items)}


@router.get("/notifications")
def notifications(db: Session = Depends(get_db), user: User = Depends(current_user)):
    items, unread = notification_service.list_for_user(db, user.id)
    return {"items": [ser.notification(n) for n in items], "unread": unread}


@router.post("/notifications/read")
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(current_user)):
    notification_service.mark_read(db, user.id)
    return {"ok": True}


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    notification_service.mark_read(db, user.id, notification_id)
    return {"ok": True}
