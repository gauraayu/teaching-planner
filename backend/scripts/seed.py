"""Development seed data.

    python -m scripts.seed                 # demo institute: 9 accounts, 5 sprint plans (one per class), 10 subjects
    python -m scripts.seed --empty         # only the 6 demo accounts - add all academic data yourself
    python -m scripts.seed --full          # the large demonstration dataset the test-suite runs on
    python -m scripts.seed --reset [...]   # wipe every table first, then seed as above

Demo sign-ins (development only; passwords are hashed like every other account):
    admin / Admin@123 · professor1 ... professor6 / Professor@123 · clch1 / CLCH@123 · om1 / OM@123
Real accounts are created by the admin in User Management. On a database that already has data the script only
makes sure every existing account can sign in (accounts without a password get Demo@1234 and must change it).
"""
from __future__ import annotations

import argparse
import random
import sys
import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select

from app.core import clock
from app.core.enums import (
    ClassType, DelayReason, ExecutionStatus, MaterialType, PlanStatus, Role, RoomType, ScopeMode, SubmissionStatus, TimetableStatus,
    TimingStatus, VerificationLevel, VerificationStatus,
)
from app.core.security import hash_password
from app.db.base import Base
from app.db.mongo_store import store
from app.db.session import SessionLocal, engine
from app.models import (
    AcademicYear, Assignment, AuditLog, Branch, ClassSession, Department, FacultySubjectAssignment, Lecture, LectureMaterial,
    LectureProgress, LectureSubtopicProgress, Notification, RoleModel, Section, Semester, Subject, TeachingPlan, User,
    Verification,
)
from app.models import Holiday, LectureSchedule, LectureSubtopic, Room, UserScope
from app.schemas.requests import SprintGenerate, SprintPlanIn, TeachingPlanCreate
from app.services import import_service, sprint_plan_service, sprint_service, teaching_plan_service, timetable_service

TODAY = clock.today()
IST = timezone(timedelta(hours=5, minutes=30))
rng = random.Random(2026)

DSA_PLAN = [
    # unit, type, topic, bloom, subtopics
    (1, "Theory", "Introduction to Recursion", "K1", ["Definition of recursion", "Base case and recursive case", "Call stack mechanism"]),
    (1, "Theory", "Journey from Iteration to Recursion", "K2", ["Loops as recursion", "Converting a loop into a recursive function"]),
    (1, "Theory", "Recursive Function Design", "K3", ["Choosing the sub-problem", "Writing the recurrence", "Tracing small inputs"]),
    (1, "Theory", "Time Complexity of Recursive Functions", "K3", ["Recurrence relations", "Recursion-tree method", "Substitution method"]),
    (1, "Theory", "Space Complexity of Recursive Functions", "K2", ["Stack frames", "Tail recursion", "Auxiliary space"]),
    (1, "Theory", "Master Theorem", "K3", ["The three cases", "Worked examples", "When the theorem does not apply"]),
    (1, "Tutorial", "When and Why to Use Recursion", "K4", ["Recursion vs iteration trade-offs", "Problem discussion"]),
    (1, "Theory", "Fibonacci and Exponential Recursion", "K3", ["Naive Fibonacci", "Overlapping sub-problems", "Exponential growth"]),
    (1, "Practical", "Recursion on Arrays and Strings", "K3", ["Array sum and search", "Palindrome check", "String reversal"]),
    (2, "Theory", "Introduction to Sorting and Divide & Conquer", "K2", ["Stability and in-place sorting", "Divide, conquer, combine"]),
    (2, "Theory", "Merge Sort", "K3", ["Merge process", "Recursive splitting", "Dry run on an example"]),
    (2, "Theory", "Merge Sort – Analysis and Variants", "K4", ["O(n log n) derivation", "Bottom-up merge sort", "Counting inversions"]),
    (2, "Theory", "Quick Sort", "K3", ["Quicksort overview", "Lomuto partition", "Hoare partition"]),
    (2, "Theory", "Quick Sort – Randomisation and Analysis", "K4", ["Worst case", "Randomised pivot", "Expected running time"]),
    (2, "Theory", "Counting Sort and Radix Sort", "K3", ["Counting sort", "Radix sort with stable passes"]),
    (2, "Theory", "Lower Bound for Comparison Sorting", "K4", ["Decision trees", "Ω(n log n) bound"]),
    (2, "Tutorial", "Tutorial: Sorting Problems", "K3", ["Kth smallest element", "Dutch national flag"]),
    (3, "Theory", "Backtracking", "K3", ["State-space tree", "Pruning", "Template for backtracking"]),
    (3, "Theory", "N-Queens Problem", "K3", ["Constraint checks", "Counting all solutions"]),
    (3, "Practical", "Subset Sum and Permutations", "K3", ["Generating subsets", "Generating permutations"]),
    (3, "Theory", "Introduction to Dynamic Programming", "K2", ["Optimal substructure", "Overlapping sub-problems"]),
    (3, "Theory", "Memoization vs Tabulation", "K3", ["Top-down memoization", "Bottom-up tabulation", "Space optimisation"]),
    (3, "Theory", "0/1 Knapsack", "K3", ["Recurrence", "Table construction", "Reconstructing the answer"]),
    (3, "Theory", "Longest Common Subsequence", "K3", ["LCS recurrence", "Printing the subsequence"]),
    (3, "Theory", "Matrix Chain Multiplication", "K4", ["Parenthesisation", "Interval DP"]),
    (4, "Theory", "Binary Trees and Traversals", "K2", ["Inorder, preorder, postorder", "Level-order traversal"]),
    (4, "Theory", "Binary Search Trees", "K3", ["Search and insert", "Deletion cases"]),
    (4, "Theory", "AVL Trees", "K3", ["Balance factor", "Rotations"]),
    (4, "Theory", "Heaps and Priority Queues", "K3", ["Heap property", "Heapify", "Priority-queue operations"]),
    (4, "Practical", "Heap Sort", "K3", ["Build-heap in O(n)", "In-place heap sort"]),
    (4, "Theory", "Tries", "K2", ["Insertion and search", "Prefix queries"]),
    (5, "Theory", "Graph Representations", "K1", ["Adjacency matrix", "Adjacency list", "Edge list"]),
    (5, "Theory", "BFS and DFS", "K3", ["Breadth-first search", "Depth-first search", "Connected components"]),
    (5, "Theory", "Topological Sort", "K3", ["Kahn's algorithm", "DFS-based ordering"]),
    (5, "Theory", "Shortest Paths – Dijkstra", "K3", ["Relaxation", "Priority-queue implementation"]),
    (5, "Theory", "Bellman-Ford Algorithm", "K4", ["Negative edges", "Negative-cycle detection"]),
    (5, "Theory", "Minimum Spanning Trees – Prim and Kruskal", "K3", ["Cut property", "Prim's algorithm", "Kruskal's algorithm"]),
    (5, "Theory", "Disjoint Set Union", "K3", ["Union by rank", "Path compression"]),
    (5, "Revision", "Revision: Graph Algorithms", "K4", ["Problem solving session"]),
    (5, "Assessment", "Class Test – Units 4 and 5", "K4", []),
]

DBMS_PLAN = [
    (1, "Introduction to Database Systems", "K1", ["File systems vs DBMS", "Three-schema architecture"]),
    (1, "Entity-Relationship Model", "K2", ["Entities and attributes", "Relationships and cardinality"]),
    (1, "Extended ER Features", "K3", ["Generalisation", "Aggregation"]),
    (1, "Relational Model", "K2", ["Relations and keys", "Integrity constraints"]),
    (2, "Relational Algebra", "K3", ["Selection and projection", "Joins", "Division"]),
    (2, "SQL – Data Definition", "K3", ["CREATE and ALTER", "Constraints"]),
    (2, "SQL – Queries and Joins", "K3", ["Inner and outer joins", "Aggregates and GROUP BY"]),
    (2, "SQL – Subqueries and Views", "K3", ["Correlated subqueries", "Views"]),
    (3, "Functional Dependencies", "K2", ["Armstrong's axioms", "Closure of attributes"]),
    (3, "Normalisation – 1NF to 3NF", "K3", ["Anomalies", "Decomposition"]),
    (3, "BCNF and Lossless Decomposition", "K4", ["BCNF", "Dependency preservation"]),
    (4, "Transactions and ACID", "K2", ["Transaction states", "ACID properties"]),
    (4, "Concurrency Control", "K3", ["Two-phase locking", "Deadlocks"]),
    (4, "Recovery Techniques", "K2", ["Log-based recovery", "Checkpoints"]),
    (5, "Indexing and B+ Trees", "K3", ["Primary and secondary indexes", "B+ tree insertion"]),
    (5, "Hashing", "K2", ["Static hashing", "Extendible hashing"]),
    (5, "Query Processing", "K3", ["Cost estimation", "Join algorithms"]),
    (5, "Revision and Problem Solving", "K4", []),
]

OS_PLAN = [
    (1, "Operating System Structures", "K1", ["Kernel modes", "System calls"]),
    (1, "Processes", "K2", ["Process states", "PCB", "Context switch"]),
    (1, "Threads", "K2", ["User and kernel threads", "Multithreading models"]),
    (2, "CPU Scheduling – FCFS and SJF", "K3", ["Scheduling criteria", "FCFS", "SJF"]),
    (2, "CPU Scheduling – Priority and Round Robin", "K3", ["Priority scheduling", "Round robin"]),
    (2, "Process Synchronisation", "K3", ["Critical-section problem", "Peterson's solution"]),
    (2, "Semaphores and Monitors", "K3", ["Semaphores", "Classic problems"]),
    (3, "Deadlocks", "K3", ["Necessary conditions", "Resource-allocation graph"]),
    (3, "Deadlock Avoidance – Banker's Algorithm", "K4", ["Safe state", "Banker's algorithm"]),
    (4, "Memory Management", "K2", ["Contiguous allocation", "Fragmentation"]),
    (4, "Paging and Segmentation", "K3", ["Page tables", "TLB"]),
    (4, "Virtual Memory", "K3", ["Demand paging", "Page replacement"]),
    (5, "File Systems", "K2", ["File allocation methods", "Directory structures"]),
    (5, "Disk Scheduling", "K3", ["FCFS, SSTF, SCAN"]),
]

ML_PLAN = [
    (1, "Introduction to Machine Learning", "K1", ["Types of learning", "ML workflow"]),
    (1, "Linear Regression", "K3", ["Least squares", "Gradient descent"]),
    (1, "Logistic Regression", "K3", ["Sigmoid", "Cross-entropy loss"]),
    (2, "Bias-Variance Trade-off", "K2", ["Underfitting and overfitting", "Regularisation"]),
    (2, "Decision Trees", "K3", ["Entropy and Gini", "Pruning"]),
    (2, "Ensemble Methods", "K3", ["Bagging", "Random forests", "Boosting"]),
    (3, "Support Vector Machines", "K3", ["Margins", "Kernels"]),
    (3, "k-Nearest Neighbours", "K2", ["Distance metrics", "Choosing k"]),
    (4, "Clustering – k-Means", "K3", ["Lloyd's algorithm", "Elbow method"]),
    (4, "Principal Component Analysis", "K4", ["Covariance", "Eigen-decomposition"]),
    (5, "Model Evaluation", "K4", ["Cross-validation", "Precision and recall", "ROC curves"]),
    (5, "Mini-project Review", "K5", []),
]

CN_PLAN = [
    (1, "Network Models – OSI and TCP/IP", "K1", ["Layering", "Encapsulation"]),
    (1, "Physical Layer Basics", "K2", ["Transmission media", "Signals"]),
    (2, "Data Link Layer – Framing and Error Detection", "K3", ["Framing", "CRC"]),
    (2, "Flow Control – Stop-and-Wait and Sliding Window", "K3", ["Stop-and-wait", "Go-Back-N", "Selective repeat"]),
    (2, "Medium Access Control", "K2", ["ALOHA", "CSMA/CD"]),
    (3, "IP Addressing and Subnetting", "K3", ["Classful addressing", "CIDR", "Subnet masks"]),
    (3, "Routing Algorithms", "K3", ["Distance vector", "Link state"]),
    (4, "Transport Layer – UDP and TCP", "K2", ["Ports", "TCP handshake"]),
    (4, "TCP Congestion Control", "K4", ["Slow start", "AIMD"]),
    (5, "Application Layer – DNS and HTTP", "K2", ["DNS resolution", "HTTP methods"]),
]


def teaching_days(start: date, weekdays: tuple[int, ...], count: int, holidays: set[date]) -> list[date]:
    out, d = [], start
    while len(out) < count:
        if d.weekday() in weekdays and d not in holidays:
            out.append(d)
        d += timedelta(days=1)
    return out


# Today is never treated as a holiday, so the Operations Manager's "today" view has classes on any weekday.
HOLIDAYS = {date(2026, 8, 15), date(2026, 8, 26), date(2026, 9, 14), date(2026, 10, 2), date(2026, 10, 20), date(2026, 11, 8)} - {TODAY}

DEMO_PASSWORD = "Demo@1234"  # the same value the sign-in page shows while DEMO_AUTH_ENABLED=true
_DEMO_HASH: str | None = None


def demo_hash() -> str:
    """One scrypt hash reused for every demo account (hashing is deliberately slow)."""
    global _DEMO_HASH
    if _DEMO_HASH is None:
        _DEMO_HASH = hash_password(DEMO_PASSWORD)
    return _DEMO_HASH


ROLE_ROWS = ((Role.ADMIN, "Administrator", "Academic office administrator"),
             (Role.PROFESSOR, "Professor", "Faculty member who executes teaching plans"),
             (Role.CL_CH, "CL/CH", "Academic verifier: reviews professor submissions within the assigned scope"),
             (Role.OM, "Operations Manager", "Records class entry/exit timings and gives final verification"))


def ensure_roles(db) -> dict:
    """Get-or-create, because migration 0002 already inserts the OM role row."""
    roles = {r.code: r for r in db.scalars(select(RoleModel))}
    for code, name, desc in ROLE_ROWS:
        if code.value not in roles:
            roles[code.value] = RoleModel(code=code.value, name=name, description=desc)
            db.add(roles[code.value])
    db.flush()
    return {Role(code): row for code, row in roles.items()}


def ensure_sign_in(db) -> int:
    """For a database created before real sign-in existed: give every account without a password a way in.

    Seeded demo accounts get their demo username; everyone else keeps their email / employee ID as the
    identifier. All of them receive the demo password and are asked to change it at first sign-in.
    """
    ensure_roles(db)
    demo_names = {Role.ADMIN: "admin.demo", Role.PROFESSOR: "professor.demo", Role.CL_CH: "clch.demo", Role.OM: "om.demo"}
    taken = set(db.scalars(select(User.username).where(User.username.is_not(None))))
    changed = 0
    for u in db.scalars(select(User).order_by(User.created_at)).unique():
        if u.is_demo and not u.username and demo_names.get(u.role_code) not in taken | {None}:
            u.username = demo_names[u.role_code]
            taken.add(u.username)
        if not u.password_hash:
            u.password_hash, u.must_change_password = demo_hash(), not u.is_demo
            changed += 1
    db.commit()
    return changed


def build_tsv(rows: list[tuple], dates: list[date], start: time, end: time, *, with_type=True, with_exec_columns=True) -> str:
    """Produce exactly what a Google Sheets copy of a legacy teaching plan looks like."""
    max_subs = 3
    header = ["SrNo", "Lecture_No"] + (["Lecture_Type"] if with_type else []) + ["Unit_No", "Content_Topic", "Blooms_Taxonomy"] \
        + [f"Sub_Topic{i}" for i in range(1, max_subs + 1)] + ["Scheduled_Date", "Start Time", "End Time"]
    if with_exec_columns:
        header += ["Remarks about Task Completion", "Daily Lecture Notes Link", "Verified by CL/HoI/CH"]
    lines = ["\t".join(header)]
    for i, row in enumerate(rows):
        if with_type:
            unit, ltype, topic, bloom, subs = row
        else:
            unit, topic, bloom, subs = row
            ltype = None
        subs = (subs + ["", "", ""])[:max_subs] if len(subs) <= max_subs else subs[:2] + ["\n".join(subs[2:])]
        cells = [str(i + 1), str(i + 1)] + ([ltype] if with_type else []) + [str(unit), topic, bloom] + subs + [
            dates[i].strftime("%d/%m/%Y"), start.strftime("%I:%M %p"), end.strftime("%I:%M %p")]
        if with_exec_columns:
            cells += ["", "", ""]
        lines.append("\t".join(f'"{c}"' if "\n" in c else c for c in cells))
    return "\n".join(lines) + "\n"


def at(d: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(d, time(hour, minute), tzinfo=IST)


def reset(db) -> None:
    for t in reversed(Base.metadata.sorted_tables):
        db.execute(t.delete())
    db.commit()


def seed(db) -> None:
    """The large demonstration dataset (`--full`). The test-suite runs against this."""
    # ------------------------------------------------------------ roles & users
    roles = ensure_roles(db)
    timetable_service.ensure_templates(db)

    cse = Department(code="CSE", name="Computer Science & Engineering")
    db.add(cse)
    db.flush()

    def user(email, name, role, designation, demo=False, code=None, username=None):
        u = User(email=email, full_name=name, role_id=roles[role].id, designation=designation, is_demo=demo,
                 department_id=cse.id, employee_code=code, username=username or email.split("@")[0], password_hash=demo_hash())
        db.add(u)
        return u

    admin = user("admin@demo.institute.edu", "Rajesh Verma", Role.ADMIN, "Academic Administrator", True, "ADM-001", "admin.demo")
    prof = user("ananya.sharma@demo.institute.edu", "Dr. Ananya Sharma", Role.PROFESSOR, "Associate Professor", True, "FAC-1042", "professor.demo")
    cl = user("clch@demo.institute.edu", "Prof. Vikram Joshi", Role.CL_CH, "CL/CH – Computer Science", True, "FAC-0871", "clch.demo")
    om = user("om@demo.institute.edu", "Sanjay Kulkarni", Role.OM, "Operations Manager", True, "OPS-0031", "om.demo")
    meera = user("meera.iyer@demo.institute.edu", "Dr. Meera Iyer", Role.PROFESSOR, "Professor", code="FAC-0933", username="professor2.demo")
    arjun = user("arjun.nair@demo.institute.edu", "Prof. Arjun Nair", Role.PROFESSOR, "Assistant Professor", code="FAC-1188")
    kavita = user("kavita.rao@demo.institute.edu", "Dr. Kavita Rao", Role.PROFESSOR, "Associate Professor", code="FAC-1007")
    farhan = user("farhan.qureshi@demo.institute.edu", "Dr. Farhan Qureshi", Role.PROFESSOR, "Assistant Professor", code="FAC-1253")
    db.flush()

    # ------------------------------------------------------------ academic structure
    ay = AcademicYear(name="2026–27", start_date=date(2026, 7, 1), end_date=date(2027, 6, 30), is_current=True)
    db.add(ay)
    db.flush()
    sems = {}
    for n, name in ((3, "Semester III"), (5, "Semester V"), (7, "Semester VII")):
        sems[n] = Semester(academic_year_id=ay.id, number=n, name=name, start_date=date(2026, 7, 15),
                           end_date=date(2026, 12, 12), is_current=n == 5)
        db.add(sems[n])
    db.flush()
    br_cse = Branch(department_id=cse.id, code="CSE", name="Computer Science & Engineering")
    br_aiml = Branch(department_id=cse.id, code="AIML", name="CSE (Artificial Intelligence & Machine Learning)")
    db.add_all([br_cse, br_aiml])
    db.flush()
    sec = {}
    for key, branch, sem, name, n in (("cse5a", br_cse, 5, "A", 64), ("cse5b", br_cse, 5, "B", 61), ("aiml5a", br_aiml, 5, "A", 58),
                                      ("cse3a", br_cse, 3, "A", 66), ("cse7a", br_cse, 7, "A", 59)):
        sec[key] = Section(branch_id=branch.id, semester_id=sems[sem].id, name=name, student_count=n)
        db.add(sec[key])
    subjects = {}
    for code, name, short, branch, semn, credits in (
        ("CS501", "Data Structures & Algorithms", "DSA", br_cse, 5, 4),
        ("CS502", "Database Management Systems", "DBMS", br_cse, 5, 4),
        ("CS503", "Operating Systems", "OS", br_cse, 5, 4),
        ("CS504", "Computer Networks", "CN", br_cse, 5, 3),
        ("CS505", "Theory of Computation", "TOC", br_cse, 5, 3),
        ("AL501", "Machine Learning", "ML", br_aiml, 5, 4),
        ("AL502", "Database Management Systems", "DBMS", br_aiml, 5, 4),
        ("CS301", "Discrete Mathematics", "DM", br_cse, 3, 4),
        ("CS701", "Compiler Design", "CD", br_cse, 7, 3),
    ):
        subjects[code] = Subject(code=code, name=name, short_name=short, branch_id=branch.id, semester_number=semn, credits=credits)
        db.add(subjects[code])
    db.commit()

    # ------------------------------------------------------------ plans via the real import pipeline
    def import_plan(subject, section, professor, rows, weekdays, start_t, end_t, *, with_type, room):
        plan = teaching_plan_service.create_plan(db, admin, TeachingPlanCreate(
            academic_year_id=ay.id, semester_id=section.semester_id, department_id=cse.id,
            branch_id=section.branch_id, section_id=section.id, subject_id=subject.id, professor_id=professor.id, room=room))
        dates = teaching_days(date(2026, 7, 20), weekdays, len(rows), HOLIDAYS)
        session = import_service.create_session(db, admin, plan.id)
        import_service.load_full_table(db, session, build_tsv(rows, dates, start_t, end_t, with_type=with_type))
        result = import_service.validate(db, session)
        if not result["can_commit"]:
            errs = [i for r in result["rows"] for i in r["issues"] if i["level"] == "ERROR"] + result["session_issues"]
            raise SystemExit(f"Seed import failed for {plan.name}: {errs[:5]}")
        import_service.commit(db, session, admin, publish=True)
        db.refresh(plan)
        plan.published_at = at(date(2026, 7, 16), 10, 30)
        session.committed_at = plan.published_at
        db.commit()
        return plan

    plans = [
        (import_plan(subjects["CS501"], sec["cse5a"], prof, DSA_PLAN, (0, 2, 3), time(10), time(11), with_type=True, room="C-204"), "steady"),
        (import_plan(subjects["CS501"], sec["cse5b"], prof, DSA_PLAN[:34], (0, 1, 4), time(11, 15), time(12, 15), with_type=True, room="C-206"), "behind"),
        (import_plan(subjects["CS502"], sec["cse5a"], meera, DBMS_PLAN, (1,), time(9), time(10), with_type=False, room="C-204"), "steady"),
        (import_plan(subjects["CS503"], sec["cse5a"], arjun, OS_PLAN, (4,), time(14), time(15), with_type=False, room="C-204"), "behind"),
        (import_plan(subjects["AL501"], sec["aiml5a"], farhan, ML_PLAN, (0,), time(12), time(13), with_type=False, room="A-112"), "steady"),
        (import_plan(subjects["CS504"], sec["cse5b"], kavita, CN_PLAN, (2,), time(15), time(16), with_type=False, room="C-206"), "steady"),
        (import_plan(subjects["AL502"], sec["aiml5a"], meera, DBMS_PLAN, (4,), time(9), time(10), with_type=False, room="A-112"), "steady"),
    ]
    db.query(AuditLog).delete()  # replace import-time audit noise with a realistic dated timeline below
    db.query(Notification).delete()
    db.commit()

    # A draft plan with an unfinished import, so the "resume import" flow has something to show.
    toc = teaching_plan_service.create_plan(db, admin, TeachingPlanCreate(
        academic_year_id=ay.id, semester_id=sems[5].id, department_id=cse.id, branch_id=br_cse.id,
        section_id=sec["cse5a"].id, subject_id=subjects["CS505"].id, professor_id=kavita.id))
    draft = import_service.create_session(db, admin, toc.id)
    import_service.set_mode(db, draft, import_service.ImportMode.COLUMN_WISE)
    import_service.add_column(db, draft, field="content_topic", raw_text="\n".join([
        "Introduction to Automata Theory", "Deterministic Finite Automata", "Non-deterministic Finite Automata",
        "NFA to DFA Conversion", "Regular Expressions", "Pumping Lemma for Regular Languages"]))
    import_service.add_column(db, draft, field="lecture_no", raw_text="1\n2\n3\n4\n5\n6")
    db.query(AuditLog).filter(AuditLog.scope_id == toc.id).delete()
    db.commit()

    # ------------------------------------------------------------ execution, verification & audit history
    for plan, pace in plans:
        simulate_execution(db, plan, pace, cl=cl, om=om, admin=admin)
    seed_todays_operations(db, [p for p, _ in plans], om)
    db.commit()

    for u, title, body, link, kind in (
        (prof, "Lecture requires correction", "CL/CH asked for the notes link on a DSA lecture.", "/professor/dashboard", "verification.correction"),
        (prof, "You have lectures scheduled today", "Check Today's Tasks for your schedule.", "/professor/dashboard", "tasks.today"),
        (cl, "Submissions are waiting for verification", "Open Pending Verification to review them.", "/verification/pending", "verification.pending"),
        (om, "Submissions are waiting for final verification", "Open Final Verification to review CL/CH verified classes.", "/om/final-verification", "verification.pending"),
        (admin, "Teaching Plan DSA Semester V imported successfully", "40 lectures published to Dr. Ananya Sharma.", f"/admin/plans/{plans[0][0].id}", "plan.imported"),
    ):
        db.add(Notification(user_id=u.id, kind=kind, title=title, body=body, link=link))
    db.commit()
    print(f"Seeded {len(plans)} published plans, 1 draft plan with a resumable import, 9 users.")


DELAY_REASONS = (
    (DelayReason.PREVIOUS_CLASS_OVERRUN, None), (DelayReason.PREVIOUS_CLASS_OVERRUN, None),
    (DelayReason.DEPARTMENTAL_MEETING, None), (DelayReason.ADMINISTRATIVE_WORK, None),
    (DelayReason.TECHNICAL_ISSUE, "Projector did not start; class began on the whiteboard."),
    (DelayReason.ROOM_ISSUE, "Room was occupied by an extended lab viva."),
    (DelayReason.OTHER, "Professor was called to the examination cell."),
)


def class_session(lec: Lecture, plan: TeachingPlan, on: date, om: User, *, delay: int, exit_offset: int | None = 0,
                  reason=None, remarks=None) -> ClassSession:
    """An OM timing record. `delay` = minutes after the scheduled start; `exit_offset` = minutes after the scheduled end."""
    sch = lec.schedule
    entry = datetime.combine(on, sch.planned_start_time, tzinfo=IST) + timedelta(minutes=delay)
    late = delay > 5
    return ClassSession(
        lecture_id=lec.id, professor_id=plan.professor_id, session_date=on, scheduled_start=sch.planned_start_time,
        scheduled_end=sch.planned_end_time, room=sch.room or plan.room, entry_at=entry,
        exit_at=None if exit_offset is None else datetime.combine(on, sch.planned_end_time, tzinfo=IST) + timedelta(minutes=exit_offset),
        entry_delay_minutes=delay, timing_status=TimingStatus.DELAYED if late else TimingStatus.ON_TIME,
        delay_reason=reason.value if late and reason else None, delay_remarks=remarks if late else None,
        entry_recorded_by_id=om.id, exit_recorded_by_id=None if exit_offset is None else om.id)


def random_session(lec: Lecture, plan: TeachingPlan, on: date, om: User) -> ClassSession:
    if rng.random() < 0.2:
        reason, remarks = rng.choice(DELAY_REASONS)
        return class_session(lec, plan, on, om, delay=rng.randint(6, 16), exit_offset=rng.randint(0, 6), reason=reason, remarks=remarks)
    return class_session(lec, plan, on, om, delay=rng.randint(0, 4), exit_offset=rng.randint(-3, 4))


def seed_todays_operations(db, plans: list[TeachingPlan], om: User) -> None:
    """Today's classes: finished ones have entry + exit, the one running right now is in class, later ones are untouched."""
    now = datetime.now(IST)
    todays = sorted((l for p in plans for l in p.lectures if l.schedule and l.schedule.planned_date == TODAY and not l.class_session),
                    key=lambda l: l.schedule.planned_start_time)
    for n, lec in enumerate(todays):
        plan, sch = lec.teaching_plan, lec.schedule
        start = datetime.combine(TODAY, sch.planned_start_time, tzinfo=IST)
        end = datetime.combine(TODAY, sch.planned_end_time, tzinfo=IST)
        if end + timedelta(minutes=5) < now:
            late = n % 2 == 1
            db.add(class_session(lec, plan, TODAY, om, delay=7 if late else 1, exit_offset=2,
                                 reason=DelayReason.PREVIOUS_CLASS_OVERRUN if late else None))
        elif start + timedelta(minutes=3) < now < end:
            db.add(class_session(lec, plan, TODAY, om, delay=2, exit_offset=None))


def simulate_execution(db, plan: TeachingPlan, pace: str, *, cl: User, om: User, admin: User) -> None:
    def log(actor, action, summary, when, entity_type="teaching_plan", entity_id=None):
        db.add(AuditLog(actor_id=actor.id, actor_role=actor.role.code, action=action, entity_type=entity_type,
                        entity_id=entity_id or plan.id, summary=summary, scope_type="teaching_plan", scope_id=plan.id, created_at=when))

    log(admin, "plan.created", f"Created teaching plan {plan.name} for {plan.professor.full_name}.", at(date(2026, 7, 16), 10, 5))
    log(admin, "plan.imported", f"Imported {len(plan.lectures)} lectures into {plan.name}.", at(date(2026, 7, 16), 10, 28))
    log(admin, "plan.published", f"Published teaching plan {plan.name}.", at(date(2026, 7, 16), 10, 30))

    professor = plan.professor
    past = [l for l in plan.lectures if l.schedule and l.schedule.planned_date and l.schedule.planned_date < TODAY]
    skipped = set()
    if pace == "behind":
        skipped = {l.id for l in past[-4:]}  # last four are delayed (no update yet)
    else:
        skipped = {past[-1].id} if past else set()  # one delayed lecture
    partial_ids = {l.id for l in past[::9]} - skipped
    for idx, lec in enumerate(past):
        if lec.id in skipped:
            continue
        planned = lec.schedule.planned_date
        late = rng.random() < 0.18
        actual = planned + timedelta(days=1 if late else 0)
        if actual >= TODAY:
            actual = planned
        is_partial = lec.id in partial_ids
        pr = LectureProgress(
            lecture_id=lec.id, professor_id=professor.id,
            execution_status=ExecutionStatus.PARTIALLY_COMPLETED if is_partial else ExecutionStatus.COMPLETED,
            actual_completion_date=actual, shared_with_students=True,
            shared_at=at(actual, 17, 30), submission_status=SubmissionStatus.DRAFT,
            remarks=("Covered the first part; remaining subtopic carried to the next lecture." if is_partial
                     else ("Lecture taken a day later due to a department seminar." if late else None)),
        )
        if rng.random() < 0.06 and not is_partial:
            pr.shared_with_students = False
            pr.shared_at = None
            pr.not_shared_reason = "Student WhatsApp group was being reorganised; notes shared in class instead."
        db.add(pr)
        db.flush()
        covered_count = len(lec.subtopics) if not is_partial else max(1, len(lec.subtopics) - 1)
        for i, sub in enumerate(lec.subtopics):
            pr.subtopic_progress.append(LectureSubtopicProgress(subtopic_id=sub.id, is_covered=i < covered_count))
        slug = lec.content_topic.lower().replace(" ", "-").replace("–", "").replace("&", "and")[:40]
        pr.materials.append(LectureMaterial(material_type=MaterialType.LECTURE_NOTES, title=f"Lecture {lec.lecture_no} notes",
                                            file_url=f"https://drive.google.com/file/d/demo-{plan.subject.code.lower()}-{lec.lecture_no:02d}/view",
                                            file_name=f"{slug}.pdf", uploaded_by_id=professor.id, uploaded_at=at(actual, 17, 10)))
        if lec.lecture_no % 3 == 0:
            pr.assignment = Assignment(title=f"Weekly Assignment {lec.lecture_no // 3}: {lec.content_topic}",
                                       description="Solve the problems in the attached sheet and submit on the LMS.",
                                       link_url=f"https://lms.demo.institute.edu/{plan.subject.code.lower()}/assignment-{lec.lecture_no // 3}",
                                       due_date=actual + timedelta(days=7), shared_with_students=True, shared_at=at(actual, 18),
                                       created_by_id=professor.id)
        log(professor, "progress.saved", f"Marked Lecture {lec.lecture_no} {'partially completed' if is_partial else 'completed'}.",
            at(actual, 11, 20), "lecture_progress", pr.id)

        rank = len(past) - 1 - idx  # 0 = most recent past lecture
        # The OM's timing record. One recent class per plan is left without one, so "Review Required" has a real case.
        if rank != 6:
            db.add(random_session(lec, plan, actual, om))
        # Older work is fully verified; the most recent lectures sit at different points in the chain.
        if rank == 1 and pace == "steady":
            continue  # saved as a draft, not yet submitted
        pr.submitted_at = at(actual, 18, 5)
        pr.submission_count = 1
        log(professor, "progress.submitted", f"Submitted Lecture {lec.lecture_no} for verification.", pr.submitted_at, "lecture_progress", pr.id)
        if rank <= 3:
            pr.submission_status = SubmissionStatus.SUBMITTED
            db.add(Verification(lecture_progress_id=pr.id, round=1, verification_level=VerificationLevel.CL_CH, status=VerificationStatus.PENDING,
                                created_at=pr.submitted_at))
            continue
        if rank == 5 and plan.professor.is_demo and pace == "steady":
            # One correction cycle currently open for the demo professor.
            pr.submission_status = SubmissionStatus.CORRECTION_REQUIRED
            db.add(Verification(lecture_progress_id=pr.id, round=1, verification_level=VerificationLevel.CL_CH,
                                status=VerificationStatus.CORRECTION_REQUIRED, verifier_id=cl.id, verifier_role=Role.CL_CH.value,
                                remarks="The notes link opens a different lecture's PDF. Please attach the correct notes.",
                                verified_at=at(actual + timedelta(days=1), 12, 30), created_at=pr.submitted_at))
            log(cl, "verification.correction_requested", f"CL/CH requested a correction on Lecture {lec.lecture_no}.",
                at(actual + timedelta(days=1), 12, 30), "lecture_progress", pr.id)
            continue
        ch_at = at(actual + timedelta(days=1), 12, 30)
        db.add(Verification(lecture_progress_id=pr.id, round=1, verification_level=VerificationLevel.CL_CH, status=VerificationStatus.VERIFIED,
                            verifier_id=cl.id, verifier_role=Role.CL_CH.value, verified_at=ch_at, created_at=pr.submitted_at))
        log(cl, "verification.verified", f"CL/CH verified Lecture {lec.lecture_no}.", ch_at, "lecture_progress", pr.id)
        om_at = at(actual + timedelta(days=3), 16, 20)
        if rank == 7 and pace == "behind":
            # One correction raised at the final (OM) step.
            pr.submission_status = SubmissionStatus.CORRECTION_REQUIRED
            db.add(Verification(lecture_progress_id=pr.id, round=1, verification_level=VerificationLevel.OM,
                                status=VerificationStatus.CORRECTION_REQUIRED, verifier_id=om.id, verifier_role=Role.OM.value,
                                remarks="Actual completion date does not match the day the class was held. Please correct the date.",
                                verified_at=om_at, created_at=ch_at))
            log(om, "verification.correction_requested", f"OM requested a correction on Lecture {lec.lecture_no}.", om_at, "lecture_progress", pr.id)
            continue
        if rank <= 7:
            pr.submission_status = SubmissionStatus.SUBMITTED
            db.add(Verification(lecture_progress_id=pr.id, round=1, verification_level=VerificationLevel.OM, status=VerificationStatus.PENDING,
                                created_at=ch_at))
            continue
        db.add(Verification(lecture_progress_id=pr.id, round=1, verification_level=VerificationLevel.OM, status=VerificationStatus.VERIFIED,
                            verifier_id=om.id, verifier_role=Role.OM.value, verified_at=om_at, created_at=ch_at))
        pr.submission_status = SubmissionStatus.FINAL_VERIFIED
        pr.final_verified_at = om_at
        log(om, "verification.final_verified", f"OM final verified Lecture {lec.lecture_no}.", om_at, "lecture_progress", pr.id)

    # One lecture rescheduled into the future, with the original planned date intact.
    future = [l for l in plan.lectures if l.schedule and l.schedule.planned_date and TODAY < l.schedule.planned_date <= TODAY + timedelta(days=10)]
    if pace == "behind" and future:
        lec = future[0]
        db.add(LectureProgress(lecture_id=lec.id, professor_id=professor.id, execution_status=ExecutionStatus.RESCHEDULED,
                               rescheduled_to=lec.schedule.planned_date + timedelta(days=2), submission_status=SubmissionStatus.DRAFT,
                               remarks="Swapped with a lab session at the HoD's request."))


DEMO_USERS = (
    # role, username, password, email, name, designation, employee ID  -  development / demo credentials only
    (Role.ADMIN, "admin", "Admin@123", "admin@demo.institute.edu", "Demo Admin", "Academic Administrator", "DEMO-ADM"),
    (Role.PROFESSOR, "professor1", "Professor@123", "professor1@demo.institute.edu", "Dr. Ankit Singh", "Associate Professor", "EMP001"),
    (Role.PROFESSOR, "professor2", "Professor@123", "professor2@demo.institute.edu", "Prof. Vikram Joshi", "Assistant Professor", "EMP002"),
    (Role.PROFESSOR, "professor3", "Professor@123", "professor3@demo.institute.edu", "Prof. Neha Sharma", "Assistant Professor", "EMP003"),
    (Role.PROFESSOR, "professor4", "Professor@123", "professor4@demo.institute.edu", "Prof. Sameer Mishra", "Assistant Professor", "EMP004"),
    (Role.PROFESSOR, "professor5", "Professor@123", "professor5@demo.institute.edu", "Dr. Kavita Rao", "Associate Professor", "EMP005"),
    (Role.PROFESSOR, "professor6", "Professor@123", "professor6@demo.institute.edu", "Prof. Arjun Nair", "Assistant Professor", "EMP006"),
    (Role.CL_CH, "clch1", "CLCH@123", "clch1@demo.institute.edu", "Demo CL/CH", "CL/CH", "CLCH001"),
    (Role.OM, "om1", "OM@123", "om1@demo.institute.edu", "Demo OM", "Operations Manager", "OM001"),
)
DEMO_LOGINS = "admin / Admin@123, professor1 ... professor6 / Professor@123, clch1 / CLCH@123, om1 / OM@123"


def _workday(d: date) -> date:
    return d + timedelta(days=1) if d.weekday() == 6 else d  # no classes on Sunday


def seed_users(db) -> dict:
    """The only accounts the seed creates. Every other account is created by the admin in User Management.
    Passwords are stored hashed like every other account; these are known development credentials."""
    roles = ensure_roles(db)
    timetable_service.ensure_templates(db)  # a --reset also empties the timing templates; put the two day structures back
    users = {}
    for role, username, password, email, name, designation, code in DEMO_USERS:
        users[username] = u = User(email=email, username=username, full_name=name, role_id=roles[role].id, designation=designation,
                                   employee_code=code, is_demo=True, password_hash=hash_password(password))
        db.add(u)
    db.commit()
    return users


# Master plan topics: (unit, type, topic, subtopics). No dates - the weekly sprint plan puts them on timetable slots.
def _units(units: list[tuple[str, list[str]]]) -> list[tuple]:
    """First-year curriculum written as units: every topic is one lecture with the same three teaching steps."""
    return [(n, "THEORY", topic, [f"{topic}: concept", f"{topic}: worked examples", f"{topic}: practice problems"])
            for n, (_, topics) in enumerate(units, start=1) for topic in topics]


CHEM_TOPICS = _units([
    ("Atomic structure", ["Bohr model", "Quantum numbers", "Electronic configuration", "Periodic trends", "Ionisation energy", "Electron affinity"]),
    ("Chemical bonding", ["Ionic bonding", "Covalent bonding", "VSEPR theory", "Hybridisation", "Molecular orbital theory", "Hydrogen bonding"]),
    ("Thermodynamics", ["First law", "Enthalpy", "Hess's law", "Entropy", "Gibbs free energy", "Spontaneity"]),
    ("Electrochemistry", ["Electrode potential", "Nernst equation", "Galvanic cells", "Electrolysis", "Batteries", "Corrosion"]),
    ("Water chemistry", ["Hardness of water", "Estimation of hardness", "Boiler troubles", "Softening methods", "Reverse osmosis", "Potable water"]),
    ("Polymers and fuels", ["Classification of polymers", "Addition polymerisation", "Condensation polymerisation", "Engineering plastics",
                            "Calorific value", "Petroleum refining"]),
])
MATH_TOPICS = _units([
    ("Differential calculus", ["Limits and continuity", "Successive differentiation", "Leibnitz theorem", "Taylor series", "Maclaurin series",
                               "Indeterminate forms", "Curvature"]),
    ("Partial differentiation", ["Functions of two variables", "Partial derivatives", "Euler's theorem", "Total derivative", "Jacobians",
                                 "Maxima and minima", "Lagrange multipliers"]),
    ("Integral calculus", ["Definite integrals", "Reduction formulae", "Beta function", "Gamma function", "Area under curves",
                           "Volume of revolution", "Improper integrals"]),
    ("Multiple integrals", ["Double integrals", "Change of order", "Polar coordinates", "Triple integrals", "Area by double integration",
                            "Volume by triple integration", "Centre of gravity"]),
    ("Matrices", ["Rank of a matrix", "System of linear equations", "Eigenvalues", "Eigenvectors", "Cayley-Hamilton theorem",
                  "Diagonalisation", "Quadratic forms"]),
    ("Vector calculus", ["Gradient", "Divergence", "Curl", "Line integrals", "Green's theorem", "Stokes' theorem", "Gauss divergence theorem"]),
])
DM_TOPICS = _units([
    ("Logic", ["Propositional logic", "Predicates and quantifiers", "Rules of inference", "Proof techniques"]),
    ("Sets and relations", ["Set operations", "Relations and their properties", "Equivalence relations", "Partial orders"]),
    ("Combinatorics", ["Counting principles", "Permutations and combinations", "Pigeonhole principle", "Recurrence relations"]),
    ("Graph theory", ["Graph terminology", "Euler and Hamilton paths", "Graph colouring", "Trees and spanning trees"]),
])
CN_TOPICS = _units([
    ("Foundations", ["Network models", "Physical layer", "Transmission media"]),
    ("Data link layer", ["Framing and error detection", "Flow control", "Medium access control"]),
    ("Network layer", ["IP addressing", "Subnetting and CIDR", "Routing algorithms", "IPv4 and IPv6"]),
    ("Transport layer", ["UDP", "TCP", "Congestion control"]),
    ("Application layer", ["DNS", "HTTP", "Email and FTP"]),
])
AI_TOPICS = _units([
    ("Search", ["Intelligent agents", "Uninformed search", "A* search", "Adversarial search"]),
    ("Knowledge", ["Propositional reasoning", "First-order logic", "Inference"]),
    ("Learning", ["Linear regression", "Decision trees", "K-nearest neighbours", "Naive Bayes"]),
    ("Neural networks", ["Perceptron", "Backpropagation", "Model evaluation"]),
])
CC_TOPICS = _units([
    ("Basics", ["Service models", "Deployment models", "Virtualisation", "Hypervisors"]),
    ("Infrastructure", ["Compute services", "Storage services", "Virtual networks", "Load balancing"]),
    ("Platforms", ["Containers", "Orchestration", "Serverless computing"]),
    ("Operations", ["Monitoring", "Cloud security", "Cost management"]),
])

DBMS_TOPICS = [
    (1, "THEORY", "Introduction to DBMS", ["File system vs DBMS", "Three-schema architecture"]),
    (1, "THEORY", "ER Model", ["Entities and attributes", "Relationships", "Cardinality"]),
    (1, "THEORY", "ER to Relational Mapping", ["Mapping entities", "Mapping relationships"]),
    (2, "THEORY", "Relational Algebra", ["Selection and projection", "Joins"]),
    (2, "THEORY", "SQL Basics", ["DDL", "DML", "Simple queries"]),
    (2, "THEORY", "SQL Joins and Subqueries", ["Inner and outer joins", "Nested queries"]),
    (2, "THEORY", "Aggregate Functions and Grouping", ["GROUP BY", "HAVING"]),
    (3, "THEORY", "Functional Dependencies", ["Closure", "Canonical cover"]),
    (3, "THEORY", "Normalization: 1NF to 3NF", ["1NF and 2NF", "3NF"]),
    (3, "THEORY", "BCNF and Decomposition", ["BCNF", "Lossless decomposition"]),
    (4, "THEORY", "Transactions", ["ACID properties", "Transaction states"]),
    (4, "THEORY", "Concurrency Control", ["Lock-based protocols", "Two-phase locking"]),
    (5, "THEORY", "Indexing", ["Ordered indices", "B+ trees"]),
]
DSA_TOPICS = [
    (1, "THEORY", "Complexity Analysis", ["Asymptotic notation", "Best, worst and average case"]),
    (1, "PRACTICAL", "Lab: Array Operations", ["Insertion and deletion", "Linear and binary search"]),
    (1, "THEORY", "Linked Lists", ["Singly linked list", "Insertion and deletion", "Reversal"]),
    (2, "THEORY", "Stacks", ["Array implementation", "Applications", "Expression evaluation"]),
    (2, "THEORY", "Queues", ["Circular queue", "Deque"]),
    (2, "PRACTICAL", "Lab: Stack and Queue", ["Stack using array", "Queue using linked list"]),
    (3, "THEORY", "Quick Sort", ["Partitioning", "Lomuto scheme", "Hoare scheme"]),
    (3, "THEORY", "Merge Sort", ["Divide and conquer", "Merge procedure"]),
    (3, "THEORY", "Heaps and Priority Queues", ["Binary heap", "Heapify", "Heap sort"]),
    (3, "PRACTICAL", "Lab: Sorting Algorithms", ["Quick sort", "Merge sort"]),
    (4, "THEORY", "Binary Search Trees", ["BST property", "Insertion and deletion"]),
    (4, "THEORY", "AVL Trees", ["Balance factor", "Rotations"]),
    (4, "THEORY", "Graphs: Representation", ["Adjacency matrix", "Adjacency list"]),
    (4, "PRACTICAL", "Lab: Trees", ["BST operations", "Tree traversals"]),
    (5, "THEORY", "Graph Traversals", ["BFS", "DFS"]),
    (5, "THEORY", "Shortest Paths", ["Dijkstra", "Bellman-Ford"]),
    (5, "PRACTICAL", "Lab: Graph Algorithms", ["BFS and DFS", "Dijkstra"]),
]
def _teach(db, lec: Lecture, *, om: User, verifier: User, stage: str, partial: bool = False) -> None:
    """Seed only: one class that was held. stage = SUBMITTED (waiting for CL/CH) | CLCH (waiting for OM) | FINAL."""
    plan, on = lec.teaching_plan, lec.schedule.planned_date
    sch = lec.schedule
    pr = LectureProgress(
        lecture_id=lec.id, professor_id=plan.professor_id, actual_completion_date=on, shared_with_students=True, shared_at=at(on, 17, 30),
        execution_status=ExecutionStatus.PARTIALLY_COMPLETED if partial else ExecutionStatus.COMPLETED,
        submission_status=SubmissionStatus.SUBMITTED, submitted_at=at(on, 18), submission_count=1, checkin_mode="TIME",
        professor_started_at=datetime.combine(on, sch.planned_start_time, tzinfo=IST) + timedelta(minutes=2),
        professor_ended_at=datetime.combine(on, sch.planned_end_time, tzinfo=IST) - timedelta(minutes=2),
        remarks="The last subtopic could not be covered; the class ran out of time." if partial else None)
    db.add(pr)
    db.flush()
    keep = len(lec.subtopics) - 1 if partial else len(lec.subtopics)
    for i, sub in enumerate(lec.subtopics):
        pr.subtopic_progress.append(LectureSubtopicProgress(subtopic_id=sub.id, is_covered=i < keep))
    pr.materials.append(LectureMaterial(material_type=MaterialType.LECTURE_NOTES, title=f"Lecture {lec.lecture_no} notes",
                                        file_name=f"lecture-{lec.lecture_no}.pdf", uploaded_by_id=plan.professor_id, uploaded_at=at(on, 17, 10),
                                        file_url=f"https://drive.google.com/file/d/demo-{plan.subject.code.lower()}-{lec.lecture_no:02d}/view"))
    db.add(class_session(lec, plan, on, om, delay=lec.lecture_no % 4, exit_offset=1))
    if stage == "SUBMITTED":
        db.add(Verification(lecture_progress_id=pr.id, round=1, verification_level=VerificationLevel.CL_CH,
                            status=VerificationStatus.PENDING, created_at=pr.submitted_at))
        return
    clch_at = at(on, 18, 40)
    db.add(Verification(lecture_progress_id=pr.id, round=1, verification_level=VerificationLevel.CL_CH, status=VerificationStatus.VERIFIED,
                        verifier_id=verifier.id, verifier_role=Role.CL_CH.value, verified_at=clch_at, created_at=pr.submitted_at))
    if stage == "CLCH":
        db.add(Verification(lecture_progress_id=pr.id, round=1, verification_level=VerificationLevel.OM,
                            status=VerificationStatus.PENDING, created_at=clch_at))
        return
    om_at = at(on, 19, 10)
    db.add(Verification(lecture_progress_id=pr.id, round=1, verification_level=VerificationLevel.OM, status=VerificationStatus.VERIFIED,
                        verifier_id=om.id, verifier_role=Role.OM.value, verified_at=om_at, created_at=clch_at))
    pr.submission_status, pr.final_verified_at = SubmissionStatus.FINAL_VERIFIED, om_at


def seed_minimal(db) -> None:
    """A small institute run from five semester sprint plans (one per class): first-year and senior classes on
    their own timings, last week taught, this week published, and next week's draft waiting with the unfinished
    topic first. Enough classes to see the weekly timetable with several professors teaching at the same time."""
    users = seed_users(db)
    admin, om, cl = users["admin"], users["om1"], users["clch1"]
    p1, p2, p3, p4, p5, p6 = (users[f"professor{i}"] for i in range(1, 7))

    year_start = TODAY.year if TODAY.month >= 7 else TODAY.year - 1
    ay = AcademicYear(name=f"{year_start}–{str(year_start + 1)[-2:]}", start_date=date(year_start, 7, 1),
                      end_date=date(year_start + 1, 6, 30), is_current=True)
    dept = Department(code="BT", name="B.Tech")
    db.add_all([ay, dept])
    db.flush()
    for u in users.values():
        u.department_id = dept.id
    this_week = TODAY - timedelta(days=TODAY.weekday())
    start_d, end_d = this_week - timedelta(days=7), this_week + timedelta(days=7 * 7 + 5)   # nine weeks, began last Monday
    odd = TODAY.month >= 7
    numbers = (1, 3, 5, 7) if odd else (2, 4, 6, 8)
    roman = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII", 8: "VIII"}
    branch = Branch(department_id=dept.id, code="CSE", name="Computer Science & Engineering")
    db.add(branch)
    db.flush()
    sems = {n: Semester(academic_year_id=ay.id, number=n, name=f"Semester {roman[n]}", is_current=n == numbers[2],
                        start_date=start_d - timedelta(days=14), end_date=end_d + timedelta(days=14)) for n in numbers}
    db.add_all(sems.values())
    db.flush()
    y1, y2, y3, y4 = (sems[n] for n in numbers)
    sections = {(s.number, name): Section(branch_id=branch.id, semester_id=s.id, name=name, student_count=60)
                for s in sems.values() for name in (("A", "B") if s is y1 else ("A",))}
    db.add_all(sections.values())
    for name, kind in (("210", "CLASSROOM"), ("211", "CLASSROOM"), ("215", "CLASSROOM"), ("314", "CLASSROOM"), ("410", "CLASSROOM"), ("Lab 301", "LAB")):
        db.add(Room(name=name, room_type=kind, capacity=30 if kind == "LAB" else 60))
    db.add(Holiday(date=_workday(TODAY + timedelta(days=24)), name="Institute Foundation Day"))
    db.commit()

    # (sprint plan, semester, section, room) and its subjects: code, name, short, professor, classes/week, labs/week, topics
    classes = (
        (f"First Year · Sem {roman[y1.number]}-A", y1, "A", "210", (
            ("BT-101", "Engineering Chemistry", "CHEM", p3, 6, 0, CHEM_TOPICS),
            ("BT-102", "Mathematics-I", "MATH-I", p2, 7, 0, MATH_TOPICS))),
        (f"First Year · Sem {roman[y1.number]}-B", y1, "B", "211", (
            ("BT-101", "Engineering Chemistry", "CHEM", p4, 6, 0, CHEM_TOPICS),
            ("BT-102", "Mathematics-I", "MATH-I", p5, 7, 0, MATH_TOPICS))),
        (f"Second Year · Sem {roman[y2.number]}-A", y2, "A", "314", (
            ("CS-301", "Database Management Systems", "DBMS", p2, 1, 0, DBMS_TOPICS),       # 1 a week on purpose: shown as At risk
            ("CS-302", "Discrete Mathematics", "DM", p6, 3, 0, DM_TOPICS))),
        (f"Third Year · Sem {roman[y3.number]}-A", y3, "A", "215", (
            ("CS-501", "Data Structures & Algorithms", "DSA", p1, 3, 1, DSA_TOPICS),
            ("CS-503", "Computer Networks", "CN", p4, 3, 0, CN_TOPICS))),
        (f"Fourth Year · Sem {roman[y4.number]}-A", y4, "A", "410", (
            ("CS-701", "Artificial Intelligence", "AI", p3, 3, 0, AI_TOPICS),
            ("CS-702", "Cloud Computing", "CC", p6, 3, 0, CC_TOPICS))),
    )
    subjects: dict[str, Subject] = {}
    plans: list[tuple[str, TeachingPlan]] = []
    sprint_ids: list[str] = []
    for title, sem, sec, room, subs in classes:
        sp_id = sprint_plan_service.create(db, admin, SprintPlanIn(
            name=f"{title} Sprint Plan – {start_d:%b %Y}", academic_year_id=ay.id, start_date=start_d, end_date=end_d,
            working_days=[0, 1, 2, 3, 4, 5]))["id"]
        sprint_ids.append(sp_id)
        for code, name, short, prof, per_week, labs, topics in subs:
            if code not in subjects:
                subjects[code] = Subject(code=code, name=name, short_name=short, branch_id=branch.id, semester_number=sem.number, credits=4)
                db.add(subjects[code])
                db.commit()
            plan = teaching_plan_service.create_plan(db, admin, TeachingPlanCreate(
                academic_year_id=ay.id, semester_id=sem.id, department_id=dept.id, branch_id=branch.id, section_id=sections[(sem.number, sec)].id,
                subject_id=subjects[code].id, professor_id=prof.id, room=room, classes_per_week=per_week, labs_per_week=labs,
                lab_room="Lab 301" if labs else None, sprint_plan_id=sp_id, name=f"{name} – {sem.name} – Section {sec}"))
            for i, (unit, ltype, topic, st) in enumerate(topics, start=1):
                lec = Lecture(teaching_plan_id=plan.id, sequence=i, serial_no=i, lecture_no=i, lecture_type=ltype, unit_no=unit,
                              content_topic=topic, blooms_taxonomy="K3", is_released=False)
                lec.subtopics = [LectureSubtopic(position=n, title=t) for n, t in enumerate(st, start=1)]
                lec.schedule = LectureSchedule()
                db.add(lec)
            db.commit()
            plans.append((f"{short}-{sem.number}{sec}", plan))

    # One subject is left without a professor or topics, to try "Add subject -> Import topics -> Regenerate" by hand.
    db.add(Subject(code="CS-502", name="Operating Systems", short_name="OS", branch_id=branch.id, semester_number=y3.number, credits=4))
    db.commit()

    # GENERATE SEMESTER SPRINT for each plan - from its first day, so last week exists too.
    scheduled = sum(sprint_plan_service.generate(db, admin, uuid.UUID(i), from_date=start_d)["generation"]["scheduled"] for i in sprint_ids)

    # Last week was published and taught; this week is published and running.
    for _, plan in plans:
        db.refresh(plan)
        for lec in plan.lectures:
            if lec.schedule.planned_date and lec.schedule.planned_date < this_week + timedelta(days=7):
                lec.is_released = True
    db.flush()
    special = {f"DSA-{y3.number}A": ("SUBMITTED", True),      # a submission waiting for CL/CH, one subtopic left -> carry-forward
               f"MATH-I-{y1.number}A": ("CLCH", False),      # verified by CL/CH, waiting for the OM's final verification
               f"CHEM-{y1.number}A": ("SUBMITTED", False),   # waiting for CL/CH
               f"AI-{y4.number}A": ("SUBMITTED", False)}
    for key, plan in plans:
        held = sorted((l for l in plan.lectures if l.schedule.planned_date and l.schedule.planned_date < TODAY),
                      key=lambda l: (l.schedule.planned_date, l.schedule.planned_start_time))
        for n, lec in enumerate(held):
            stage, partial = special[key] if key in special and n == len(held) - 1 else ("FINAL", False)
            _teach(db, lec, om=om, verifier=cl, stage=stage, partial=partial)
    db.commit()

    # MAKE WEEKLY SPRINT PLAN for next week, exactly as the admin does it. It stays a draft.
    result = sprint_service.generate_week(db, admin, SprintGenerate())["generation"]
    print(f"Seeded demo data: {len(DEMO_USERS)} accounts; {len(sprint_ids)} sprint plans ({start_d:%d %b} – {end_d:%d %b %Y}), one per class, "
          f"{len(plans)} subjects; {scheduled} classes scheduled over the semester; last week taught, this week published, "
          f"next week drafted ({result['carry_forward']} carry-forward item first).\n"
          f"Sign in with: {DEMO_LOGINS}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="Delete all existing rows first")
    parser.add_argument("--full", action="store_true", help="Seed the large demonstration dataset instead of the minimal one")
    parser.add_argument("--empty", action="store_true", help="Seed only the demo accounts; no academic data at all")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        if args.reset:
            reset(db)
        elif db.scalar(select(User.id).limit(1)):
            fixed = ensure_sign_in(db)
            print((f"{fixed} existing account(s) had no password: they can now sign in with the password {DEMO_PASSWORD} "
                   "(email or employee ID as the username) and will be asked to change it. " if fixed
                   else "Database already has data; nothing was changed. ") + "Use --reset to wipe it and seed again.")
            return
        # Build everything locally first, then upload it to MongoDB Atlas in one go: thousands of small
        # round trips to the cloud would take minutes, one bulk upload takes seconds.
        store.deferred = True
        print("Building the demo data ...", flush=True)
        if args.full:
            seed(db)
        elif args.empty:
            seed_users(db)
            print(f"Seeded {len(DEMO_USERS)} demo accounts and no academic data. Sign in as admin / Admin@123 "
                  "and start from Admin → Academic Setup.")
        else:
            seed_minimal(db)
        db.close()
        print("Uploading to MongoDB Atlas ...", flush=True)
        count = store.push_all(engine)
        print(f"Done: {count} documents are in MongoDB database '{store.db.name}'. "
              "Restart the backend (uvicorn) if it is running, so it loads the new data.")
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
