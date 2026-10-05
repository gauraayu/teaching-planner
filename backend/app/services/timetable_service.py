"""Timing templates and the institution's recurring master timetable.

Two day structures exist (First Year, Second-Fourth Year). They overlap in clock time but number their
lectures differently and each has ITS OWN lunch, so:

  * a lecture number means something only inside its template - every check compares real intervals;
  * lunch blocks only the classes of the year group it belongs to, never the other group;
  * professor, section and room clashes are checked across the whole institution.

One timetable is shared by every role. Admin sees all of it; a professor their own classes; CL/CH and OM
the classes inside their scope. Generate / Edit work on a DRAFT version; Publish replaces the published
one and archives it. Generation is a deterministic greedy constraint pass - no AI, same input, same output.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.enums import ClassType, PlanStatus, Role, RoomType, SlotType, TimetableStatus
from app.core.errors import BusinessRuleViolation, Conflict, NotFound
from app.models import Holiday, Room, TeachingPlan, TimetableEntry, TimetableVersion, TimingSlot, TimingTemplate, User
from app.schemas import requests as rq
from app.services import audit_service, notification_service, scope_service
from app.services import serializers as ser

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
YEARS = ["", "1st Year", "2nd Year", "3rd Year", "4th Year", "5th Year", "6th Year"]


def year_label(semester_number: int) -> str:
    return YEARS[(semester_number + 1) // 2] if 0 < semester_number <= 12 else ""


def _m(t: time) -> int:
    return t.hour * 60 + t.minute


def _hm(t: time) -> str:
    return t.strftime("%H:%M")


def _span(start: time, end: time) -> str:
    return f"{start:%H:%M}–{end:%H:%M}"


# ------------------------------------------------------------------ timing templates

def templates(db: Session, *, active_only: bool = True) -> list[TimingTemplate]:
    stmt = select(TimingTemplate).order_by(TimingTemplate.display_order, TimingTemplate.name)
    if active_only:
        stmt = stmt.where(TimingTemplate.is_active.is_(True))
    return list(db.scalars(stmt).unique())


_FIRST = [("LECTURE", "10:10", "11:00"), ("LECTURE", "11:00", "11:50"), ("LECTURE", "11:50", "12:40"), ("LUNCH", "12:40", "13:20"),
          ("LECTURE", "13:20", "14:10"), ("LECTURE", "14:10", "15:00"), ("LECTURE", "15:00", "15:45"), ("LECTURE", "15:45", "16:30")]
_SENIOR = [("LECTURE", "08:30", "09:20"), ("LECTURE", "09:20", "10:10"), ("LECTURE", "10:10", "11:00"), ("LECTURE", "11:00", "11:50"),
           ("LUNCH", "11:50", "12:30"), ("LECTURE", "12:30", "13:20"), ("LECTURE", "13:20", "14:10"), ("LECTURE", "14:10", "15:00"),
           ("LECTURE", "15:00", "15:45"), ("LECTURE", "15:45", "16:30")]
DEFAULT_TEMPLATES = (
    ("FIRST_YEAR", "First Year", "1st Year", "Semesters I and II. Lunch 12:40-13:20.", [1, 2], _FIRST),
    ("SECOND_TO_FOURTH_YEAR", "Second to Fourth Year", "2nd-4th Year", "Semesters III to VIII. Lunch 11:50-12:30.", [3, 4, 5, 6, 7, 8], _SENIOR),
)


def ensure_templates(db: Session) -> None:
    """The two institutional day structures. The migration creates them; this restores them after a full reset.
    They are ordinary rows afterwards - the admin edits them in Academic Setup."""
    if db.scalar(select(TimingTemplate.id).limit(1)):
        return
    for order, (code, name, short, desc, sems, slots) in enumerate(DEFAULT_TEMPLATES, start=1):
        tpl = TimingTemplate(code=code, name=name, short_name=short, description=desc, semester_numbers=sems, display_order=order)
        number = 0
        for i, (kind, a, b) in enumerate(slots, start=1):
            teaching = kind == "LECTURE"
            number += teaching
            tpl.slots.append(TimingSlot(slot_type=kind, lecture_number=number if teaching else None, start_time=time.fromisoformat(a),
                                        end_time=time.fromisoformat(b), display_order=i, is_teaching_slot=teaching))
        db.add(tpl)
    db.flush()


def template_map(db: Session) -> dict[int, TimingTemplate]:
    """semester number -> the timing template that semester follows (configured on the template)."""
    out: dict[int, TimingTemplate] = {}
    for t in templates(db):
        for n in t.semester_numbers or []:
            out.setdefault(int(n), t)
    return out


def template_view(t: TimingTemplate) -> dict:
    return {
        "id": str(t.id), "code": t.code, "name": t.name, "short_name": t.short_name, "description": t.description,
        "semester_numbers": sorted(t.semester_numbers or []), "is_active": t.is_active,
        "slots": [{"id": str(s.id), "slot_type": s.slot_type, "lecture_number": s.lecture_number, "start": _hm(s.start_time),
                   "end": _hm(s.end_time), "is_teaching_slot": s.is_teaching_slot} for s in t.slots],
    }


def lunch_overlap(tpl: TimingTemplate | None, start: time, end: time) -> TimingSlot | None:
    """The lunch / break of THIS template that the interval runs into, if any. Other templates are irrelevant."""
    if not tpl:
        return None
    for s in tpl.slots:
        if not s.is_teaching_slot and _m(start) < _m(s.end_time) and _m(s.start_time) < _m(end):
            return s
    return None


def lecture_numbers(tpl: TimingTemplate | None, start: time, end: time) -> list[int]:
    """Which of the template's lecture periods an interval occupies (a lab occupies two)."""
    if not tpl:
        return []
    return [s.lecture_number for s in tpl.slots
            if s.is_teaching_slot and s.lecture_number and _m(start) < _m(s.end_time) and _m(s.start_time) < _m(end)]


def save_template(db: Session, admin: User, template_id: uuid.UUID, data: rq.TimingTemplateIn) -> dict:
    tpl = db.get(TimingTemplate, template_id)
    if not tpl:
        raise NotFound("Timing template not found.")
    wanted = set(data.semester_numbers)
    for other in templates(db, active_only=False):
        clash = wanted & set(other.semester_numbers or []) if other.id != tpl.id else set()
        if clash:
            raise Conflict(f"Semester {', '.join(str(n) for n in sorted(clash))} already follows the {other.name} timings. "
                           "A semester can follow only one timing template.", code="SEMESTER_ALREADY_MAPPED")
    ordered = sorted(data.slots, key=lambda s: s.start_time)
    for a, b in zip(ordered, ordered[1:]):
        if b.start_time < a.end_time:
            raise BusinessRuleViolation(f"Periods {a.start_time}–{a.end_time} and {b.start_time}–{b.end_time} overlap.", code="SLOTS_OVERLAP")
    before = template_view(tpl)
    tpl.name, tpl.short_name, tpl.description = data.name, data.short_name, data.description
    tpl.semester_numbers = sorted(wanted)
    tpl.slots.clear()
    db.flush()
    number = 0
    for i, s in enumerate(ordered, start=1):
        teaching = s.slot_type == SlotType.LECTURE
        number += 1 if teaching else 0
        tpl.slots.append(TimingSlot(slot_type=s.slot_type.value, lecture_number=number if teaching else None,
                                    start_time=time.fromisoformat(s.start_time), end_time=time.fromisoformat(s.end_time),
                                    display_order=i, is_teaching_slot=teaching))
    db.flush()
    audit_service.record(db, actor=admin, action="timing_template.saved", entity_type="timing_template", entity_id=tpl.id,
                         summary=f"Updated the {tpl.name} timing template.",
                         old={"semester_numbers": before["semester_numbers"], "slots": [f"{s['slot_type']} {s['start']}-{s['end']}" for s in before["slots"]]},
                         new={"semester_numbers": tpl.semester_numbers, "slots": [f"{s.slot_type} {_hm(s.start_time)}-{_hm(s.end_time)}" for s in tpl.slots]})
    db.commit()
    db.refresh(tpl)
    return template_view(tpl)


# ------------------------------------------------------------------ rooms & holidays

def list_rooms(db: Session) -> list[Room]:
    return list(db.scalars(select(Room).order_by(Room.room_type, Room.name)))


def save_room(db: Session, admin: User, data: rq.RoomIn, room_id: uuid.UUID | None = None) -> Room:
    room = db.get(Room, room_id) if room_id else Room()
    if room is None:
        raise NotFound("Room not found.")
    name = data.name.strip()
    dup = db.scalar(select(Room.id).where(func.lower(Room.name) == name.lower(), Room.id != (room.id if room_id else None)))
    if dup:
        raise Conflict(f"Room {name} already exists.", code="DUPLICATE")
    room.name, room.room_type, room.capacity, room.is_active = name, data.room_type.value, data.capacity, data.is_active
    db.add(room)
    db.flush()
    audit_service.record(db, actor=admin, action="room.saved", entity_type="room", entity_id=room.id, summary=f"Saved room {name}.")
    db.commit()
    return room


def list_holidays(db: Session) -> list[Holiday]:
    return list(db.scalars(select(Holiday).order_by(Holiday.date)))


def save_holiday(db: Session, admin: User, data: rq.HolidayIn, holiday_id: uuid.UUID | None = None) -> Holiday:
    h = db.get(Holiday, holiday_id) if holiday_id else Holiday()
    if h is None:
        raise NotFound("Holiday not found.")
    dup = db.scalar(select(Holiday.id).where(Holiday.date == data.date, Holiday.id != (h.id if holiday_id else None)))
    if dup:
        raise Conflict(f"{data.date:%d %b %Y} is already a holiday.", code="DUPLICATE")
    h.date, h.name = data.date, data.name
    db.add(h)
    db.flush()
    audit_service.record(db, actor=admin, action="holiday.saved", entity_type="holiday", entity_id=h.id,
                         summary=f"Saved holiday {h.name} on {h.date:%d %b %Y}.")
    db.commit()
    return h


def delete_holiday(db: Session, admin: User, holiday_id: uuid.UUID) -> None:
    h = db.get(Holiday, holiday_id)
    if not h:
        raise NotFound("Holiday not found.")
    audit_service.record(db, actor=admin, action="holiday.deleted", entity_type="holiday", entity_id=h.id,
                         summary=f"Removed holiday {h.name} on {h.date:%d %b %Y}.")
    db.delete(h)
    db.commit()


# ------------------------------------------------------------------ versions

def _version(db: Session, status: TimetableStatus) -> TimetableVersion | None:
    return db.scalar(select(TimetableVersion).where(TimetableVersion.status == status.value))


def published_entries(db: Session) -> list[TimetableEntry]:
    v = _version(db, TimetableStatus.PUBLISHED)
    return list(v.entries) if v else []


def _require_draft(db: Session) -> TimetableVersion:
    v = db.scalar(select(TimetableVersion).where(TimetableVersion.status == TimetableStatus.DRAFT.value).with_for_update(of=TimetableVersion))
    if not v:
        raise Conflict("There is no draft timetable. Choose Edit Schedule or Generate Schedule first.", code="NO_DRAFT")
    return v


def _brief(v: TimetableVersion | None) -> dict | None:
    if not v:
        return None
    return {"id": str(v.id), "status": v.status, "version_number": v.version_number, "note": v.note,
            "entry_count": len(v.entries), "published_at": ser._iso(v.published_at),
            "published_by": ser.user_brief(v.published_by), "updated_at": ser._iso(v.updated_at)}


# ------------------------------------------------------------------ entries & conflicts

def entry_view(e: TimetableEntry, tmap: dict[int, TimingTemplate]) -> dict:
    plan = e.teaching_plan
    prof = e.effective_professor
    tpl = tmap.get(plan.semester.number)
    return {
        "id": str(e.id), "plan_id": str(plan.id), "weekday": e.weekday, "day": DAYS[e.weekday],
        "start": _hm(e.start_time), "end": _hm(e.end_time), "room": e.room or plan.room, "class_type": e.class_type,
        "professor": {"id": str(prof.id), "full_name": prof.full_name}, "is_substitute": e.professor_id is not None,
        "subject": {"id": str(plan.subject_id), "code": plan.subject.code, "name": plan.subject.name, "short_name": plan.subject.short_name},
        "semester": plan.semester.name, "semester_number": plan.semester.number, "semester_id": str(plan.semester_id),
        "section": plan.section.name, "section_id": str(plan.section_id), "year": year_label(plan.semester.number),
        "academic_year": plan.academic_year.name, "branch_code": plan.branch.code,
        "plan_status": plan.status, "template": tpl.code if tpl else None,
        "lecture_numbers": lecture_numbers(tpl, e.start_time, e.end_time),
    }


@dataclass(frozen=True)
class Booking:
    """One class occupying a professor, a section and maybe a room for a real time interval on a weekday."""
    key: str                 # entry id (or any stable id) - reported back so the UI can mark the cell
    weekday: int
    start: time
    end: time
    professor_id: str
    professor_name: str
    section_id: str
    section_label: str       # "Sem V-A"
    room: str | None
    label: str               # "DSA · Sem V-A"
    group: str               # timing template name, e.g. "First Year"


def booking(e: TimetableEntry, tmap: dict[int, TimingTemplate]) -> Booking:
    plan = e.teaching_plan
    prof = e.effective_professor
    tpl = tmap.get(plan.semester.number)
    sec = f"{plan.semester.name.replace('Semester', 'Sem')}-{plan.section.name}"
    return Booking(key=str(e.id), weekday=e.weekday, start=e.start_time, end=e.end_time, professor_id=str(prof.id),
                   professor_name=prof.full_name, section_id=str(plan.section_id), section_label=sec,
                   room=((e.room or plan.room or "").strip() or None), label=f"{plan.subject.short_name or plan.subject.code} · {sec}",
                   group=tpl.name if tpl else "No timing template")


def overlap(a: Booking, b: Booking) -> tuple[time, time] | None:
    """new_start < existing_end AND new_end > existing_start, on the same weekday. Returns the shared interval."""
    if a.weekday != b.weekday or not (_m(a.start) < _m(b.end) and _m(b.start) < _m(a.end)):
        return None
    return max(a.start, b.start), min(a.end, b.end)


def clash_messages(a: Booking, b: Booking) -> list[dict]:
    shared = overlap(a, b)
    if not shared:
        return []
    out = []
    detail = (f"{a.label} ({a.group}) {_span(a.start, a.end)} and {b.label} ({b.group}) {_span(b.start, b.end)} on {DAYS[a.weekday]}. "
              f"Overlap: {_span(*shared)}.")

    def add(kind: str, text: str) -> None:
        out.append({"kind": kind, "level": "ERROR", "weekday": a.weekday, "keys": [a.key, b.key], "message": f"{text} {detail}"})

    if a.professor_id == b.professor_id:
        add("PROFESSOR", f"{a.professor_name} has overlapping classes:")
    if a.section_id == b.section_id:
        add("SECTION", f"{a.section_label} cannot attend two classes at once:")
    if a.room and b.room and a.room.lower() == b.room.lower():
        add("ROOM", f"Room {a.room} is double-booked:")
    return out


def find_conflicts(entries: list[TimetableEntry], tmap: dict[int, TimingTemplate]) -> list[dict]:
    out: list[dict] = []
    books = [booking(e, tmap) for e in entries]
    by_day: dict[int, list[Booking]] = defaultdict(list)
    for b in books:
        by_day[b.weekday].append(b)
    for day in sorted(by_day):
        row = sorted(by_day[day], key=lambda b: (b.start, b.end, b.key))
        for i, a in enumerate(row):
            for b in row[i + 1:]:
                if _m(b.start) >= _m(a.end):
                    break
                out.extend(clash_messages(a, b))
    for e, b in zip(entries, books):
        tpl = tmap.get(e.teaching_plan.semester.number)
        if not tpl:
            out.append({"kind": "NO_TEMPLATE", "level": "WARNING", "weekday": e.weekday, "keys": [b.key],
                        "message": f"{b.label}: {e.teaching_plan.semester.name} is not mapped to a timing template, so its lunch cannot be checked."})
            continue
        lunch = lunch_overlap(tpl, e.start_time, e.end_time)
        if lunch:
            out.append({"kind": "LUNCH", "level": "ERROR", "weekday": e.weekday, "keys": [b.key],
                        "message": f"{b.label} {_span(e.start_time, e.end_time)} on {DAYS[e.weekday]} runs into the {tpl.name} "
                                   f"{lunch.slot_type.lower()} ({_span(lunch.start_time, lunch.end_time)})."})
        teaching = [s for s in tpl.slots if s.is_teaching_slot]
        if teaching and (_m(e.start_time) < _m(teaching[0].start_time) or _m(e.end_time) > _m(teaching[-1].end_time)):
            out.append({"kind": "OUTSIDE_HOURS", "level": "WARNING", "weekday": e.weekday, "keys": [b.key],
                        "message": f"{b.label} {_span(e.start_time, e.end_time)} is outside the {tpl.name} teaching day "
                                   f"({_span(teaching[0].start_time, teaching[-1].end_time)})."})
    return out


def _visible(viewer: User, entries: list[TimetableEntry]) -> list[TimetableEntry]:
    role = viewer.role_code
    if role == Role.ADMIN:
        return entries
    if role == Role.PROFESSOR:
        return [e for e in entries if e.effective_professor.id == viewer.id]
    return [e for e in entries if scope_service.covers(viewer, e.teaching_plan)]


def view(db: Session, viewer: User, *, draft: bool = False) -> dict:
    """The one shared timetable, filtered for whoever asks. Only an admin can see the draft."""
    is_admin = viewer.role_code == Role.ADMIN
    published = _version(db, TimetableStatus.PUBLISHED)
    working = _version(db, TimetableStatus.DRAFT) if is_admin else None
    showing = working if (draft and working) else published
    tmap = template_map(db)
    all_entries = list(showing.entries) if showing else []
    entries = sorted(_visible(viewer, all_entries), key=lambda e: (e.weekday, e.start_time, e.teaching_plan.subject.code))
    conflicts = find_conflicts(all_entries, tmap) if (is_admin and showing) else []
    return {
        "showing": showing.status if showing else None,
        "published": _brief(published), "draft": _brief(working),
        "templates": [template_view(t) for t in templates(db)],
        "entries": [entry_view(e, tmap) for e in entries],
        "conflicts": conflicts,
        "can_publish": bool(working) and not any(c["level"] == "ERROR" for c in conflicts) if (draft and working) else False,
        "scope": scope_service.describe(db, viewer) if viewer.role_code in (Role.CL_CH, Role.OM) else None,
        "today_weekday": clock.today().weekday(),
    }


# ------------------------------------------------------------------ draft editing

def start_draft(db: Session, admin: User) -> dict:
    """Edit Schedule: a working copy of the published timetable. Nothing changes for anyone until Publish."""
    if not _version(db, TimetableStatus.DRAFT):
        draft = TimetableVersion(status=TimetableStatus.DRAFT.value, created_by_id=admin.id)
        db.add(draft)
        db.flush()
        for e in published_entries(db):
            db.add(TimetableEntry(version_id=draft.id, teaching_plan_id=e.teaching_plan_id, professor_id=e.professor_id,
                                  weekday=e.weekday, start_time=e.start_time, end_time=e.end_time, room=e.room, class_type=e.class_type))
        audit_service.record(db, actor=admin, action="timetable.draft_started", entity_type="timetable_version", entity_id=draft.id,
                             summary="Started editing the master timetable (draft).")
        db.commit()
    db.expire_all()
    return view(db, admin, draft=True)


def discard_draft(db: Session, admin: User) -> dict:
    draft = _require_draft(db)
    audit_service.record(db, actor=admin, action="timetable.draft_discarded", entity_type="timetable_version", entity_id=draft.id,
                         summary=f"Discarded the draft master timetable ({len(draft.entries)} classes).")
    db.delete(draft)
    db.commit()
    db.expire_all()
    return view(db, admin)


def _plan_for_entry(db: Session, plan_id: uuid.UUID) -> TeachingPlan:
    plan = db.get(TeachingPlan, plan_id)
    if not plan or plan.status == PlanStatus.ARCHIVED:
        raise NotFound("Choose a teaching plan that is not archived.")
    return plan


def save_entry(db: Session, admin: User, data: rq.TimetableEntryIn, entry_id: uuid.UUID | None = None) -> dict:
    draft = _require_draft(db)
    plan = _plan_for_entry(db, data.teaching_plan_id)
    start, end = time.fromisoformat(data.start_time), time.fromisoformat(data.end_time)
    if end <= start:
        raise BusinessRuleViolation("End time must be after start time.", code="TIMES_ORDERED")
    professor_id = None
    if data.professor_id and data.professor_id != plan.professor_id:
        prof = db.get(User, data.professor_id)
        if not prof or prof.role_code != Role.PROFESSOR or not prof.is_active:
            raise BusinessRuleViolation("Choose an active professor account.", code="INVALID_FACULTY")
        professor_id = prof.id
    entry = db.get(TimetableEntry, entry_id) if entry_id else TimetableEntry(version_id=draft.id)
    if entry is None or entry.version_id != draft.id:
        raise NotFound("Class not found in the draft timetable.")
    before = None if not entry_id else f"{DAYS[entry.weekday]} {_span(entry.start_time, entry.end_time)} {entry.room or ''}".strip()
    entry.teaching_plan_id, entry.professor_id, entry.weekday = plan.id, professor_id, data.weekday
    room = (data.room or "").strip() or None
    if room:  # "c-204" and "C-204" are the same room: store the registered spelling
        room = db.scalar(select(Room.name).where(func.lower(Room.name) == room.lower())) or room
    entry.start_time, entry.end_time, entry.room, entry.class_type = start, end, room, data.class_type.value
    db.add(entry)
    db.flush()
    label = f"{plan.subject.short_name or plan.subject.code} {plan.semester.name.replace('Semester', 'Sem')}-{plan.section.name}"
    after = f"{DAYS[entry.weekday]} {_span(start, end)} {entry.room or ''}".strip()
    audit_service.record(db, actor=admin, action="timetable.entry_changed" if entry_id else "timetable.entry_added",
                         entity_type="timetable_entry", entity_id=entry.id,
                         summary=f"{'Moved' if entry_id else 'Added'} {label} in the draft timetable: {after}.",
                         old={"slot": before} if before else None, new={"slot": after}, scope_type="teaching_plan", scope_id=plan.id)
    db.commit()
    db.expire_all()
    return view(db, admin, draft=True)


def delete_entry(db: Session, admin: User, entry_id: uuid.UUID) -> dict:
    draft = _require_draft(db)
    entry = db.get(TimetableEntry, entry_id)
    if not entry or entry.version_id != draft.id:
        raise NotFound("Class not found in the draft timetable.")
    plan = entry.teaching_plan
    audit_service.record(db, actor=admin, action="timetable.entry_removed", entity_type="timetable_entry", entity_id=entry.id,
                         summary=f"Removed {plan.subject.short_name or plan.subject.code} {DAYS[entry.weekday]} "
                                 f"{_span(entry.start_time, entry.end_time)} from the draft timetable.",
                         scope_type="teaching_plan", scope_id=plan.id)
    db.delete(entry)
    db.commit()
    db.expire_all()
    return view(db, admin, draft=True)


# ------------------------------------------------------------------ generation

class _Busy:
    """Who and what is taken, by weekday. All checks are on clock intervals."""

    def __init__(self) -> None:
        self.by: dict[tuple[str, str], list[tuple[int, int, int]]] = defaultdict(list)

    def free(self, kind: str, key: str | None, day: int, start: time, end: time) -> bool:
        if not key:
            return True
        return not any(d == day and _m(start) < e and s < _m(end) for d, s, e in self.by[(kind, key.lower())])

    def take(self, kind: str, key: str | None, day: int, start: time, end: time) -> None:
        if key:
            self.by[(kind, key.lower())].append((day, _m(start), _m(end)))


def _place(db: Session, draft: TimetableVersion, plans: list[TeachingPlan], default_days: list[int]) -> tuple[int, list[dict]]:
    """Put each plan's missing weekly classes on free periods of its own year group. Deterministic: plans, days,
    periods and rooms are always tried in the same order. Classes already in `draft` stay where they are."""
    tmap = template_map(db)
    busy = _Busy()
    have: dict[tuple[uuid.UUID, str], int] = defaultdict(int)         # classes each plan already has, by type
    plan_days: dict[uuid.UUID, set[int]] = defaultdict(set)           # days a plan already meets
    section_load: dict[tuple[uuid.UUID, int], int] = defaultdict(int)  # classes a section has per day
    day_use: dict[tuple[uuid.UUID, int], int] = defaultdict(int)      # classes a plan has per day

    def book(plan: TeachingPlan, professor_id: uuid.UUID, day: int, start: time, end: time, room: str | None, kind: str) -> None:
        busy.take("prof", str(professor_id), day, start, end)
        busy.take("section", str(plan.section_id), day, start, end)
        busy.take("room", room, day, start, end)
        have[(plan.id, "LAB" if kind == ClassType.LAB else "CLASS")] += 1
        plan_days[plan.id].add(day)
        section_load[(plan.section_id, day)] += 1
        day_use[(plan.id, day)] += 1

    for e in draft.entries:
        book(e.teaching_plan, e.effective_professor.id, e.weekday, e.start_time, e.end_time, e.room or e.teaching_plan.room, e.class_type)

    rooms = [r for r in list_rooms(db) if r.is_active]
    classrooms = [r.name for r in rooms if r.room_type == RoomType.CLASSROOM]
    labs = [r.name for r in rooms if r.room_type == RoomType.LAB]
    # Hardest first: labs need two free periods in a row, then the subjects that meet most often.
    plans = sorted(plans, key=lambda p: (-p.labs_per_week, -p.classes_per_week, p.semester.number, p.subject.code, p.section.name))
    placed, unplaced = 0, []

    def pick_room(preferred: str | None, pool: list[str], day: int, start: time, end: time) -> tuple[bool, str | None]:
        for name in ([preferred] if preferred else []) + [r for r in pool if r != preferred]:
            if busy.free("room", name, day, start, end):
                return True, name
        return (not preferred and not pool), None  # no rooms configured at all: schedule without one

    for plan in plans:
        tpl = tmap.get(plan.semester.number)
        label = f"{plan.subject.short_name or plan.subject.code} {plan.semester.name.replace('Semester', 'Sem')}-{plan.section.name}"
        if not tpl:
            unplaced.append({"plan_id": str(plan.id), "label": label, "missing": plan.classes_per_week + plan.labs_per_week,
                             "reason": f"{plan.semester.name} is not mapped to a timing template."})
            continue
        days = sorted(set(plan.sprint_plan.working_days)) if plan.sprint_plan and plan.sprint_plan.working_days else sorted(set(default_days))
        periods = [s for s in tpl.slots if s.is_teaching_slot]
        pairs = [(a, b) for a, b in zip(periods, periods[1:]) if a.end_time == b.start_time]  # never across lunch
        prof = str(plan.professor_id)

        def day_order() -> list[int]:
            # spread a subject over the week first (fewest classes of this subject), then the lighter days of the section
            return sorted(days, key=lambda d: (day_use[(plan.id, d)], section_load[(plan.section_id, d)], d))

        def place(kind: str, spans: list[tuple[time, time]], preferred: str | None, pool: list[str]) -> bool:
            for day in day_order():
                for start, end in spans:
                    if not (busy.free("prof", prof, day, start, end) and busy.free("section", str(plan.section_id), day, start, end)):
                        continue
                    ok, room = pick_room(preferred, pool, day, start, end)
                    if not ok:
                        continue
                    db.add(TimetableEntry(version_id=draft.id, teaching_plan_id=plan.id, weekday=day, start_time=start, end_time=end,
                                          room=room, class_type=kind))
                    book(plan, plan.professor_id, day, start, end, room, kind)
                    return True
            return False

        missing = 0
        for _ in range(max(0, plan.labs_per_week - have[(plan.id, "LAB")])):
            ok = place(ClassType.LAB.value, [(a.start_time, b.end_time) for a, b in pairs], plan.lab_room, labs)
            placed, missing = placed + ok, missing + (not ok)
        for _ in range(max(0, plan.classes_per_week - have[(plan.id, "CLASS")])):
            ok = place(ClassType.THEORY.value, [(s.start_time, s.end_time) for s in periods], plan.room, classrooms)
            placed, missing = placed + ok, missing + (not ok)
        if missing:
            unplaced.append({"plan_id": str(plan.id), "label": label, "missing": missing,
                             "reason": f"No free period where {plan.professor.full_name}, the section and a room are all available."})
    return placed, unplaced


def generate(db: Session, admin: User, data: rq.TimetableGenerate) -> dict:
    """Build a DRAFT weekly pattern from the subject allocations. Never publishes."""
    days = sorted(set(data.days)) or [0, 1, 2, 3, 4]
    draft = _version(db, TimetableStatus.DRAFT)
    if draft and data.replace:
        db.delete(draft)
        db.flush()
        draft = None
    if not draft:
        draft = TimetableVersion(status=TimetableStatus.DRAFT.value, created_by_id=admin.id)
        db.add(draft)
        db.flush()
        if not data.replace:
            for e in published_entries(db):
                db.add(TimetableEntry(version_id=draft.id, teaching_plan_id=e.teaching_plan_id, professor_id=e.professor_id,
                                      weekday=e.weekday, start_time=e.start_time, end_time=e.end_time, room=e.room, class_type=e.class_type))
            db.flush()
            db.refresh(draft)
    plans = list(db.scalars(select(TeachingPlan).where(
        TeachingPlan.status != PlanStatus.ARCHIVED, (TeachingPlan.classes_per_week > 0) | (TeachingPlan.labs_per_week > 0))).unique())
    placed, unplaced = _place(db, draft, plans, days)
    audit_service.record(db, actor=admin, action="timetable.generated", entity_type="timetable_version", entity_id=draft.id,
                         summary=f"Generated a draft master timetable: {placed} classes placed"
                                 + (f", {sum(u['missing'] for u in unplaced)} could not be placed." if unplaced else "."),
                         new={"days": [DAYS[d] for d in days], "replace": data.replace, "plans": len(plans)})
    db.commit()
    db.expire_all()
    return view(db, admin, draft=True) | {"generation": {"placed": placed, "plans": len(plans), "unplaced": unplaced}}


def rebuild_pattern(db: Session, admin: User, plans: list[TeachingPlan], *, drop: list[uuid.UUID] | None = None) -> tuple[int, list[dict]]:
    """The weekly class pattern behind the sprint plans (no page of its own). Re-places the given subjects around
    everything else that is already scheduled, removes `drop`, and makes the result current. Does not commit."""
    gone = {p.id for p in plans} | set(drop or [])
    old_draft = _version(db, TimetableStatus.DRAFT)
    if old_draft:
        db.delete(old_draft)
        db.flush()
    current = _version(db, TimetableStatus.PUBLISHED)
    draft = TimetableVersion(status=TimetableStatus.DRAFT.value, created_by_id=admin.id)
    db.add(draft)
    db.flush()
    for e in (current.entries if current else []):
        if e.teaching_plan_id not in gone and e.teaching_plan.status != PlanStatus.ARCHIVED:
            db.add(TimetableEntry(version_id=draft.id, teaching_plan_id=e.teaching_plan_id, professor_id=e.professor_id,
                                  weekday=e.weekday, start_time=e.start_time, end_time=e.end_time, room=e.room, class_type=e.class_type))
    db.flush()
    db.refresh(draft)
    placed, unplaced = _place(db, draft, plans, [0, 1, 2, 3, 4, 5])
    db.flush()
    number = (db.scalar(select(func.max(TimetableVersion.version_number))) or 0) + 1
    if current:
        current.status = TimetableStatus.ARCHIVED.value
        db.flush()
    draft.status, draft.version_number, draft.note = TimetableStatus.PUBLISHED.value, number, "Weekly pattern of the sprint plans"
    draft.published_by_id, draft.published_at = admin.id, clock.now_utc()
    db.flush()
    db.expire(draft, ["entries"])
    return placed, unplaced


# ------------------------------------------------------------------ publish

def publish(db: Session, admin: User, data: rq.TimetablePublish) -> dict:
    draft = _require_draft(db)
    tmap = template_map(db)
    blocking = [c for c in find_conflicts(list(draft.entries), tmap) if c["level"] == "ERROR"]
    if blocking:
        raise Conflict(f"Schedule conflict: {blocking[0]['message']}" + (f" ({len(blocking) - 1} more.)" if len(blocking) > 1 else "")
                       + " Resolve every conflict, then publish.", code="SCHEDULE_CONFLICT", details={"conflicts": blocking})
    if not draft.entries:
        raise BusinessRuleViolation("The draft timetable is empty. Add classes or generate the schedule first.", code="TIMETABLE_EMPTY")
    previous = _version(db, TimetableStatus.PUBLISHED)
    number = (db.scalar(select(func.max(TimetableVersion.version_number))) or 0) + 1
    if previous:
        previous.status = TimetableStatus.ARCHIVED.value
        db.flush()
    draft.status, draft.version_number, draft.note = TimetableStatus.PUBLISHED.value, number, data.note
    draft.published_by_id, draft.published_at = admin.id, clock.now_utc()
    audit_service.record(db, actor=admin, action="timetable.published", entity_type="timetable_version", entity_id=draft.id,
                         summary=f"Published master timetable v{number} with {len(draft.entries)} weekly classes.",
                         new={"version": number, "classes": len(draft.entries), "note": data.note})
    counts: dict[uuid.UUID, int] = defaultdict(int)
    for e in draft.entries:
        counts[e.effective_professor.id] += 1
    for pid, n in counts.items():
        notification_service.notify(db, pid, kind="timetable.published", title="Master timetable published",
                                    body=f"Timetable v{number}: you have {n} class{'es' if n != 1 else ''} in a normal week.",
                                    link="/professor/schedule")
    db.commit()
    db.expire_all()
    return view(db, admin)


def history(db: Session) -> list[dict]:
    rows = db.scalars(select(TimetableVersion).where(TimetableVersion.status != TimetableStatus.DRAFT.value)
                      .order_by(TimetableVersion.version_number.desc())).unique()
    return [_brief(v) for v in rows]
