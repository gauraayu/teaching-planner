"""Turn mapped source columns into canonical lecture rows and validate them.

The output (stored in import_sessions.validation_result) drives the preview
table, the summary counters and the commit step. Commit re-runs this function
rather than trusting the stored result.
"""
from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date

from app.core.config import get_settings
from app.core.enums import MappingStatus, RowValidation
from app.services import value_parsers as vp
from app.services.mapping_service import FIELD_BY_KEY, mapping_problems

SINGLE_FIELDS = ("serial_no", "lecture_no", "lecture_type", "unit_no", "content_topic", "blooms_taxonomy",
                 "planned_date", "planned_start_time", "planned_end_time", "room", "professor_employee_id")


@dataclass
class ValidationContext:
    semester_start: date | None = None
    semester_end: date | None = None
    session_issues: list[dict] = field(default_factory=list)  # plan/faculty/duplicate checks from the caller
    # Professor mapping: lower-cased employee ID -> {"id", "name", "active"}. Unknown IDs are errors, never new accounts.
    professors: dict[str, dict] = field(default_factory=dict)
    plan_professor: dict | None = None      # {"id", "name"} - teaches every row that names nobody else
    plan_room: str | None = None
    plan_label: str = "this plan"
    busy: list = field(default_factory=list)  # conflict_service.Slot of every published class elsewhere


def _fill_down(values: list[str]) -> list[str]:
    out, last = [], ""
    for v in values:
        if v:
            last = v
        out.append(v or last)
    return out


def resolve_columns(columns: list[dict], mapping: dict[str, dict]) -> tuple[dict[str, list[str]], list[list[str]], int]:
    """Return ({field: values}, [subtopic value lists in order], row_count)."""
    row_count = max((len(c["values"]) for c in columns), default=0)
    single: dict[str, list[str]] = {}
    subtopic_cols: list[tuple[int, int, list[str]]] = []
    for position, col in enumerate(columns):
        m = mapping.get(col["key"]) or {}
        if m.get("status") != MappingStatus.MAPPED or not m.get("field"):
            continue
        values = list(col["values"]) + [""] * (row_count - len(col["values"]))
        if m.get("fill_down"):
            values = _fill_down(values)
        if m["field"] == "subtopic":
            subtopic_cols.append((m.get("order") or 99, position, values))
        else:
            single.setdefault(m["field"], values)
    subtopic_cols.sort(key=lambda t: (t[0], t[1]))
    return single, [v for _, _, v in subtopic_cols], row_count


def validate_rows(columns: list[dict], mapping: dict[str, dict], *, overrides: dict | None = None,
                  removed: list[int] | None = None, ctx: ValidationContext | None = None) -> dict:
    settings = get_settings()
    ctx = ctx or ValidationContext()
    overrides = overrides or {}
    removed_set = set(removed or [])

    session_issues = list(mapping_problems(mapping, columns)) + list(ctx.session_issues)
    single, subtopic_cols, row_count = resolve_columns(columns, mapping)
    mapped_fields = set(single) | ({"subtopic"} if subtopic_cols else set())

    if row_count == 0:
        session_issues.append({"level": "ERROR", "code": "NO_ROWS", "message": "There are no data rows to import."})
    if row_count > settings.import_max_rows:
        session_issues.append({"level": "ERROR", "code": "TOO_MANY_ROWS",
                               "message": f"{row_count} rows exceed the limit of {settings.import_max_rows} per plan."})

    rows: list[dict] = []
    for i in range(row_count):
        ov = overrides.get(str(i)) or {}
        raw = {f: (ov[f] if f in ov else single[f][i]) for f in SINGLE_FIELDS if f in single or f in ov}
        raw_subtopics = ov["subtopics"] if "subtopics" in ov else [col[i] for col in subtopic_cols]
        row: dict = {"index": i, "row_number": i + 1, "raw": raw, "issues": [], "values": {}, "edited": bool(ov)}

        if i in removed_set:
            row["status"] = "REMOVED"
            rows.append(row)
            continue
        if not any(str(v).strip() for v in raw.values()) and not any(str(s).strip() for s in raw_subtopics):
            row["status"] = RowValidation.EMPTY.value
            rows.append(row)
            continue

        issues = row["issues"]

        def note(field_key: str, issue):
            if issue:
                issues.append({"field": field_key, "level": issue[0], "message": issue[1]})

        values = row["values"]
        values["serial_no"], iss = vp.parse_serial(raw.get("serial_no", ""))
        note("serial_no", iss)
        values["lecture_no"], iss = vp.parse_lecture_no(raw.get("lecture_no", ""))
        note("lecture_no", iss)
        values["lecture_type"], iss = vp.parse_lecture_type(raw.get("lecture_type", ""))
        note("lecture_type", iss)
        if "unit_no" in mapped_fields or "unit_no" in raw:
            values["unit_no"], iss = vp.parse_unit(raw.get("unit_no", ""))
            note("unit_no", iss)
        else:
            values["unit_no"] = None
        topic = (raw.get("content_topic") or "").strip()
        values["content_topic"] = topic or None
        if not topic:
            note("content_topic", ("ERROR", "Content topic is missing."))
        elif len(topic) > 500:
            note("content_topic", ("WARNING", "Topic is unusually long - check that cells were not merged."))
        if "blooms_taxonomy" in mapped_fields or "blooms_taxonomy" in raw:
            values["blooms_taxonomy"], iss = vp.parse_bloom(raw.get("blooms_taxonomy", ""))
            note("blooms_taxonomy", iss)
        else:
            values["blooms_taxonomy"] = None
        values["subtopics"] = vp.split_subtopics([str(s) for s in raw_subtopics])

        planned = None
        if "planned_date" in mapped_fields or "planned_date" in raw:
            planned, iss = vp.parse_date(raw.get("planned_date", ""), dayfirst=settings.import_date_dayfirst)
            note("planned_date", iss)
            if planned and ctx.semester_start and ctx.semester_end and not (ctx.semester_start <= planned <= ctx.semester_end):
                note("planned_date", ("WARNING", f"{planned:%d %b %Y} is outside the semester "
                                                 f"({ctx.semester_start:%d %b} - {ctx.semester_end:%d %b %Y})."))
            if planned and planned.weekday() == 6:
                note("planned_date", ("WARNING", f"{planned:%d %b %Y} is a Sunday."))
        values["planned_date"] = planned.isoformat() if planned else None

        start_raw, end_raw = raw.get("planned_start_time", ""), raw.get("planned_end_time", "")
        rng = vp.split_time_range(start_raw)
        if rng and not end_raw:
            start_raw, end_raw = rng
        start, iss = vp.parse_time(start_raw, "Start time")
        note("planned_start_time", iss)
        end, iss = vp.parse_time(end_raw, "End time")
        note("planned_end_time", iss)
        if start and end and end <= start:
            note("planned_end_time", ("ERROR", "End time must be after start time."))
        if (start or end) and not planned:
            note("planned_start_time", ("WARNING", "A time is given but no date."))
        values["planned_start_time"] = start.strftime("%H:%M") if start else None
        values["planned_end_time"] = end.strftime("%H:%M") if end else None

        values["room"] = (str(raw.get("room") or "").strip() or None)
        if values["room"] and len(values["room"]) > 40:
            note("room", ("ERROR", "Room is longer than 40 characters."))

        # Professor Employee ID -> an existing professor account. Nothing is ever created from spreadsheet text.
        emp = str(raw.get("professor_employee_id") or "").strip()
        values["professor_employee_id"] = emp or None
        values["professor_id"] = values["professor_name"] = None
        if emp:
            match = ctx.professors.get(emp.lower())
            if not match:
                note("professor_employee_id", ("ERROR", f"Professor not found: no professor account has employee ID “{emp}”. "
                                                        "Map this row to an existing professor."))
            elif not match["active"]:
                note("professor_employee_id", ("ERROR", f"{match['name']} ({emp}) is inactive. Map this row to an active professor."))
            else:
                values["professor_id"], values["professor_name"] = match["id"], match["name"]
        elif ctx.plan_professor:
            values["professor_name"] = ctx.plan_professor["name"]

        # Allocation clashes with classes that are already published elsewhere.
        if planned and start and ctx.busy:
            from app.services import conflict_service as cs
            teacher = values["professor_id"] or (ctx.plan_professor or {}).get("id")
            slot = cs.Slot(on=planned, start=start, end=end, professor_id=uuid.UUID(teacher) if teacher else None,
                           professor_name=values["professor_name"] or "The professor",
                           room=values["room"] or ctx.plan_room, label=f"{ctx.plan_label} Lecture {values['lecture_no'] or '?'}")
            for clash in cs.clashes(slot, [b for b in ctx.busy if b.on == planned]):
                note("professor_employee_id" if clash["kind"] == "PROFESSOR" else "room", (clash["level"], clash["message"]))
        rows.append(row)

    active = [r for r in rows if r.get("status") not in ("REMOVED", RowValidation.EMPTY.value)]

    # Duplicate lecture numbers are errors - they would violate the plan's unique constraint.
    by_no: dict[int, list[dict]] = defaultdict(list)
    for r in active:
        if r["values"].get("lecture_no"):
            by_no[r["values"]["lecture_no"]].append(r)
    for no, group in by_no.items():
        if len(group) > 1:
            rows_txt = ", ".join(str(g["row_number"]) for g in group)
            for g in group:
                g["issues"].append({"field": "lecture_no", "level": "ERROR",
                                    "message": f"Lecture {no} appears more than once (rows {rows_txt})."})

    # Same topic in the same unit is often a continuation lecture - flag, don't block.
    topic_seen: dict[tuple, int] = {}
    for r in active:
        t = r["values"].get("content_topic")
        if not t:
            continue
        key = (r["values"].get("unit_no"), t.strip().lower())
        if key in topic_seen:
            r["issues"].append({"field": "content_topic", "level": "WARNING",
                                "message": f"Same topic as row {topic_seen[key]} - confirm this is a continuation lecture."})
        else:
            topic_seen[key] = r["row_number"]

    # Two lectures in the same slot.
    slots: dict[tuple, int] = {}
    for r in active:
        v = r["values"]
        if v.get("planned_date") and v.get("planned_start_time"):
            key = (v["planned_date"], v["planned_start_time"])
            if key in slots:
                r["issues"].append({"field": "planned_start_time", "level": "WARNING",
                                    "message": f"Same date and start time as row {slots[key]}."})
            else:
                slots[key] = r["row_number"]

    # Schedule going backwards relative to lecture order.
    ordered = sorted((r for r in active if r["values"].get("lecture_no") and r["values"].get("planned_date")),
                     key=lambda r: r["values"]["lecture_no"])
    for prev, cur in zip(ordered, ordered[1:]):
        if cur["values"]["planned_date"] < prev["values"]["planned_date"]:
            cur["issues"].append({"field": "planned_date", "level": "WARNING",
                                  "message": f"Scheduled before Lecture {prev['values']['lecture_no']}."})

    # One professor, two overlapping lectures inside this same sheet: the plan could not be published like that.
    if ctx.plan_professor or any(r["values"].get("professor_id") for r in active):
        from datetime import time as _time

        from app.services import conflict_service as cs
        slots = []
        for r in active:
            v = r["values"]
            teacher = v.get("professor_id") or (ctx.plan_professor or {}).get("id")
            if not (v.get("planned_date") and v.get("planned_start_time") and teacher):
                continue
            slots.append((r, cs.Slot(on=date.fromisoformat(v["planned_date"]), start=_time.fromisoformat(v["planned_start_time"]),
                                     end=_time.fromisoformat(v["planned_end_time"]) if v.get("planned_end_time") else None,
                                     professor_id=uuid.UUID(teacher), professor_name=v.get("professor_name") or "The professor",
                                     room=None, label=f"row {r['row_number']}")))
        slots.sort(key=lambda p: (p[1].on, p[1].start))
        for i, (r, slot) in enumerate(slots):
            for other_row, other in slots[i + 1:]:
                if other.on != slot.on:
                    break
                if slot.professor_id == other.professor_id and cs.overlaps(slot, other):
                    other_row["issues"].append({"field": "planned_start_time", "level": "ERROR",
                                                "message": f"{other.professor_name} would be in two classes at once: this row overlaps row {r['row_number']} "
                                                           f"({slot.start:%H:%M} on {slot.on:%d %b %Y}). Change the time or the professor."})

    counts = Counter()
    for r in rows:
        if "status" not in r:
            levels = {iss["level"] for iss in r["issues"]}
            r["status"] = (RowValidation.ERROR if "ERROR" in levels else
                           RowValidation.WARNING if "WARNING" in levels else RowValidation.VALID).value
        counts[r["status"]] += 1

    importable = [r for r in rows if r["status"] in (RowValidation.VALID, RowValidation.WARNING)]
    session_errors = [s for s in session_issues if s["level"] == "ERROR"]
    if not importable and row_count:
        session_issues.append({"level": "ERROR", "code": "NO_VALID_ROWS", "message": "No row can be imported yet."})
        session_errors.append(session_issues[-1])

    summary = {
        "rows": row_count,
        "lectures": len(importable),
        "units": len({r["values"].get("unit_no") for r in importable if r["values"].get("unit_no")}),
        "subtopics": sum(len(r["values"].get("subtopics") or []) for r in importable),
        "columns": sum(1 for c in columns if (mapping.get(c["key"]) or {}).get("status") == MappingStatus.MAPPED),
        "scheduled": sum(1 for r in importable if r["values"].get("planned_date")),
        "valid": counts[RowValidation.VALID.value],
        "warnings": counts[RowValidation.WARNING.value],
        "errors": counts[RowValidation.ERROR.value],
        "empty": counts[RowValidation.EMPTY.value],
        "removed": counts["REMOVED"],
        "session_errors": len(session_errors),
        "session_warnings": sum(1 for s in session_issues if s["level"] == "WARNING"),
    }
    dates = sorted(r["values"]["planned_date"] for r in importable if r["values"].get("planned_date"))
    summary["first_date"] = dates[0] if dates else None
    summary["last_date"] = dates[-1] if dates else None

    return {
        "summary": summary,
        "session_issues": session_issues,
        "rows": rows,
        "can_commit": summary["errors"] == 0 and not session_errors and summary["lectures"] > 0,
        "fields": {k: FIELD_BY_KEY[k].label for k in FIELD_BY_KEY},
    }
