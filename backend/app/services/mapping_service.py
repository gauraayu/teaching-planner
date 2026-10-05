"""Deterministic column-mapping engine.

Pipeline per spreadsheet column:
  1. normalise the header
  2. exact match against canonical field keys/labels
  3. alias match (configurable dictionary below)
  4. RapidFuzz suggestion - only when 1-3 fail, never auto-accepted
  5. admin confirmation / manual override in the UI

No machine learning is involved; every decision is explainable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz, process

from app.core.config import get_settings
from app.core.enums import MappingMethod, MappingStatus


@dataclass(frozen=True)
class FieldDef:
    key: str
    label: str
    required: bool = False
    multi: bool = False  # several source columns may map here (subtopics)
    description: str = ""


FIELDS: tuple[FieldDef, ...] = (
    FieldDef("serial_no", "Serial Number", description="Row serial from the sheet (optional)"),
    FieldDef("lecture_no", "Lecture Number", required=True),
    FieldDef("lecture_type", "Lecture Type", description="Theory, Practical, Tutorial..."),
    FieldDef("unit_no", "Unit Number"),
    FieldDef("content_topic", "Content Topic", required=True),
    FieldDef("blooms_taxonomy", "Bloom's Taxonomy", description="K1-K6"),
    FieldDef("subtopic", "Subtopic", multi=True, description="Map every subtopic column here; order is preserved"),
    FieldDef("planned_date", "Planned Date"),
    FieldDef("planned_start_time", "Planned Start Time"),
    FieldDef("planned_end_time", "Planned End Time"),
    FieldDef("room", "Room", description="Classroom for this lecture; empty = the plan's default room"),
    FieldDef("professor_employee_id", "Professor Employee ID",
             description="Employee ID of the professor for this lecture; empty = the plan's professor"),
)
FIELD_BY_KEY = {f.key: f for f in FIELDS}
REQUIRED_FIELDS = tuple(f.key for f in FIELDS if f.required)

# Aliases are written naturally and normalised at load time, so admins can extend
# this list (or load it from settings) without caring about case/underscores.
FIELD_ALIASES: dict[str, list[str]] = {
    "serial_no": ["sr no", "srno", "sr", "s no", "sno", "serial", "serial no", "serial number", "sl no", "sl", "sr. no.", "#"],
    "lecture_no": ["lecture no", "lecture_no", "lecture number", "lec no", "lec_no", "lecture", "lecture #", "lec", "lecture num", "class no", "session no"],
    "lecture_type": ["lecture type", "type", "lec type", "class type", "session type", "mode", "delivery type"],
    "unit_no": ["unit", "unit no", "unit_no", "unit number", "module", "module no", "unit num"],
    "content_topic": ["content topic", "content_topic", "topic", "topic name", "lecture topic", "topics", "content", "title", "topic covered", "topic to be covered", "main topic"],
    "blooms_taxonomy": ["bloom", "blooms", "bloom taxonomy", "blooms taxonomy", "bloom's taxonomy", "bloom level", "blooms level", "bt", "bt level", "bloom's level", "taxonomy", "rbt", "rbt level", "knowledge level", "k level"],
    "subtopic": ["subtopic", "sub topic", "subtopics", "sub topics", "sub-topic"],
    "planned_date": ["scheduled date", "schedule date", "planned date", "lecture date", "date", "date of lecture", "proposed date", "plan date", "tentative date"],
    "planned_start_time": ["start time", "planned start time", "from", "time from", "start", "lecture time", "time", "scheduled time", "slot"],
    "planned_end_time": ["end time", "planned end time", "to", "time to", "end"],
    "room": ["room", "room no", "room number", "classroom", "class room", "venue", "lab", "hall"],
    "professor_employee_id": ["professor employee id", "professor id", "faculty id", "faculty employee id", "employee id", "emp id",
                              "emp code", "employee code", "faculty code", "professor code", "staff id", "teacher id"],
}

# Execution/verification columns from the legacy sheet. The portal captures these
# itself, so they are auto-ignored with an explanation instead of being imported.
EXECUTION_COLUMN_PATTERNS = (
    r"^remarks?\b", r"\bverified\b", r"\bverification\b", r"\bshared\b", r"\bnotes? link\b",
    r"\bassignment link\b", r"\bactual date\b", r"\bcompletion\b", r"\bcompleted\b", r"^status$",
    r"\bsign(ature)?\b", r"\bdaily lecture notes\b", r"\bweekly assignment\b",
)
EXECUTION_NOTE = "Execution data - professors record this in the portal, so it is not imported."

_SUBTOPIC_RE = re.compile(r"^(?:sub ?topics?|sub topic)(?: (\d{1,2}))?$")


def normalize_header(header: str | None) -> str:
    """'Content_Topic', 'CONTENT-TOPIC', ' content topic', 'ContentTopic' -> 'content topic'."""
    if not header:
        return ""
    h = header.replace(" ", " ").strip()
    h = re.sub(r"([a-z])([A-Z])", r"\1 \2", h)  # camelCase -> camel Case
    h = h.lower()
    h = re.sub(r"[’'`]", "", h)  # bloom's -> blooms
    h = h.replace("&", " and ").replace("#", " no ")
    h = re.sub(r"[^a-z0-9]+", " ", h)
    h = re.sub(r"([a-z])(\d)", r"\1 \2", h)  # topic1 -> topic 1
    h = re.sub(r"(\d)([a-z])", r"\1 \2", h)
    return re.sub(r"\s+", " ", h).strip()


def _build_alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for key, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            norm = normalize_header(alias)
            if norm:
                index.setdefault(norm, key)
    return index


ALIAS_INDEX = _build_alias_index()
_EXACT_INDEX = {normalize_header(f.key): f.key for f in FIELDS} | {normalize_header(f.label): f.key for f in FIELDS}


@dataclass
class MappingDecision:
    field: str | None
    status: MappingStatus
    method: MappingMethod
    confidence: int
    order: int | None = None  # subtopic ordinal
    suggestion: str | None = None  # field hint for NEEDS_REVIEW
    note: str | None = None

    def to_dict(self) -> dict:
        return {
            "field": self.field, "status": self.status.value, "method": self.method.value,
            "confidence": self.confidence, "order": self.order, "suggestion": self.suggestion, "note": self.note,
            "fill_down": False,
        }


def _subtopic_order(norm: str) -> tuple[bool, int | None]:
    m = _SUBTOPIC_RE.match(norm)
    if not m:
        return False, None
    return True, int(m.group(1)) if m.group(1) else None


# --- value profiling: used only to *hint* at a field when the header says nothing useful.
_BLOOM_VALUE = re.compile(r"^(k|l|bt)?\s*[1-6]$|^(remember|understand|apply|analy[sz]e|evaluate|create)", re.I)
_DATE_VALUE = re.compile(r"^\d{1,4}[-/.]\d{1,2}[-/.]\d{2,4}$|^\d{1,2}[ -][A-Za-z]{3,9}[ -,]*\d{2,4}$")
_TIME_VALUE = re.compile(r"^\d{1,2}([:.]\d{2})?\s*(am|pm)?(\s*[-–to]+\s*\d{1,2}([:.]\d{2})?\s*(am|pm)?)?$", re.I)


def profile_values(values: list[str]) -> str | None:
    sample = [v for v in values if v][:30]
    if len(sample) < 2:
        return None

    def share(pattern) -> float:
        return sum(1 for v in sample if pattern.match(v)) / len(sample)

    if share(_BLOOM_VALUE) >= 0.8:
        return "blooms_taxonomy"
    if share(_DATE_VALUE) >= 0.8:
        return "planned_date"
    if share(_TIME_VALUE) >= 0.8 and any(":" in v or "am" in v.lower() or "pm" in v.lower() for v in sample):
        return "planned_start_time"
    return None


def decide(header: str, values: list[str] | None = None) -> MappingDecision:
    settings = get_settings()
    norm = normalize_header(header)
    values = values or []

    if not norm:
        hint = profile_values(values)
        return MappingDecision(None, MappingStatus.NEEDS_REVIEW, MappingMethod.NONE, 0, suggestion=hint,
                               note="Column has no header." + (" Values look like " + FIELD_BY_KEY[hint].label + "." if hint else ""))

    is_sub, order = _subtopic_order(norm)
    if is_sub:
        return MappingDecision("subtopic", MappingStatus.MAPPED, MappingMethod.ALIAS, 100, order=order)

    if norm in _EXACT_INDEX:
        return MappingDecision(_EXACT_INDEX[norm], MappingStatus.MAPPED, MappingMethod.EXACT, 100)
    if norm in ALIAS_INDEX:
        return MappingDecision(ALIAS_INDEX[norm], MappingStatus.MAPPED, MappingMethod.ALIAS, 100)

    if any(re.search(p, norm) for p in EXECUTION_COLUMN_PATTERNS):
        return MappingDecision(None, MappingStatus.IGNORED, MappingMethod.EXECUTION_COLUMN, 100, note=EXECUTION_NOTE)

    # Fuzzy: compare against every alias; never silently accepted.
    match = process.extractOne(norm, list(ALIAS_INDEX.keys()), scorer=fuzz.token_sort_ratio)
    if match:
        alias, score, _ = match
        field = ALIAS_INDEX[alias]
        score = int(round(score))
        if score >= settings.mapping_fuzzy_suggest_threshold:
            return MappingDecision(field, MappingStatus.SUGGESTED, MappingMethod.FUZZY, score,
                                   note=f"Close to '{alias}'. Confirm this mapping.")
        if score >= settings.mapping_fuzzy_hint_threshold:
            return MappingDecision(None, MappingStatus.NEEDS_REVIEW, MappingMethod.FUZZY, score, suggestion=field,
                                   note=f"Possibly {FIELD_BY_KEY[field].label} ({score}% similar). Choose a field or ignore.")

    hint = profile_values(values)
    if hint:
        return MappingDecision(None, MappingStatus.NEEDS_REVIEW, MappingMethod.NONE, 0, suggestion=hint,
                               note=f"Header not recognised; values look like {FIELD_BY_KEY[hint].label}.")
    return MappingDecision(None, MappingStatus.NEEDS_REVIEW, MappingMethod.NONE, 0, note="Header not recognised.")


def suggest_mapping(columns: list[dict]) -> dict[str, dict]:
    """Map a list of {key, header, values} source columns.

    Single-value fields can be claimed once; a weaker competing column is demoted
    to NEEDS_REVIEW so the admin resolves the conflict explicitly.
    """
    decisions = {c["key"]: decide(c.get("header", ""), c.get("values", [])) for c in columns}
    rank = {MappingStatus.MAPPED: 2, MappingStatus.SUGGESTED: 1}
    claimed: dict[str, str] = {}
    for col in columns:
        d = decisions[col["key"]]
        if not d.field or FIELD_BY_KEY[d.field].multi or d.status not in rank:
            continue
        holder = claimed.get(d.field)
        if holder is None:
            claimed[d.field] = col["key"]
            continue
        other = decisions[holder]
        loser_key = col["key"] if (rank[d.status], d.confidence) <= (rank[other.status], other.confidence) else holder
        if loser_key == holder:
            claimed[d.field] = col["key"]
        loser = decisions[loser_key]
        holder_header = next(c.get("header") for c in columns if c["key"] == claimed[d.field])
        decisions[loser_key] = MappingDecision(
            None, MappingStatus.NEEDS_REVIEW, loser.method, loser.confidence, suggestion=loser.field,
            note=f"{FIELD_BY_KEY[loser.field].label} is already mapped to '{holder_header}'.",
        )

    # Subtopic columns without an explicit number get their order from sheet position.
    next_order = 1
    used = {d.order for d in decisions.values() if d.field == "subtopic" and d.order}
    for col in columns:
        d = decisions[col["key"]]
        if d.field == "subtopic" and d.order is None:
            while next_order in used:
                next_order += 1
            d.order = next_order
            used.add(next_order)
    return {k: v.to_dict() for k, v in decisions.items()}


def mapping_problems(mapping: dict[str, dict], columns: list[dict]) -> list[dict]:
    """Session-level problems that block validation from passing."""
    problems: list[dict] = []
    headers = {c["key"]: c.get("header") or c["key"] for c in columns}
    unresolved = [k for k, m in mapping.items() if k in headers and m.get("status") in (MappingStatus.SUGGESTED, MappingStatus.NEEDS_REVIEW)]
    if unresolved:
        problems.append({
            "level": "ERROR", "code": "MAPPING_UNRESOLVED",
            "message": f"{len(unresolved)} column(s) still need a mapping decision: " + ", ".join(f"'{headers[k]}'" for k in unresolved[:5]),
        })
    mapped_fields: dict[str, list[str]] = {}
    for key, m in mapping.items():
        if key in headers and m.get("status") == MappingStatus.MAPPED and m.get("field"):
            mapped_fields.setdefault(m["field"], []).append(key)
    for field, keys in mapped_fields.items():
        if field not in FIELD_BY_KEY:
            problems.append({"level": "ERROR", "code": "MAPPING_INVALID", "message": f"Unknown portal field '{field}'."})
        elif len(keys) > 1 and not FIELD_BY_KEY[field].multi:
            problems.append({
                "level": "ERROR", "code": "MAPPING_DUPLICATE_FIELD",
                "message": f"{FIELD_BY_KEY[field].label} is mapped from more than one column ("
                           + ", ".join(f"'{headers[k]}'" for k in keys) + ").",
            })
    for field in REQUIRED_FIELDS:
        if field not in mapped_fields:
            problems.append({"level": "ERROR", "code": "MAPPING_REQUIRED_MISSING",
                             "message": f"{FIELD_BY_KEY[field].label} must be mapped to a column."})
    for field, label in (("unit_no", "Unit Number"), ("planned_date", "Planned Date"), ("blooms_taxonomy", "Bloom's Taxonomy")):
        if field not in mapped_fields:
            problems.append({"level": "WARNING", "code": "MAPPING_RECOMMENDED_MISSING",
                             "message": f"{label} is not mapped. Lectures will be imported without it."})
    return problems


def detect_header_row(first_row: list[str], body: list[list[str]]) -> bool:
    """Heuristic: does the first pasted row look like column headers?"""
    non_empty = [c for c in first_row if c]
    if not non_empty:
        return False
    recognised = 0
    for cell in non_empty:
        norm = normalize_header(cell)
        if norm in _EXACT_INDEX or norm in ALIAS_INDEX or _subtopic_order(norm)[0]:
            recognised += 1
    if recognised >= 2 or recognised >= max(1, len(non_empty) // 2):
        return True
    # Fallback: a column whose first cell is text while the rest are mostly numbers.
    for col, head in enumerate(first_row):
        if not head or head.replace(".", "", 1).isdigit():
            continue
        below = [r[col] for r in body[:20] if col < len(r) and r[col]]
        if len(below) >= 3 and sum(v.replace(".", "", 1).isdigit() for v in below) / len(below) >= 0.8:
            return True
    return False


def field_catalog() -> list[dict]:
    return [
        {"key": f.key, "label": f.label, "required": f.required, "multi": f.multi, "description": f.description}
        for f in FIELDS
    ]
