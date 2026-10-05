"""Professor -> CL/CH -> OM verification chain.

One shared workflow; the verifier's role decides the level they act on, and their scope
(user_scopes) decides which professors' submissions they see. Both come from the signed-in
account - the client never sends a role or a level.
"""
from __future__ import annotations

import uuid
from datetime import datetime, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.core.enums import (
    LEVEL_LABELS, LEVEL_QUEUE_LINK, LEVEL_ROLE, ROLE_LABELS, VERIFICATION_CHAIN, SubmissionStatus, VerificationLevel, VerificationStatus,
)
from app.core.errors import Conflict, NotFound, PermissionDenied
from app.models import Lecture, LectureProgress, TeachingPlan, User, Verification
from app.schemas import requests as rq
from app.services import audit_service, notification_service, operations_service, scope_service
from app.services import serializers as ser
from app.services.professor_service import lecture_detail

ROLE_LEVEL = {role: level for level, role in LEVEL_ROLE.items()}


def level_for(user: User) -> VerificationLevel | None:
    return ROLE_LEVEL.get(user.role_code)


def _queue_row(v: Verification) -> dict:
    pr: LectureProgress = v.progress
    lec: Lecture = pr.lecture
    plan: TeachingPlan = lec.teaching_plan
    prior = [p for p in pr.verifications if p.round == v.round and p.id != v.id and p.status == VerificationStatus.VERIFIED]
    return {
        "id": str(v.id), "level": v.verification_level, "level_label": LEVEL_LABELS.get(v.verification_level, v.verification_level),
        "status": v.status, "round": v.round,
        "professor": ser.user_brief(pr.professor),
        "subject": {"code": plan.subject.code, "name": plan.subject.name, "short_name": plan.subject.short_name},
        "plan_id": str(plan.id), "section": plan.section.name, "semester": plan.semester.name,
        "lecture_id": str(lec.id), "lecture_no": lec.lecture_no, "topic": lec.content_topic, "unit_no": lec.unit_no,
        "semester_number": plan.semester.number,
        "planned_date": ser._iso(lec.schedule.planned_date) if lec.schedule else None,
        "class_session": operations_service.session_brief(lec.class_session),
        "actual_date": ser._iso(pr.actual_completion_date), "execution_status": pr.execution_status,
        "submission_status": pr.submission_status, "submitted_at": ser._iso(pr.submitted_at),
        "is_resubmission": pr.submission_count > 1 and v.round == pr.submission_count,
        "prior_verifications": [ser.verification(p) for p in prior],
        "verifier": ser.user_brief(v.verifier), "remarks": v.remarks, "verified_at": ser._iso(v.verified_at),
        "created_at": ser._iso(v.created_at),
    }


def queue(db: Session, user: User, *, view: str = "pending", professor_id=None, subject_id=None, section_id=None,
          semester_id=None, date_from=None, date_to=None, q: str | None = None, limit: int = 200) -> list[dict]:
    """view: pending (my level), verified (by my level), corrections (raised at my level), all (admin overview)."""
    level = level_for(user)
    stmt = (select(Verification).join(LectureProgress, Verification.lecture_progress_id == LectureProgress.id)
            .join(Lecture, LectureProgress.lecture_id == Lecture.id)
            .join(TeachingPlan, Lecture.teaching_plan_id == TeachingPlan.id)
            .where(*scope_service.plan_filter(user)))
    if view == "pending":
        stmt = stmt.where(Verification.status == VerificationStatus.PENDING)
        if level:
            stmt = stmt.where(Verification.verification_level == level)
        stmt = stmt.order_by(LectureProgress.submitted_at)
    elif view == "verified":
        stmt = stmt.where(Verification.status == VerificationStatus.VERIFIED)
        if level:
            stmt = stmt.where(Verification.verification_level == level)
        stmt = stmt.order_by(Verification.verified_at.desc())
    elif view == "corrections":
        stmt = stmt.where(Verification.status == VerificationStatus.CORRECTION_REQUIRED)
        if level:
            stmt = stmt.where(Verification.verification_level == level)
        stmt = stmt.order_by(Verification.verified_at.desc())
    elif view == "all":
        stmt = stmt.order_by(Verification.created_at.desc())
    else:
        raise NotFound("Unknown queue.")
    for col, val in ((LectureProgress.professor_id, professor_id), (TeachingPlan.subject_id, subject_id),
                     (TeachingPlan.section_id, section_id), (TeachingPlan.semester_id, semester_id)):
        if val:
            stmt = stmt.where(col == val)
    if date_from:
        stmt = stmt.where(LectureProgress.actual_completion_date >= date_from)
    if date_to:
        stmt = stmt.where(LectureProgress.actual_completion_date <= date_to)
    rows = [_queue_row(v) for v in db.scalars(stmt.limit(limit)).unique().all()]
    if q:
        needle = q.lower()
        rows = [r for r in rows if needle in f"{r['topic']} {r['professor']['full_name']} {r['subject']['code']} {r['subject']['name']} {r['lecture_no']}".lower()]
    return rows


def metrics(db: Session, user: User) -> dict:
    level = level_for(user)

    scope = scope_service.plan_filter(user)

    def scoped(stmt):
        if not scope:
            return stmt
        return (stmt.join(Lecture, LectureProgress.lecture_id == Lecture.id)
                .join(TeachingPlan, Lecture.teaching_plan_id == TeachingPlan.id).where(*scope))

    def count(*conds) -> int:
        stmt = scoped(select(func.count(Verification.id)).join(LectureProgress, Verification.lecture_progress_id == LectureProgress.id)
                      .where(*conds))
        if level:
            stmt = stmt.where(Verification.verification_level == level)
        return db.scalar(stmt) or 0

    start = datetime.combine(clock.today(), time.min, tzinfo=get_settings().tz)
    todays = db.scalar(scoped(select(func.count(LectureProgress.id)).where(LectureProgress.submitted_at >= start))) or 0
    return {
        "level": level.value if level else None,
        "level_label": LEVEL_LABELS[level.value] if level else None,
        "scope": scope_service.describe(db, user),
        "pending": count(Verification.status == VerificationStatus.PENDING),
        "verified": count(Verification.status == VerificationStatus.VERIFIED),
        "correction_required": count(Verification.status == VerificationStatus.CORRECTION_REQUIRED),
        "todays_submissions": todays,
        "final_verified": db.scalar(scoped(select(func.count(LectureProgress.id))
                                           .where(LectureProgress.submission_status == SubmissionStatus.FINAL_VERIFIED))) or 0,
    }


def detail(db: Session, user: User, verification_id: uuid.UUID) -> dict:
    v = db.get(Verification, verification_id)
    if not v:
        raise NotFound("Verification record not found.")
    level = level_for(user)
    pr = v.progress
    scope_service.require(user, pr.lecture.teaching_plan, "This submission")
    lecture = lecture_detail(db, user, pr.lecture_id)
    return {
        "verification": _queue_row(v),
        "lecture": lecture,
        "history": [ser.verification(x) for x in pr.verifications],
        "can_act": bool(level and v.status == VerificationStatus.PENDING and v.verification_level == level),
        "acting_level": level.value if level else None,
        # Why the signed-in user cannot act, in words the page can show as-is.
        "waiting_for": _waiting_for(v, level),
    }


def _waiting_for(v: Verification, level: VerificationLevel | None) -> str | None:
    if not level or v.status != VerificationStatus.PENDING or v.verification_level == level:
        return None
    if v.verification_level in VERIFICATION_CHAIN and VERIFICATION_CHAIN.index(VerificationLevel(v.verification_level)) < VERIFICATION_CHAIN.index(level):
        return f"Waiting for {LEVEL_LABELS[v.verification_level]} academic verification."
    return None


def _lock_pending(db: Session, user: User, verification_id: uuid.UUID) -> Verification:
    level = level_for(user)
    if not level:
        raise PermissionDenied("Only CL/CH and OM accounts can verify submissions.")
    v = db.scalar(select(Verification).where(Verification.id == verification_id).with_for_update(of=Verification))
    if not v:
        raise NotFound("Verification record not found.")
    scope_service.require(user, v.progress.lecture.teaching_plan, "This submission")
    if v.verification_level != level:
        step, mine = LEVEL_LABELS.get(v.verification_level, v.verification_level), LEVEL_LABELS[level.value]
        waiting = v.verification_level in VERIFICATION_CHAIN and \
            VERIFICATION_CHAIN.index(level) > VERIFICATION_CHAIN.index(VerificationLevel(v.verification_level))
        raise PermissionDenied(
            f"This step is for {step}. "
            + (f"{mine} verification opens after {step} has verified it." if waiting else f"It has moved past the {mine} stage."),
            code="WRONG_VERIFICATION_LEVEL",
        )
    if v.status != VerificationStatus.PENDING:
        raise Conflict(f"This step is already {v.status.replace('_', ' ').lower()}.", code="VERIFICATION_CLOSED")
    return v


def verify(db: Session, user: User, verification_id: uuid.UUID, data: rq.VerifyRequest) -> dict:
    v = _lock_pending(db, user, verification_id)
    pr: LectureProgress = v.progress
    lec = pr.lecture
    plan = lec.teaching_plan
    now = clock.now_utc()
    v.status, v.verifier_id, v.verifier_role, v.remarks, v.verified_at = (
        VerificationStatus.VERIFIED, user.id, user.role_code.value, data.remarks, now)

    idx = VERIFICATION_CHAIN.index(VerificationLevel(v.verification_level))
    is_final = idx == len(VERIFICATION_CHAIN) - 1
    who = ROLE_LABELS[user.role_code.value]
    subject = plan.subject.short_name or plan.subject.code
    if is_final:
        pr.submission_status = SubmissionStatus.FINAL_VERIFIED
        pr.final_verified_at = now
        notification_service.notify(db, pr.professor_id, kind="verification.final",
                                    title=f"Lecture {lec.lecture_no} final verified",
                                    body=f"{subject}: “{lec.content_topic}” was final verified by {who}.",
                                    link=f"/professor/lectures/{lec.id}")
    else:
        nxt = VERIFICATION_CHAIN[idx + 1]
        db.add(Verification(lecture_progress_id=pr.id, round=v.round, verification_level=nxt, status=VerificationStatus.PENDING))
        notification_service.notify(db, pr.professor_id, kind="verification.verified",
                                    title=f"Lecture {lec.lecture_no} verified by {who}",
                                    body=f"Your lecture record for {subject} “{lec.content_topic}” has been verified by {who}.",
                                    link=f"/professor/lectures/{lec.id}")
        notification_service.notify_many(db, scope_service.users_covering(db, LEVEL_ROLE[nxt], plan), kind="verification.pending",
                                         title=f"Ready for final verification: {subject} Lecture {lec.lecture_no}",
                                         body=f"{pr.professor.full_name} · “{lec.content_topic}” was verified by {who}. "
                                              "Lecture record is ready for final verification.",
                                         link=LEVEL_QUEUE_LINK[nxt])
    action = "verification.final_verified" if is_final else "verification.verified"
    audit_service.record(db, actor=user, action=action, entity_type="verification", entity_id=v.id,
                         summary=f"{who} ({user.full_name}) {'final verified' if is_final else 'verified'} Lecture {lec.lecture_no}.",
                         new={"level": v.verification_level, "round": v.round, "remarks": data.remarks},
                         scope_type="teaching_plan", scope_id=plan.id)
    db.commit()
    db.expire_all()
    return detail(db, user, v.id)


def request_correction(db: Session, user: User, verification_id: uuid.UUID, data: rq.CorrectionRequest) -> dict:
    v = _lock_pending(db, user, verification_id)
    pr: LectureProgress = v.progress
    lec = pr.lecture
    plan = lec.teaching_plan
    v.status, v.verifier_id, v.verifier_role, v.remarks, v.verified_at = (
        VerificationStatus.CORRECTION_REQUIRED, user.id, user.role_code.value, data.remarks, clock.now_utc())
    pr.submission_status = SubmissionStatus.CORRECTION_REQUIRED
    who = ROLE_LABELS[user.role_code.value]
    notification_service.notify(db, pr.professor_id, kind="verification.correction",
                                title=f"Correction requested by {who}: Lecture {lec.lecture_no}",
                                body=f"{who} remark: {data.remarks}", link=f"/professor/lectures/{lec.id}")
    audit_service.record(db, actor=user, action="verification.correction_requested", entity_type="verification", entity_id=v.id,
                         summary=f"{who} ({user.full_name}) requested a correction on Lecture {lec.lecture_no}.",
                         new={"level": v.verification_level, "round": v.round, "remarks": data.remarks},
                         scope_type="teaching_plan", scope_id=plan.id)
    db.commit()
    db.expire_all()
    return detail(db, user, v.id)
