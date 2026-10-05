# Academic Teaching Plan, Execution & Verification Management Portal

Replaces the spreadsheet-based teaching-plan workflow:

- **Admin** creates or imports the semester teaching plan once.
- **Professor** sees scheduled lectures as tasks and records execution only.
- **OM (Operations Manager)** records the professor's actual classroom entry and exit, with a mandatory reason when the entry is late.
- **CL/CH → OM** verify each submitted lecture record: CL/CH (one role) gives the academic verification, OM the final one.
- **Admin** creates every Professor, CL/CH and OM account, and decides what each CL/CH and OM account may see (its scope).
- Progress, delay, verification and audit views are computed live.

```
ADMIN creates schedule ─┬─► OM live class check (entry 10:07, exit 11:02, delay 7 min)
                        └─► PROFESSOR teaches, updates topic / notes / assignment
                                      │
                             CL/CH verifies ─► OM final verify ─► FINAL VERIFIED
```

| Layer | Stack |
|---|---|
| Frontend | **Next.js 16 (App Router)**, React 19, TypeScript, Tailwind CSS v4, TanStack Table, React Hook Form + Zod, Lucide, Axios |
| Backend | Python 3.11, FastAPI, Pydantic v2, PyMongo, SQLAlchemy 2 (in-process working copy), Pandas, OpenPyXL, RapidFuzz |
| Database | MongoDB Atlas: one collection per entity, `_id` = the record's UUID |

---

## Run it locally

Prerequisites: Python 3.11+, Node 20+, a MongoDB Atlas cluster (the free tier is enough).

```bash
# 1. Database: create a MongoDB Atlas cluster, a database user, allow your IP under Network Access,
#    and copy the connection string (Connect → Drivers).

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                 # set MONGODB_URI (Atlas connection string) and SECRET_KEY
python -m scripts.seed               # demo: 9 accounts, 5 sprint plans (one per class), 10 subjects
                                     #   --empty  only the demo accounts   --full  large demo dataset   --reset  wipe first
uvicorn app.main:app --reload --port 8000   # loads the data from Atlas on start
# API docs: http://localhost:8000/api/docs

# 3. Frontend (new terminal)
cd frontend
npm install
npm run dev                          # http://localhost:3000 (Next.js proxies /api/* to :8000)
```

Sign in with an email, username or employee ID and a password. The seed creates these development accounts (passwords are stored hashed): `admin / Admin@123`, `professor1`, `professor2`, `professor3` / `Professor@123`, `clch1 / CLCH@123`, `om1 / OM@123`. Set `DEMO_AUTH_ENABLED=false` and remove them for real use.

| Portal | Username | Password |
| --- | --- | --- |
| Admin | `admin` | `Admin@123` |
| Professor | `professor1` … `professor6` | `Professor@123` |
| CL/CH | `clch1` | `CLCH@123` |
| OM | `om1` | `OM@123` |

While `DEMO_AUTH_ENABLED=true` the sign-in page shows these under the form. Set it to `false` for real use and change (or deactivate) the demo accounts. Every other account is created by the admin in **User Management**.

### Tests

```bash
cd backend && pytest                 # 134 tests: sprint revisions, carry-forward, live class, parser, mapping, alignment, validation, transactions, permissions, sign-in and accounts, scopes, allocation and schedule conflicts, CL/CH→OM order, OM timing rules
cd frontend && npm test              # clipboard TSV parser (Vitest)
cd frontend && npm run build         # Next.js production build (includes type-check)
```

Backend tests need no database server: they run the real application against an in-process stand-in for MongoDB (mongomock) and check, after every test module has run, that each collection matches the application's state document for document.

---

## Semester plan → weekly sprint → live class

```
ADMIN imports the semester master plan once ──► published = v1 for every week
        │
  every week: Weekly Sprint Plan → Start sprint meeting update (DRAFT, invisible to professors)
        │        edit / move / reassign / cancel / add lecture, place carry-forward items (reason required)
        │        Review changes → Publish weekly revision (v2, v3 …, earlier versions kept)
        ▼
PROFESSOR sees master plan + latest published revision; one "Sprint Plan updated" notification
        │   5-minute alert → Start Class (optional check-in / photo) → topics, notes, assignment, photos → End Class → Submit
        ▼
OM records official entry / exit (separate from the professor's start / end) ─► CL/CH → OM final verify
        ▼
Partially completed / not conducted topics appear as CARRY-FORWARD in the next sprint meeting; the admin decides where they go.
```

- **Draft isolation.** `sprint_revisions` (DRAFT/PUBLISHED) + `sprint_revision_items` (before/after diff, reason). Nothing touches `lectures` / `lecture_schedules` until publish; publish applies the diffs in one transaction, stores the master values once in `lectures.master_snapshot`, audits every change.
- **Three sets of times, never merged:** schedule (`lecture_schedules`), professor's Start/End (`lecture_progress.professor_started_at/ended_at`), OM's entry/exit (`class_sessions`). All written from the server clock.
- **Alerts.** `providers/ScheduleNotificationProvider` (mounted in the app shell) polls `GET /api/schedule/today`, syncs the display clock to the server and raises each class alert once (localStorage + server-side dedupe in the notification history). Swap the polling for WebSocket/SSE there later.
- **Class photos.** `POST /api/lectures/{id}/evidence`: JPG/PNG/WebP checked from the file bytes, ≤ 5 MB, server-generated key. Stored in `LOCAL_UPLOAD_DIR` (or the S3 bucket when configured); the database keeps URL + metadata only. On hosts with an ephemeral disk, configure the bucket.
- **Endpoints.** `/api/admin/sprint-plan/{week, revisions, revisions/{id}/lectures…, …/changes, …/publish, history, carry-forward/{lecture_id}}`, `/api/professor/sprint-plan[/history|/{revision_id}/changes]`, `/api/lectures/{id}/{start,end,evidence}`, `/api/schedule/{today, alerts/{lecture_id}}`.

## Semester sprint plan → weekly sprint plans → schedule → verification

There is no separate master timetable. One **Semester Sprint Plan** is the source of every schedule:

1. **Create Sprint Plan** (`/admin/sprint-plans`): name, academic year, **start date, end date**, working days. The plan page shows the calendar arithmetic (weeks, working days, holidays, teaching days).
2. **Add subjects**: subject + semester/section + professor + **weekly sessions** (stored per subject, never hard-coded per year) + preferred room. Import each subject's topics with the existing spreadsheet import (full-table or column paste; no dates needed).
3. **Generate Semester Sprint**: works out the weekly periods of every subject on its own year group's timing template (professor, room and section free at that real time, never in its own lunch), then dates every topic in lecture order until the end date. Shows required weekly pace, projected completion and **At risk** subjects; nothing is changed automatically.
4. **Weekly Sprint Plan** (`/admin/sprint-plan`) is the institutional timetable of a week: Timetable view (all professors, both year groups) and an Excel-like Table view. A week reaches professors, CL/CH and OM only after **Publish**.
5. **Make Weekly Sprint Plan**: next week's draft from what was actually taught: unfinished subtopics and not-conducted classes come first as carry-forward, the remaining topics move on in order.
6. Professor **My Schedule** → Open class → tick subtopics, notes/assignment/recording links → Send for verification → **CL/CH** verify or request correction → **OM** Clock In / Clock Out (server time), delay reason, Final Verify.

Timing templates (First Year, Second to Fourth Year, each with its own lunch), rooms and holidays are under Admin → Academic Setup. Conflicts always compare real intervals (`new_start < existing_end AND new_end > existing_start`).

Deleting a sprint plan is allowed only while nothing in it was published or recorded; otherwise it is archived and every academic record is kept.

## What is in the seed

The default seed has one admin, six professors, one CL/CH and one OM, and five sprint plans (one per class: Sem I-A, I-B, III-A, V-A, VII-A) with ten subjects, so the weekly timetable shows several professors teaching at the same time on both year-group timings. Last week is taught (records at different verification stages, one unfinished subtopic), this week is published, next week is drafted with the carry-forward first. One spare subject (CS-502) is left to try "Add subject → Import topics → Regenerate". `--full` seeds the large dataset the test-suite uses.

- Academic year 2026–27, Semesters III / V / VII (V is current), CSE and CSE-AIML branches, five sections, nine subjects.
- Users: Rajesh Verma (Admin), Dr. Ananya Sharma (Professor), Prof. Vikram Joshi (CL/CH), Sanjay Kulkarni (OM), plus four more professors.
- OM timing records for past classes (about one in five delayed, with reasons), today's finished/running classes, records waiting for OM final verification, one OM correction and a few classes with no timing record.
- Seven published plans (DSA in two sections, DBMS in two branches, OS, ML, CN), each with a classroom, created by **pasting TSV through the real import engine**, with execution history relative to today: completed, partial, delayed, rescheduled, submitted, CL/CH-verified, final-verified and one open correction request.
- One draft plan (Theory of Computation) with a half-finished column-by-column import to resume.

---

## Architecture

```
backend/app
  api/           thin routers (auth, academic, teaching_plans, imports, professor, verification, operations, reports)
  core/          config, enums (single source of every status), permissions matrix, session tokens, errors, clock
  models/        SQLAlchemy models: academic, teaching_plan, progress, verification, import_session, audit
  schemas/       request bodies (extra="forbid" everywhere)
  services/      business logic
    import_parsing.py     clipboard/xlsx/csv -> Grid (blank cells preserved)
    mapping_service.py    normalise -> exact -> alias -> RapidFuzz suggestion -> admin confirms
    value_parsers.py      lecture no, unit (incl. roman), Bloom (K/L/BT/words), dates (day-first), times, subtopics
    validation_service.py canonical rows + row/import-level issues
    import_service.py     session lifecycle, column-wise alignment, undo, preview edits, transactional commit
    professor_service.py  derived task lists, execution rules, submission
    verification_service.py CL/CH -> OM chain, corrections, resubmission rounds
    user_service.py         sign-in, admin user management, password hashing calls
    scope_service.py        which plans a CL/CH or OM account may see (one rule for lists and actions)
    conflict_service.py     professor / room clashes across published classes
    operations_service.py OM: derived class state, entry/exit recording, delay rule, records and reports
    report_service.py     metric definitions and reports
scripts/seed.py

frontend/                 Next.js 16, App Router
  next.config.ts          rewrites /api/* -> FastAPI (API_PROXY_TARGET), so the browser sees one origin
  src/app/                routes only: layout.tsx, login/, admin/*, professor/*, verification/*, om/* (+ [planId], [lectureId]…)
                          each area has a layout.tsx = role guard + AppShell
  src/lib/router.tsx      Link / NavLink / useNavigate / useParams / useSearchParams over next/navigation
  src/components/         ui (Button, Badge, Dialog, Menu, Tabs…), layout (AppShell, PageHeader), tables, forms, feedback, domain
  src/app/globals.css     the design tokens: every colour in the product is defined here and nowhere else
  src/features/           auth, admin, academic-setup, teaching-plans, imports (parsers + wizard steps), professor, verification, reports
  src/features/om/        components/ (OperationsTable, LiveClassCard, RecordEntry/ExitDialog, DelayReason, FinalVerificationPanel…),
                          pages/, hooks/useOmDay, services/omApi, types/om.types
  src/services/api.ts     axios client with one normalised ApiError
  src/types/domain.ts     mirrors backend enums
```

### Key design decisions

**Three kinds of data, three owners.** Master plan (`teaching_plans`, `lectures`, `lecture_subtopics`, `lecture_schedules`) is Admin-owned. Execution (`lecture_progress`, `lecture_subtopic_progress`, `lecture_materials`, `assignments`) is Professor-owned. Verification (`verifications`) is owned by CL/CH and OM. A professor's update body is a Pydantic model with `extra="forbid"`, so sending `content_topic` is rejected with 422, and the lecture-correction endpoint requires `plans.manage` (403 for professors). Both are tested.

**One import engine, three inputs.** Full-table paste, column-by-column paste and Excel/CSV upload all become the same list of *source columns*; mapping, validation, preview and commit never know where the data came from. Draft data lives in `import_sessions.draft_data` (JSONB) and is discarded into normalised tables on commit.

**Rows never shift.** Blank cells and blank rows keep their index in both parsers (Python and the identical TypeScript one used for instant feedback). Column-wise imports align strictly by row index. A column whose length differs is *not* stored: the API returns `MISMATCH` with expected/received/difference and a side-by-side alignment, and the admin must choose *Continue with empty values* (pads at the end), *Extend table*, or re-paste. Undo restores the previous snapshot.

**Mapping is deterministic, not "AI".** Header normalisation (`Content_Topic`, `CONTENT-TOPIC`, `ContentTopic` → `content topic`), exact match, configurable alias dictionary, then RapidFuzz `token_sort_ratio`. A fuzzy match ≥ 86 is only *Suggested* and blocks validation until confirmed; 65–85 is a hint. Legacy execution columns (*Remarks…*, *Verified by CL/HoI/CH*, *Notes link*) are auto-ignored with an explanation. Value profiling (e.g. a column of K1/K2/K3) only produces hints.

**Commit is one transaction.** The plan row is locked (`SELECT … FOR UPDATE OF teaching_plans`), validation is re-run server-side, lectures/subtopics/schedules/faculty mapping/status/audit/notifications are written, then committed. Any failure rolls back and marks the session `FAILED` with the draft intact (`test_commit_failure_rolls_back_everything` injects a failure after lectures are flushed).

**Duplicate protection twice.** The service refuses a second live plan for the same subject/section/semester (409 `DUPLICATE_PLAN`, also checked live in the create form), and a partial unique index on the working copy (`WHERE status <> 'ARCHIVED'`) enforces it in PostgreSQL.

**Verification is a table, not a flag.** Each submission round creates a `CL_CH PENDING` row; CL/CH verifying opens an `OM PENDING` row; OM verifying sets `FINAL_VERIFIED`. Every row stores who decided (`verifier_id`), when, and their remarks. A correction closes the round with mandatory remarks (CHECK constraint) and reopens the record for editing; resubmission starts round 2 at CL/CH. A partial unique index allows at most one pending step per record. No level can act on another level's step (`WRONG_VERIFICATION_LEVEL`). The chain is one tuple, `VERIFICATION_CHAIN = (CL_CH, OM)`; adding a level = one more entry there + `LEVEL_ROLE`.

**Class timing is its own record.** `class_sessions` (one row per lecture, OM-owned) stores the actual entry and exit beside a copy of the scheduled slot. The *backend* decides what is late: entry more than `ENTRY_DELAY_TOLERANCE_MINUTES` (default 5) after the scheduled start returns `422 DELAY_REASON_REQUIRED` with the delay in minutes, and the UI then asks for the reason ("Other" needs remarks; both are also CHECK constraints). Class state (yet to start, entry due, in class, completed, not recorded) is derived from schedule + clock + record, never stored. The timing record locks when the lecture is final verified. Professors and CL/CH see it read-only next to the lecture update.

**One theme, one file.** Black surfaces, grey type and a single emerald accent are defined as tokens in `src/app/globals.css`; Tailwind's default palette is switched off there, so components can only use token classes (`bg-surface`, `text-fg-secondary`, `border-line`, `text-primary`, `text-warning`, `text-danger`). Green is reserved for primary actions, active/selected state, progress and success; amber for attention, red for errors and destructive actions. The atmospheric grid/glow exists on the sign-in screen only.

**Tasks are derived, not stored.** Today / upcoming / overdue / completed / corrections are queries over published schedule + progress (indexed on `lecture_schedules.planned_date`, `teaching_plans(professor_id, status)`). `planned_date` is never overwritten; rescheduling stores `rescheduled_to`.

**Explicit metrics.** Completed, Partial, Delayed (original planned date passed, not done) and Pending always sum to Total. Execution %, Verified % and On-time % definitions are returned by the API and shown in the UI.

**Why Next.js + FastAPI.** Next.js owns routing, layouts and the browser bundle; FastAPI owns every rule and all data. The App Router pages are thin client components that render feature modules, and `next.config.ts` proxies `/api` so both run as one site. Google sign-in later is a backend endpoint plus a button; it needs no change to this split.

**Accounts are real and admin-controlled.** `POST /api/auth/login` checks an email / username / employee ID and password against `users.password_hash` (scrypt, per-password salt; the password itself is never stored or logged) and issues an HMAC-signed token carrying only the user id. Every request re-reads the account, its role and its active flag from the database through `get_current_user`, so a deactivated account stops working on its next request and nothing in browser storage can grant a role. A new account gets a temporary password and must replace it at first sign-in - until then the API answers `403 PASSWORD_CHANGE_REQUIRED` to everything except reading the session and changing the password. Changing or resetting a password ends every session issued before it (the token carries a fingerprint of the hash). A placeholder `SECRET_KEY` is never used to sign: production refuses to start without a real one, and elsewhere a random key is generated once into `backend/.secret_key`. Failed sign-ins are throttled per account. Accounts are deactivated, never deleted, and a role cannot be changed once the account has lectures, verifications or class timings. Permissions live in one matrix (`core/permissions.py`) that `/api/me` also sends to the UI.

**Scope is one rule.** `user_scopes` holds, per CL/CH or OM account, a mode (ALL / SELECTED) and optional department, semesters, sections and subjects. `scope_service.plan_filter(user)` turns it into SQL conditions for every list (queues, metrics, the sprint sheet, OM classes, alerts) and `scope_service.require(user, plan)` guards every single-record read and action - a record outside the scope answers 404. Notifications go only to the accounts whose scope covers the lecture. For a professor the same row lists the subjects they may be allocated.

**A lecture belongs to an account, not a name.** `teaching_plans.professor_id` and the per-lecture override `lectures.professor_id` are foreign keys to `users`. Professor queries always filter on the signed-in user (`coalesce(lecture.professor_id, plan.professor_id) = me`); there is no `professor_id` parameter to tamper with. The admin allocates per lecture in the Semester Master Plan, in the bulk import (a *Professor Employee ID* column is matched to accounts; an unknown ID is an error the admin maps to a real professor - accounts are never created from spreadsheet text) and in the weekly sprint revision. A professor in two overlapping published classes is refused (`SCHEDULE_CONFLICT`) at each of those points; a shared room is reported as a warning.

**Audit trail.** `audit_logs` is append-only (no update/delete endpoints) with actor, role, action, entity, before/after values and a plan scope, which powers each plan's Activity timeline.

---

## API overview

| Area | Endpoints |
|---|---|
| Session | `POST /api/auth/login`, `POST /api/auth/change-password`, `GET /api/auth/config`, `GET /api/me` |
| Users (admin) | `GET/POST /api/admin/users` (`?role=PROFESSOR&status=ACTIVE&subject_id=` feeds every professor dropdown), `GET/PATCH /api/admin/users/{id}`, `POST /api/admin/users/{id}/password` |
| Sprint sheet | `GET /api/sprint-plan/sheet` - one week of the published plan for CL/CH, OM (inside their scope) and Admin |
| Academic | `GET/POST/PUT /api/academic-years · semesters · departments · branches · sections · subjects`, `GET /api/users`, `GET/POST /api/faculty-assignments` |
| Plans | `GET/POST /api/teaching-plans`, `GET /api/teaching-plans/{id}` (+ `/lectures`, `/activity`), `POST /api/teaching-plans/{id}/status`, `GET /api/teaching-plans/check-duplicate`, `PATCH /api/lectures/{id}` (audited correction) |
| Import | `POST /api/imports/session`, `PUT /{id}/mode`, `POST /{id}/full-table`, `POST /{id}/column`, `POST /{id}/file`, `PUT /{id}/header`, `PUT /{id}/mapping`, `POST /{id}/mapping/confirm-suggestions`, `DELETE /{id}/columns/{key}`, `POST /{id}/undo`, `POST /{id}/validate`, `GET /{id}/preview`, `PUT /{id}/rows/{i}`, `PUT /{id}/rows/{i}/removed`, `POST /{id}/commit` |
| Professor | `GET /api/professor/dashboard`, `GET /api/professor/tasks/{today\|upcoming\|overdue\|completed\|corrections}`, `GET /api/professor/courses[/{id}]`, `GET /api/professor/schedule`, `GET /api/lectures/{id}`, `PUT /api/lectures/{id}/progress`, `POST /api/lecture-progress/{id}/submit` |
| Operations (OM) | `GET /api/om/dashboard?on=`, `GET /api/om/classes`, `GET /api/om/classes/{lecture_id}`, `POST /api/om/classes/{lecture_id}/entry`, `POST …/exit`, `GET /api/om/delay-reasons`, `GET /api/om/records`, `GET /api/om/faculty`, `GET /api/om/reports/summary` |
| Verification | `GET /api/verifications/metrics`, `GET /api/verifications/queue/{pending\|verified\|corrections\|all}`, `GET /api/verifications/pending`, `GET /api/verifications/{id}`, `POST /{id}/verify`, `POST /{id}/request-correction` |
| Reports | `GET /api/admin/dashboard`, `GET /api/reports/progress`, `GET /api/reports/lectures/{delayed\|pending\|planned_vs_actual\|completion\|upcoming}`, `GET /api/reports/verification/{pending\|corrections}`, `GET /api/audit`, notifications |

Every error has the shape `{"error": {"code", "message", "details"}}`; stack traces never reach the client.

---

## How MongoDB is used

MongoDB Atlas is the only database. Each entity has its own collection (`users`, `teaching_plans`, `lectures`, `lecture_schedules`, `lecture_progress`, `verifications`, `class_sessions`, `semester_sprint_plans`, `sprint_revisions`, `timing_templates`, …). `_id` is the record's UUID as a string, references are UUID strings, moments are BSON dates in UTC, calendar dates are `"YYYY-MM-DD"`, times `"HH:MM:SS"`.

The portal's rules are relational (joins across plan → lecture → progress → verification, uniqueness, clash checks), so the backend works on a private working copy:

1. **On start** the whole database is read from Atlas into a temporary SQLite file (a few seconds).
2. **Reads** run on that copy, so pages stay fast although the database is in the cloud.
3. **Every write** is sent to Atlas *before* it is committed locally. If Atlas cannot be reached the request fails with `503 DATABASE_UNAVAILABLE` and nothing is kept.
4. The working copy is deleted when the process stops. Nothing is stored only on the server.

What follows from that:

- Run **one** backend process (`--workers 1`). Two processes would each hold their own copy.
- **Restart the backend** after running the seed script or after editing documents directly in Atlas.
- There are no migrations. A new field simply appears in documents written from then on; older documents load with the field's default.
- Atlas → Network Access must allow the IP address the backend runs from.

## Deployment

- **Database:** MongoDB Atlas. Set `MONGODB_URI=mongodb+srv://…` and optionally `MONGODB_DB`. Run a single backend instance.
- **API:** `render.yaml` (Render) or `backend/Dockerfile` (Railway/anything). Migrations run before start.
- **Frontend:** Vercel (native Next.js), root directory `frontend/`. Set `API_PROXY_TARGET=https://<api-host>` and the Next.js server proxies `/api/*` to FastAPI, so no CORS setup is needed. (Alternative: set `NEXT_PUBLIC_API_BASE_URL=https://<api-host>` to call the API directly and add the site origin to the API's `CORS_ORIGINS`.)
- Set a long random `SECRET_KEY` on the API. Set `DEMO_AUTH_ENABLED=false` once real authentication exists.

---

## Clearly marked as future work

These are labelled as *planned* in the UI rather than shown as working controls:

- Class photos stored locally are served from `/api/uploads` by unguessable file name without a sign-in check; use the S3 option with private URLs if that is not acceptable.
- SSO, self-service password reset by email, and account lockout shared across server instances (sign-in throttling is per process today).
- In-app notifications for "entry pending" / "exit pending" (the OM dashboard shows these states live; no notification is stored).
- Uploading PDFs for notes/assignments: `services/storage.py` has the S3-compatible presigned-upload backend; the UI stores links today.
- User invitations and role editing (Users page is read-only).
- Email / push / WhatsApp notification delivery (in-app notifications work; dispatchers plug into `notification_service.DISPATCHERS`).
- Plan lifecycle labels ACTIVE / COMPLETED (plans are DRAFT → PUBLISHED → ARCHIVED today).
- Changing a lecture's section or sequence number in a sprint revision (date, time, room, professor, topic, subtopics, type, cancel and add are supported).
- Pages are client components (the session lives in the browser); server components are not used for data yet.
- HoI as a fourth verification level (chain is configurable; not enabled).
- Room as an import column and room-clash checks (a plan has one default classroom today).
- OM final verification is not blocked when a timing record is missing; the review screen warns and lists it under Review Required.
- Rate limiting (add at the reverse proxy or with middleware when public).
