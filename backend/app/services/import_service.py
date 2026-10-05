"""Import-session orchestration: one workflow for all three import methods.

    FULL TABLE PASTE --+
    COLUMN-WISE PASTE -+--> draft_data (normalised source columns) --> mapping --> validate --> preview --> commit
    EXCEL / CSV -------+

draft_data layout (JSONB, temporary):
    table modes   {"grid": [[...]], "has_header": bool, "source": {...}}
    column mode   {"columns": [{"key","header","values","field","order"}], "row_count": n,
                   "padded": {key: {...}}, "history": [...], "last_added_key": key}
    every mode    {"overrides": {"<row index>": {field: raw}}, "removed": [row indexes]}
"""
from __future__ import annotations

import copy
import uuid
from datetime import date, time

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.clock import now_utc
from app.core.config import get_settings
from app.core.enums import ImportMode, ImportStatus, MappingMethod, MappingStatus, PlanStatus, Role
from app.core.errors import AppError, BusinessRuleViolation, Conflict, NotFound
from app.models import (
    FacultySubjectAssignment, ImportSession, Lecture, LectureSchedule, LectureSubtopic, TeachingPlan, User,
)
from app.services import audit_service, notification_service
from app.services.import_parsing import column_letter, parse_column_text, parse_csv, parse_table_text, parse_xlsx
from app.services.mapping_service import FIELD_BY_KEY, detect_header_row, suggest_mapping
from app.services.validation_service import ValidationContext, validate_rows

ACTIVE_STATUSES = (ImportStatus.DRAFT, ImportStatus.VALIDATING, ImportStatus.READY, ImportStatus.FAILED)
HISTORY_LIMIT = 15


# --------------------------------------------------------------------------- helpers

def _touch(session: ImportSession, *, step: str | None = None) -> None:
    """Any draft change invalidates the previous validation."""
    session.revision = (session.revision or 0) + 1
    if session.status in (ImportStatus.READY, ImportStatus.VALIDATING, ImportStatus.FAILED):
        session.status = ImportStatus.DRAFT
    if step:
        session.current_step = step


def source_columns(session: ImportSession) -> list[dict]:
    draft = session.draft_data or {}
    if session.import_mode == ImportMode.COLUMN_WISE:
        return [{"key": c["key"], "header": c["header"], "values": c["values"], "letter": None} for c in draft.get("columns", [])]
    grid = draft.get("grid") or []
    if not grid:
        return []
    has_header = draft.get("has_header", True)
    width = len(grid[0])
    header_row = grid[0] if has_header else [""] * width
    body = grid[1:] if has_header else grid
    cols = []
    for i in range(width):
        letter = column_letter(i)
        cols.append({
            "key": f"c{i}",
            "header": header_row[i] or (f"Column {letter}" if not has_header else ""),
            "letter": letter,
            "values": [r[i] for r in body],
        })
    return cols


def _row_count(session: ImportSession) -> int:
    cols = source_columns(session)
    return max((len(c["values"]) for c in cols), default=0)


def get_session(db: Session, session_id: uuid.UUID) -> ImportSession:
    s = db.get(ImportSession, session_id)
    if not s:
        raise NotFound("Import session not found.")
    return s


def _ensure_editable(session: ImportSession) -> None:
    if session.status == ImportStatus.IMPORTED:
        raise Conflict("This import has already been published. Start a new import to make changes.", code="IMPORT_CLOSED")


def _save(db: Session, session: ImportSession) -> ImportSession:
    session.row_count = _row_count(session)
    # JSONB columns are replaced wholesale so SQLAlchemy always detects the change.
    session.draft_data = copy.deepcopy(session.draft_data)
    session.column_mapping = copy.deepcopy(session.column_mapping)
    db.commit()
    db.refresh(session)
    return session


# --------------------------------------------------------------------------- lifecycle

def create_session(db: Session, admin: User, plan_id: uuid.UUID, *, resume: bool = True) -> ImportSession:
    plan = db.get(TeachingPlan, plan_id)
    if not plan:
        raise NotFound("Teaching plan not found.")
    if plan.status in (PlanStatus.PUBLISHED, PlanStatus.ARCHIVED):
        raise Conflict(f"This plan is {plan.status.lower()}. Lectures can only be imported into a draft plan.",
                       code="PLAN_NOT_DRAFT")
    if resume:
        existing = db.scalar(
            select(ImportSession).where(ImportSession.teaching_plan_id == plan.id, ImportSession.status.in_(ACTIVE_STATUSES))
            .order_by(ImportSession.updated_at.desc())
        )
        if existing:
            return existing
    session = ImportSession(
        admin_id=admin.id, teaching_plan_id=plan.id, subject_id=plan.subject_id, semester_id=plan.semester_id,
        section_id=plan.section_id, faculty_id=plan.professor_id, status=ImportStatus.DRAFT,
        current_step="METHOD", draft_data={}, column_mapping={}, revision=0,
    )
    db.add(session)
    db.flush()
    audit_service.record(db, actor=admin, action="import.started", entity_type="import_session", entity_id=session.id,
                         summary=f"Started an import for {plan.name}.", scope_type="teaching_plan", scope_id=plan.id)
    db.commit()
    db.refresh(session)
    return session


def set_mode(db: Session, session: ImportSession, mode: ImportMode) -> ImportSession:
    _ensure_editable(session)
    if session.import_mode and session.import_mode != mode:
        # Switching method discards the previous method's data - explicit, never a silent merge.
        session.draft_data, session.column_mapping = {}, {}
    session.import_mode = mode
    _touch(session, step="PASTE" if mode != ImportMode.COLUMN_WISE else "COLUMNS")
    return _save(db, session)


def _load_grid(db: Session, session: ImportSession, grid, *, mode: ImportMode, source: dict, has_header: bool | None) -> dict:
    if grid.height == 0 or grid.width == 0:
        raise AppError("No data was found in the pasted range or file.", code="EMPTY_DATA")
    detected = detect_header_row(grid.rows[0], grid.rows[1:]) if has_header is None else has_header
    session.import_mode = mode
    session.source_name = source.get("file_name")
    session.draft_data = {"grid": grid.rows, "has_header": detected, "source": source | {
        "trailing_empty_rows_dropped": grid.trailing_empty_rows_dropped, "notes": grid.notes,
    }, "overrides": {}, "removed": []}
    session.column_mapping = suggest_mapping(source_columns(session))
    _touch(session, step="MAP")
    _save(db, session)
    return {
        "rows_detected": session.row_count,
        "columns_detected": grid.width,
        "has_header": detected,
        "trailing_empty_rows_dropped": grid.trailing_empty_rows_dropped,
        "notes": grid.notes,
    }


def load_full_table(db: Session, session: ImportSession, raw_text: str, has_header: bool | None = None) -> dict:
    _ensure_editable(session)
    grid = parse_table_text(raw_text)
    return _load_grid(db, session, grid, mode=ImportMode.FULL_TABLE, source={"kind": "clipboard"}, has_header=has_header)


def load_file(db: Session, session: ImportSession, file_name: str, content: bytes, sheet: str | None = None,
              has_header: bool | None = None) -> dict:
    _ensure_editable(session)
    settings = get_settings()
    if len(content) > settings.import_max_file_mb * 1024 * 1024:
        raise AppError(f"The file is larger than {settings.import_max_file_mb} MB.", code="FILE_TOO_LARGE")
    lower = (file_name or "").lower()
    if lower.endswith(".xlsx") or lower.endswith(".xlsm"):
        grid, sheets, chosen = parse_xlsx(content, sheet)
        result = _load_grid(db, session, grid, mode=ImportMode.EXCEL,
                            source={"kind": "file", "file_name": file_name, "sheet": chosen, "sheets": sheets}, has_header=has_header)
        return result | {"sheet": chosen, "sheets": sheets}
    if lower.endswith(".csv"):
        grid = parse_csv(content)
        return _load_grid(db, session, grid, mode=ImportMode.CSV, source={"kind": "file", "file_name": file_name}, has_header=has_header)
    if lower.endswith(".xls"):
        raise AppError("Legacy .xls files are not supported. Save the sheet as .xlsx or .csv and upload again.", code="UNSUPPORTED_FILE")
    raise AppError("Unsupported file type. Upload an .xlsx or .csv file.", code="UNSUPPORTED_FILE")


def set_header(db: Session, session: ImportSession, has_header: bool) -> ImportSession:
    _ensure_editable(session)
    if session.import_mode == ImportMode.COLUMN_WISE:
        raise BusinessRuleViolation("Column-by-column imports do not use a header row.")
    session.draft_data = {**session.draft_data, "has_header": has_header, "overrides": {}, "removed": []}
    session.column_mapping = suggest_mapping(source_columns(session))
    _touch(session, step="MAP")
    return _save(db, session)


def update_mapping(db: Session, session: ImportSession, updates: dict[str, dict]) -> ImportSession:
    """updates: {column_key: {"field": str|None, "ignore": bool, "fill_down": bool, "order": int, "confirm": bool}}"""
    _ensure_editable(session)
    keys = {c["key"] for c in source_columns(session)}
    mapping = copy.deepcopy(session.column_mapping or {})
    for key, upd in updates.items():
        if key not in keys:
            raise AppError(f"Unknown column '{key}'.", code="INVALID_MAPPING")
        current = mapping.get(key) or {"field": None, "status": MappingStatus.NEEDS_REVIEW.value, "method": MappingMethod.NONE.value, "confidence": 0}
        if upd.get("ignore"):
            current |= {"field": None, "status": MappingStatus.IGNORED.value, "method": MappingMethod.MANUAL.value, "note": None}
        elif upd.get("confirm") and current.get("status") == MappingStatus.SUGGESTED:
            current |= {"status": MappingStatus.MAPPED.value, "note": None}
        elif "field" in upd:
            field = upd["field"]
            if field is None:
                current |= {"field": None, "status": MappingStatus.NEEDS_REVIEW.value, "method": MappingMethod.MANUAL.value}
            else:
                if field not in FIELD_BY_KEY:
                    raise AppError(f"'{field}' is not a portal field.", code="INVALID_MAPPING")
                if not FIELD_BY_KEY[field].multi:
                    # Moving a single-value field releases it from any other column.
                    for other_key, other in mapping.items():
                        if other_key != key and other.get("field") == field and other.get("status") in (MappingStatus.MAPPED, MappingStatus.SUGGESTED):
                            other |= {"field": None, "status": MappingStatus.NEEDS_REVIEW.value,
                                      "note": f"{FIELD_BY_KEY[field].label} was moved to another column."}
                current |= {"field": field, "status": MappingStatus.MAPPED.value, "method": MappingMethod.MANUAL.value,
                            "confidence": 100, "note": None, "suggestion": None}
                if field == "subtopic" and not current.get("order"):
                    used = [m.get("order") or 0 for k, m in mapping.items() if m.get("field") == "subtopic" and k != key]
                    current["order"] = max(used, default=0) + 1
        if "fill_down" in upd:
            current["fill_down"] = bool(upd["fill_down"])
        if upd.get("order"):
            current["order"] = int(upd["order"])
        mapping[key] = current
    session.column_mapping = mapping
    _touch(session, step="MAP")
    return _save(db, session)


def confirm_all_suggestions(db: Session, session: ImportSession) -> ImportSession:
    pending = {k: {"confirm": True} for k, m in (session.column_mapping or {}).items() if m.get("status") == MappingStatus.SUGGESTED}
    return update_mapping(db, session, pending) if pending else session


# --------------------------------------------------------------------------- column-wise

def _snapshot(draft: dict, mapping: dict) -> dict:
    return {"columns": copy.deepcopy(draft.get("columns", [])), "row_count": draft.get("row_count"),
            "padded": copy.deepcopy(draft.get("padded", {})), "mapping": copy.deepcopy(mapping),
            "last_added_key": draft.get("last_added_key")}


def _field_header(field: str, order: int | None) -> str:
    return f"{FIELD_BY_KEY[field].label} {order}" if field == "subtopic" else FIELD_BY_KEY[field].label


def add_column(db: Session, session: ImportSession, *, field: str, raw_text: str, order: int | None = None,
               replace_key: str | None = None, on_mismatch: str | None = None) -> dict:
    """Add (or replace) one pasted column, aligned strictly by row index.

    Returns {"status": "ADDED"} or {"status": "MISMATCH", ...}. A mismatch is never
    resolved automatically: the admin must choose PAD (fill missing rows at the end
    with empty values), EXTEND (the new column is longer - extend the table) or re-paste.
    """
    _ensure_editable(session)
    if session.import_mode != ImportMode.COLUMN_WISE:
        raise BusinessRuleViolation("Switch the import method to Column-by-Column first.")
    if field not in FIELD_BY_KEY:
        raise AppError(f"'{field}' is not a portal field.", code="INVALID_FIELD")
    values, notes = parse_column_text(raw_text)

    draft = copy.deepcopy(session.draft_data or {})
    columns: list[dict] = draft.setdefault("columns", [])
    mapping = copy.deepcopy(session.column_mapping or {})

    target = None
    if replace_key:
        target = next((c for c in columns if c["key"] == replace_key), None)
        if not target:
            raise NotFound("The column to replace no longer exists.")
        field = target["field"]
        order = target.get("order")
    elif not FIELD_BY_KEY[field].multi and any(c["field"] == field for c in columns):
        raise Conflict(f"{FIELD_BY_KEY[field].label} has already been imported. Use Replace Column to paste it again.",
                       code="FIELD_ALREADY_IMPORTED")
    if field == "subtopic" and not order:
        order = max((c.get("order") or 0 for c in columns if c["field"] == "subtopic"), default=0) + 1

    others = [c for c in columns if c is not target]
    expected = max((len(c["values"]) for c in others), default=None) if others else None
    received = len(values)

    if expected is not None and received != expected:
        if on_mismatch is None:
            reference = max(others, key=lambda c: len(c["values"]))
            return {
                "status": "MISMATCH", "field": field, "field_label": _field_header(field, order),
                "expected": expected, "received": received, "difference": abs(expected - received),
                "reference_column": reference["header"],
                "can_pad": received < expected, "can_extend": received > expected,
                # Side-by-side alignment so the admin can see where rows diverge.
                "alignment": [
                    {"row": i + 1, "reference": reference["values"][i] if i < len(reference["values"]) else None,
                     "incoming": values[i] if i < received else None}
                    for i in range(max(expected, received))
                ],
                "notes": notes,
            }
        if on_mismatch == "PAD" and received < expected:
            draft.setdefault("padded", {})
            values = values + [""] * (expected - received)
            pad_note = {"expected": expected, "received": received}
        elif on_mismatch == "EXTEND" and received > expected:
            for c in others:
                c["values"] = c["values"] + [""] * (received - len(c["values"]))
            pad_note = None
            draft.setdefault("padded", {})
            for c in others:
                draft["padded"].setdefault(c["key"], {"expected": received, "received": expected})
        else:
            raise AppError("That option does not apply to this mismatch.", code="INVALID_MISMATCH_RESOLUTION")
    else:
        pad_note = None

    history = draft.setdefault("history", [])
    history.append(_snapshot(draft, mapping))
    del history[:-HISTORY_LIMIT]

    if target:
        target["values"] = values
        key = target["key"]
        draft.get("padded", {}).pop(key, None)
    else:
        key = f"k{uuid.uuid4().hex[:8]}"
        columns.append({"key": key, "field": field, "order": order, "header": _field_header(field, order), "values": values})
        mapping[key] = {"field": field, "order": order, "status": MappingStatus.MAPPED.value,
                        "method": MappingMethod.MANUAL.value, "confidence": 100, "fill_down": False}
    if pad_note:
        draft["padded"][key] = pad_note
    draft["row_count"] = max((len(c["values"]) for c in columns), default=0)
    draft["last_added_key"] = key
    draft.setdefault("overrides", {})
    draft.setdefault("removed", [])

    session.draft_data, session.column_mapping = draft, mapping
    _touch(session, step="COLUMNS")
    _save(db, session)
    return {"status": "ADDED", "key": key, "values_detected": received, "row_count": session.row_count, "notes": notes}


def clear_column(db: Session, session: ImportSession, key: str) -> ImportSession:
    _ensure_editable(session)
    draft = copy.deepcopy(session.draft_data or {})
    columns = draft.get("columns", [])
    if not any(c["key"] == key for c in columns):
        raise NotFound("Column not found.")
    mapping = copy.deepcopy(session.column_mapping or {})
    draft.setdefault("history", []).append(_snapshot(draft, mapping))
    draft["columns"] = [c for c in columns if c["key"] != key]
    mapping.pop(key, None)
    draft.get("padded", {}).pop(key, None)
    draft["row_count"] = max((len(c["values"]) for c in draft["columns"]), default=0)
    if draft.get("last_added_key") == key:
        draft["last_added_key"] = None
    session.draft_data, session.column_mapping = draft, mapping
    _touch(session, step="COLUMNS")
    return _save(db, session)


def undo_column_change(db: Session, session: ImportSession) -> ImportSession:
    _ensure_editable(session)
    draft = copy.deepcopy(session.draft_data or {})
    history = draft.get("history") or []
    if not history:
        raise AppError("There is nothing to undo.", code="NOTHING_TO_UNDO")
    snap = history.pop()
    draft.update(columns=snap["columns"], row_count=snap["row_count"], padded=snap["padded"],
                 last_added_key=snap.get("last_added_key"), history=history)
    session.draft_data, session.column_mapping = draft, snap["mapping"]
    _touch(session, step="COLUMNS")
    return _save(db, session)


# --------------------------------------------------------------------------- preview edits

EDITABLE_FIELDS = {"serial_no", "lecture_no", "lecture_type", "unit_no", "content_topic", "blooms_taxonomy",
                   "planned_date", "planned_start_time", "planned_end_time", "subtopics", "room", "professor_employee_id"}


def edit_row(db: Session, session: ImportSession, index: int, values: dict) -> ImportSession:
    _ensure_editable(session)
    if not 0 <= index < _row_count(session):
        raise NotFound("Row not found.")
    bad = set(values) - EDITABLE_FIELDS
    if bad:
        raise AppError(f"Cannot edit {', '.join(sorted(bad))}.", code="INVALID_FIELD")
    draft = copy.deepcopy(session.draft_data)
    clean = {k: ([str(s).strip() for s in v if str(s).strip()] if k == "subtopics" else str(v or "").strip()) for k, v in values.items()}
    draft.setdefault("overrides", {})[str(index)] = {**draft["overrides"].get(str(index), {}), **clean}
    session.draft_data = draft
    _touch(session, step="PREVIEW")
    return _save(db, session)


def set_row_removed(db: Session, session: ImportSession, index: int, removed: bool) -> ImportSession:
    _ensure_editable(session)
    if not 0 <= index < _row_count(session):
        raise NotFound("Row not found.")
    draft = copy.deepcopy(session.draft_data)
    current = set(draft.get("removed", []))
    current.add(index) if removed else current.discard(index)
    draft["removed"] = sorted(current)
    session.draft_data = draft
    _touch(session, step="PREVIEW")
    return _save(db, session)


# --------------------------------------------------------------------------- validation

def _context(db: Session, session: ImportSession) -> ValidationContext:
    plan = session.teaching_plan
    issues: list[dict] = []
    professor = plan.professor
    if not professor or professor.role_code != Role.PROFESSOR or not professor.is_active:
        issues.append({"level": "ERROR", "code": "INVALID_FACULTY", "message": "The assigned professor is not an active professor account."})
    if plan.section.semester_id != plan.semester_id or plan.section.branch_id != plan.branch_id:
        issues.append({"level": "ERROR", "code": "INVALID_ASSIGNMENT", "message": "The section does not belong to the plan's branch and semester."})
    if plan.subject.branch_id != plan.branch_id:
        issues.append({"level": "ERROR", "code": "INVALID_ASSIGNMENT", "message": "The subject is not offered by the plan's branch."})
    if plan.status in (PlanStatus.PUBLISHED, PlanStatus.ARCHIVED):
        issues.append({"level": "ERROR", "code": "PLAN_NOT_DRAFT", "message": "The target plan is no longer a draft."})
    # Duplicate import protection: another live plan with lectures for the same class.
    other = db.scalar(
        select(TeachingPlan).where(
            TeachingPlan.id != plan.id, TeachingPlan.subject_id == plan.subject_id, TeachingPlan.section_id == plan.section_id,
            TeachingPlan.semester_id == plan.semester_id, TeachingPlan.status != PlanStatus.ARCHIVED,
        )
    )
    if other:
        issues.append({"level": "ERROR", "code": "DUPLICATE_PLAN",
                       "message": f"'{other.name}' already covers this subject and section ({other.status.title()}). Archive it first."})
    existing = db.scalar(select(func.count(Lecture.id)).where(Lecture.teaching_plan_id == plan.id)) or 0
    if existing:
        issues.append({"level": "WARNING", "code": "REPLACES_LECTURES",
                       "message": f"This draft plan already has {existing} lectures. Publishing will replace them."})
    for key, info in ((session.draft_data or {}).get("padded") or {}).items():
        col = next((c for c in source_columns(session) if c["key"] == key), None)
        if col:
            issues.append({"level": "WARNING", "code": "ROW_COUNT_PADDED",
                           "message": f"{col['header']} had {info['received']} values for {info['expected']} rows; "
                                      f"{info['expected'] - info['received']} empty value(s) were added at the end."})
    sem = plan.semester
    from app.models import RoleModel
    from app.services import conflict_service
    professors = {u.employee_code.lower(): {"id": str(u.id), "name": u.full_name, "active": u.is_active}
                  for u in db.scalars(select(User).join(RoleModel).where(RoleModel.code == Role.PROFESSOR.value,
                                                                         User.employee_code.is_not(None))).unique()}
    return ValidationContext(
        semester_start=sem.start_date, semester_end=sem.end_date, session_issues=issues, professors=professors,
        plan_professor={"id": str(professor.id), "name": professor.full_name} if professor else None, plan_room=plan.room,
        plan_label=f"{plan.subject.short_name or plan.subject.code} {sem.name.replace('Semester', 'Sem')}-{plan.section.name}",
        busy=conflict_service.published_slots(db, sem.start_date, sem.end_date, exclude_plan_id=plan.id))


def validate(db: Session, session: ImportSession) -> dict:
    _ensure_editable(session)
    session.status = ImportStatus.VALIDATING
    db.flush()
    draft = session.draft_data or {}
    result = validate_rows(source_columns(session), session.column_mapping or {},
                           overrides=draft.get("overrides"), removed=draft.get("removed"), ctx=_context(db, session))
    result["revision"] = session.revision
    session.validation_result = result
    session.validated_revision = session.revision
    session.status = ImportStatus.READY if result["can_commit"] else ImportStatus.DRAFT
    session.current_step = "PREVIEW"
    session.row_count = result["summary"]["rows"]
    db.commit()
    db.refresh(session)
    return result


def preview(session: ImportSession, *, status: str | None = None, q: str | None = None) -> dict:
    result = session.validation_result
    if not result:
        raise AppError("Validate the import before opening the preview.", code="NOT_VALIDATED")
    rows = result["rows"]
    if status:
        wanted = set(status.split(","))
        rows = [r for r in rows if r["status"] in wanted]
    if q:
        needle = q.lower()
        rows = [r for r in rows if needle in " ".join(str(v) for v in r["values"].values() if v).lower()
                or needle in str(r["row_number"])]
    return {**result, "rows": rows, "stale": session.validated_revision != session.revision}


# --------------------------------------------------------------------------- commit

def commit(db: Session, session: ImportSession, admin: User, *, publish: bool = True) -> dict:
    """Write the plan in ONE transaction. Any failure rolls everything back."""
    _ensure_editable(session)
    session_id, plan_id = session.id, session.teaching_plan_id
    try:
        plan = db.scalar(select(TeachingPlan).where(TeachingPlan.id == plan_id).with_for_update(of=TeachingPlan))
        if plan.status in (PlanStatus.PUBLISHED, PlanStatus.ARCHIVED):
            raise Conflict("The plan was published or archived in the meantime.", code="PLAN_NOT_DRAFT")

        # Never trust a stored result: re-validate against the current draft.
        draft = session.draft_data or {}
        result = validate_rows(source_columns(session), session.column_mapping or {},
                               overrides=draft.get("overrides"), removed=draft.get("removed"), ctx=_context(db, session))
        if not result["can_commit"]:
            raise BusinessRuleViolation("The import still has errors. Fix or remove them before publishing.",
                                        code="IMPORT_HAS_ERRORS", details={"summary": result["summary"]})

        db.execute(delete(Lecture).where(Lecture.teaching_plan_id == plan.id))  # draft re-import replaces lectures

        importable = [r for r in result["rows"] if r["status"] in ("VALID", "WARNING")]
        subtopic_total = 0
        for seq, r in enumerate(importable, start=1):
            v = r["values"]
            lecture = Lecture(
                teaching_plan_id=plan.id, sequence=seq, serial_no=v.get("serial_no"), lecture_no=v["lecture_no"],
                lecture_type=v["lecture_type"], unit_no=v.get("unit_no"), content_topic=v["content_topic"],
                blooms_taxonomy=v.get("blooms_taxonomy"), import_row_index=r["index"],
                is_released=plan.sprint_plan_id is None,  # a sprint plan's topics are dated and published week by week
                # Per-lecture allocation from the "Professor Employee ID" column; NULL = the plan's professor.
                professor_id=(uuid.UUID(v["professor_id"]) if v.get("professor_id") and v["professor_id"] != str(plan.professor_id) else None),
            )
            lecture.subtopics = [LectureSubtopic(position=p, title=t) for p, t in enumerate(v.get("subtopics") or [], start=1)]
            subtopic_total += len(lecture.subtopics)
            lecture.schedule = LectureSchedule(
                planned_date=date.fromisoformat(v["planned_date"]) if v.get("planned_date") else None,
                planned_start_time=time.fromisoformat(v["planned_start_time"]) if v.get("planned_start_time") else None,
                planned_end_time=time.fromisoformat(v["planned_end_time"]) if v.get("planned_end_time") else None,
                room=v.get("room"),
            )
            db.add(lecture)
        db.flush()  # surface constraint violations here, before anything else is written

        assignment = db.scalar(select(FacultySubjectAssignment).where(
            FacultySubjectAssignment.subject_id == plan.subject_id, FacultySubjectAssignment.section_id == plan.section_id,
            FacultySubjectAssignment.semester_id == plan.semester_id, FacultySubjectAssignment.professor_id == plan.professor_id,
        ))
        if not assignment:
            db.add(FacultySubjectAssignment(professor_id=plan.professor_id, subject_id=plan.subject_id,
                                            section_id=plan.section_id, semester_id=plan.semester_id, is_primary=True))

        now = now_utc()
        plan.status = PlanStatus.PUBLISHED if publish else PlanStatus.READY
        if publish:
            plan.published_at, plan.published_by_id = now, admin.id

        session.status = ImportStatus.IMPORTED
        session.committed_at = now
        session.current_step = "DONE"
        session.validation_result = result
        session.validated_revision = session.revision
        session.failure_reason = None

        counts = {"lectures": len(importable), "subtopics": subtopic_total, "units": result["summary"]["units"]}
        audit_service.record(db, actor=admin, action="plan.imported", entity_type="teaching_plan", entity_id=plan.id,
                             summary=f"Imported {len(importable)} lectures into {plan.name}.",
                             new=counts | {"import_mode": session.import_mode, "source": session.source_name},
                             scope_type="teaching_plan", scope_id=plan.id)
        if publish:
            audit_service.record(db, actor=admin, action="plan.published", entity_type="teaching_plan", entity_id=plan.id,
                                 summary=f"Published teaching plan {plan.name}.", new={"status": PlanStatus.PUBLISHED},
                                 scope_type="teaching_plan", scope_id=plan.id)
            db.flush()
            db.expire(plan, ["lectures"])  # the lectures were replaced above
            from app.services import teaching_plan_service
            teaching_plan_service.notify_published(db, plan, len(importable))
        notification_service.notify(db, admin.id, kind="plan.imported",
                                    title=f"{plan.name} imported successfully",
                                    body=f"{len(importable)} lectures, {subtopic_total} subtopics.",
                                    link=f"/admin/plans/{plan.id}")
        db.commit()
    except AppError as exc:
        db.rollback()
        _mark_failed(db, session_id, exc.message)
        raise
    except Exception as exc:
        db.rollback()
        _mark_failed(db, session_id, "The import could not be saved. No lectures were created.")
        raise AppError("Unable to import plan. No lectures were created; your draft is safe.",
                       code="IMPORT_FAILED", status_code=500) from exc
    return {"teaching_plan_id": str(plan_id), "status": "PUBLISHED" if publish else "READY", **counts}


def _mark_failed(db: Session, session_id: uuid.UUID, reason: str) -> None:
    s = db.get(ImportSession, session_id)
    if s and s.status != ImportStatus.IMPORTED:
        s.status = ImportStatus.FAILED
        s.failure_reason = reason
        db.commit()


def discard(db: Session, session: ImportSession, admin: User) -> None:
    _ensure_editable(session)
    db.delete(session)
    db.commit()
