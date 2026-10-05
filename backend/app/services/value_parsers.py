"""Parse individual spreadsheet cell values into typed teaching-plan values.

Each parser returns (value, issue) where issue is None or a (level, message)
tuple. Parsers never guess silently: when they normalise something unusual
they say so as a WARNING.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

from app.core.enums import BloomLevel, LectureType

Issue = tuple[str, str] | None  # ("ERROR" | "WARNING", message)

ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10}


def _int_like(value: str) -> int | None:
    v = value.strip()
    if re.fullmatch(r"\d+", v):
        return int(v)
    if re.fullmatch(r"\d+\.0+", v):
        return int(float(v))
    return None


def parse_lecture_no(value: str) -> tuple[int | None, Issue]:
    if not value:
        return None, ("ERROR", "Lecture number is missing.")
    n = _int_like(value)
    if n is None:
        m = re.fullmatch(r"(?:l|lec|lecture)\s*[-.#:]?\s*(\d+)", value.strip(), re.I)
        n = int(m.group(1)) if m else None
    if n is None:
        return None, ("ERROR", f"Lecture number '{value}' is not a whole number.")
    if n <= 0:
        return None, ("ERROR", "Lecture number must be greater than zero.")
    return n, None


def parse_serial(value: str) -> tuple[int | None, Issue]:
    if not value:
        return None, None
    n = _int_like(value)
    if n is None:
        return None, ("WARNING", f"Serial number '{value}' is not numeric and was ignored.")
    return n, None


def parse_unit(value: str) -> tuple[int | None, Issue]:
    if not value:
        return None, ("WARNING", "Unit is missing.")
    v = value.strip().lower()
    n = _int_like(v)
    if n is None:
        m = re.fullmatch(r"(?:unit|module|u|m)\s*[-.#:]?\s*([0-9]+|[ivx]+)", v)
        token = m.group(1) if m else v
        n = _int_like(token) if token.isdigit() else ROMAN.get(token)
    if n is None:
        return None, ("ERROR", f"Unit '{value}' is not a valid unit number (use 1, 2, Unit 3, IV...).")
    if n <= 0 or n > 20:
        return None, ("ERROR", f"Unit {n} is out of range.")
    return n, None


_BLOOM_WORDS = {
    "remember": "K1", "remembering": "K1", "knowledge": "K1",
    "understand": "K2", "understanding": "K2", "comprehension": "K2",
    "apply": "K3", "applying": "K3", "application": "K3",
    "analyse": "K4", "analyze": "K4", "analysing": "K4", "analyzing": "K4", "analysis": "K4",
    "evaluate": "K5", "evaluating": "K5", "evaluation": "K5",
    "create": "K6", "creating": "K6", "synthesis": "K6",
}


def parse_bloom(value: str) -> tuple[str | None, Issue]:
    if not value:
        return None, ("WARNING", "Bloom's taxonomy level is missing.")
    v = value.strip().lower()
    levels: list[str] = []
    for token in re.split(r"[\s,/;&+]+|\band\b", v):
        if not token:
            continue
        m = re.fullmatch(r"(?:k|l|bt|btl|level)?-?([1-6])", token)
        if m:
            levels.append(f"K{m.group(1)}")
        elif token in _BLOOM_WORDS:
            levels.append(_BLOOM_WORDS[token])
    if not levels:
        return None, ("ERROR", f"'{value}' is not a valid Bloom's level (K1-K6).")
    unique = sorted(set(levels))
    chosen = unique[-1]
    if len(unique) > 1:
        return chosen, ("WARNING", f"Several levels given ({', '.join(unique)}); the highest, {chosen}, will be stored.")
    return chosen, None  # "k2", "L2", "Understand" all normalise to K2


_TYPE_WORDS = {
    LectureType.THEORY: {"theory", "th", "t", "l", "lecture", "lec", "class", "regular", "lect"},
    LectureType.PRACTICAL: {"practical", "lab", "p", "pr", "laboratory", "prac", "lab session"},
    LectureType.TUTORIAL: {"tutorial", "tut", "tu"},
    LectureType.REVISION: {"revision", "rev", "recap", "doubt", "doubt session", "doubt clearing"},
    LectureType.ASSESSMENT: {"assessment", "test", "quiz", "exam", "class test", "ct", "evaluation", "viva"},
}


def parse_lecture_type(value: str) -> tuple[str, Issue]:
    if not value:
        return LectureType.THEORY.value, None
    v = re.sub(r"\s+", " ", value.strip().lower())
    for lt, words in _TYPE_WORDS.items():
        if v in words:
            return lt.value, None
    for lt, words in _TYPE_WORDS.items():
        if any(len(w) > 3 and w in v for w in words):
            return lt.value, ("WARNING", f"Lecture type '{value}' was read as {lt.value.title()}.")
    return LectureType.OTHER.value, ("WARNING", f"Lecture type '{value}' is not a standard type; stored as Other.")


_DATE_FORMATS_DAYFIRST = (
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%d.%m.%y",
)
_DATE_FORMATS_MONTHFIRST = ("%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y")
_DATE_FORMATS_UNAMBIGUOUS = (
    "%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
    "%d-%b-%Y", "%d-%b-%y", "%d %b %Y", "%d %B %Y", "%d %b %y", "%d-%B-%Y", "%d %b, %Y", "%d %B, %Y",
    "%b %d %Y", "%B %d %Y", "%b %d, %Y", "%B %d, %Y",
    "%a %d %b %Y", "%A %d %B %Y", "%a, %d %b %Y", "%A, %d %B %Y", "%A, %B %d, %Y", "%a, %b %d, %Y",
)


def parse_date(value: str, *, dayfirst: bool = True) -> tuple[date | None, Issue]:
    if not value:
        return None, ("WARNING", "Planned date is missing - this lecture will not appear in task lists until scheduled.")
    v = value.strip()
    # Excel serial day number pasted as plain text.
    if re.fullmatch(r"\d{5}(\.0+)?", v):
        serial = int(float(v))
        if 30000 <= serial <= 80000:
            return date(1899, 12, 30) + timedelta(days=serial), None
    cleaned = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", v, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned.replace(",", ", ")).replace(" ,", ",").strip()
    cleaned = re.sub(r",\s*", ", ", cleaned)
    formats = _DATE_FORMATS_UNAMBIGUOUS + (_DATE_FORMATS_DAYFIRST if dayfirst else _DATE_FORMATS_MONTHFIRST)
    for candidate in {cleaned, cleaned.replace(",", ""), re.sub(r"\s+", " ", cleaned.replace(",", " "))}:
        for fmt in formats:
            try:
                return datetime.strptime(candidate, fmt).date(), None
            except ValueError:
                continue
    return None, ("ERROR", f"'{value}' is not a recognisable date (use DD/MM/YYYY or YYYY-MM-DD).")


_TIME_RE = re.compile(r"^(\d{1,2})(?:[:.](\d{2}))?(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?$", re.I)
_RANGE_SPLIT = re.compile(r"\s*(?:-|–|—|to)\s*", re.I)


def parse_time(value: str, label: str = "Time") -> tuple[time | None, Issue]:
    if not value:
        return None, None
    v = value.strip().lower().replace("\u00a0", " ")
    m = _TIME_RE.match(v)
    if not m:
        return None, ("ERROR", f"{label} '{value}' is not a valid time (use 10:00 or 10:00 AM).")
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    meridian = (m.group(4) or "").replace(".", "")
    if meridian:
        if not 1 <= hour <= 12:
            return None, ("ERROR", f"{label} '{value}' is not a valid 12-hour time.")
        hour = hour % 12 + (12 if meridian == "pm" else 0)
    if hour > 23 or minute > 59:
        return None, ("ERROR", f"{label} '{value}' is not a valid time.")
    parsed = time(hour, minute)
    if not meridian and hour < 7:
        return parsed, ("WARNING", f"{label} {parsed.strftime('%H:%M')} is outside normal teaching hours - check AM/PM.")
    return parsed, None


def split_time_range(value: str) -> tuple[str, str] | None:
    """'10:00 - 11:00' -> ('10:00', '11:00'). Returns None when the value is not a range."""
    if not value:
        return None
    parts = _RANGE_SPLIT.split(value.strip())
    if len(parts) == 2 and all(parts):
        return parts[0], parts[1]
    return None


_BULLET = re.compile(r"^\s*(?:[-•*●▪◦]|\(?\d{1,2}[.)])\s+")


def split_subtopics(values: list[str]) -> list[str]:
    """Each subtopic cell may itself hold several lines; every non-empty line becomes one subtopic."""
    result: list[str] = []
    for value in values:
        for line in (value or "").split("\n"):
            line = _BULLET.sub("", line).strip()
            if line:
                result.append(line)
    return result
