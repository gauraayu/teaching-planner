"""Admin operations dashboard assembled from the report primitives."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import ImportStatus, VerificationStatus
from app.models import AuditLog, ImportSession, TeachingPlan, Verification
from app.services import report_service
from app.services import serializers as ser


def admin_dashboard(db: Session, **filters) -> dict:
    items = report_service.facts(db, **filters)
    summary = report_service.summarize(items)
    recent_imports = db.scalars(select(ImportSession).where(ImportSession.status == ImportStatus.IMPORTED)
                                .order_by(ImportSession.committed_at.desc()).limit(5)).all()
    drafts = db.scalars(select(ImportSession).where(ImportSession.status.in_(
        (ImportStatus.DRAFT, ImportStatus.READY, ImportStatus.FAILED, ImportStatus.VALIDATING)))
        .order_by(ImportSession.updated_at.desc()).limit(5)).all()
    pending_by_level = dict(db.execute(select(Verification.verification_level, func.count(Verification.id))
                                       .where(Verification.status == VerificationStatus.PENDING)
                                       .group_by(Verification.verification_level)).all())
    activity = db.scalars(select(AuditLog).where(AuditLog.action.notin_(("auth.demo_login", "auth.login")))
                          .order_by(AuditLog.created_at.desc()).limit(12)).all()
    return {
        "metrics": {
            "active_subjects": len({f.subject_id for f in items}),
            "active_plans": len({f.plan_id for f in items}),
            "total_lectures": summary["total"], "completed": summary["completed"], "partial": summary["partial"],
            "pending": summary["pending"], "delayed": summary["delayed"],
            "verification_pending": sum(pending_by_level.values()),
            "verification_pending_by_level": pending_by_level,
            "execution_pct": summary["execution_pct"], "verified_pct": summary["verified_pct"], "on_time_pct": summary["on_time_pct"],
        },
        "definitions": report_service.METRIC_DEFINITIONS,
        "subject_progress": report_service.subject_progress(items),
        "upcoming": report_service.lecture_list(items, "upcoming")[:8],
        "delayed": sorted(report_service.lecture_list(items, "delayed"), key=lambda r: -(r["delay_days"] or 0))[:8],
        "recent_activity": [ser.audit_entry(a) for a in activity],
        "recent_imports": [ser.import_session(s, include_draft=False) for s in recent_imports],
        "draft_imports": [ser.import_session(s, include_draft=False) for s in drafts],
        "plan_status_counts": dict(db.execute(select(TeachingPlan.status, func.count(TeachingPlan.id))
                                              .group_by(TeachingPlan.status)).all()),
    }
