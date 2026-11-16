from __future__ import annotations

import json
import sqlite3
import uuid
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, Response, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.auth import hash_password, verify_password, new_session_token, token_digest, new_join_code
from app.assessment import assess_explanation
from app.intervention_planner import build_intervention_plan
from app.adaptive import adaptation_summary
from app.curriculum import get_lesson
from app.llm import generate_reply, public_status
from app.learning_journey import build_learning_journey
from app.pedagogy import advance_state, initial_state, state_context
from app.teacher_intelligence import build_review_priorities

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "pupil_zero.db"
app = FastAPI(title="PUPIL ZERO", version="1.2.0", description="Local-first learning-by-teaching MVP")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


class StartRequest(BaseModel):
    lesson_id: str = "fractions"
    persona: str = "milo"
    learner_id: str | None = Field(default=None, min_length=36, max_length=36)
    class_id: str | None = None
    assignment_id: str | None = None


class MessageRequest(BaseModel):
    session_id: str
    text: str = Field(min_length=1, max_length=3000)


class FinishRequest(BaseModel):
    session_id: str


class TeacherRegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(min_length=2, max_length=80)

class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128)

class ClassCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    grade_label: str = Field(default="", max_length=40)

class StudentJoinRequest(BaseModel):
    join_code: str = Field(min_length=8, max_length=8)
    display_name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=10, max_length=128)

class AssignmentCreateRequest(BaseModel):
    class_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=1500)
    lesson_id: str = Field(min_length=1, max_length=64)
    due_at: str = Field(default="", max_length=40)

class InterventionFeedbackRequest(BaseModel):
    lesson_id: str
    concept_id: str
    rating: str = Field(pattern="^(helpful|partly_helpful|not_helpful)$")
    note: str = Field(default="", max_length=500)


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY, lesson_id TEXT NOT NULL, persona TEXT NOT NULL,
            transcript TEXT NOT NULL DEFAULT '[]', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            state_json TEXT NOT NULL DEFAULT '{}', learner_id TEXT
        )""")
        columns = {row["name"] for row in con.execute("PRAGMA table_info(sessions)")}
        if "state_json" not in columns:
            con.execute("ALTER TABLE sessions ADD COLUMN state_json TEXT NOT NULL DEFAULT '{}'")
        if "learner_id" not in columns:
            con.execute("ALTER TABLE sessions ADD COLUMN learner_id TEXT")
        for column in ("student_id", "class_id", "teacher_id"):
            if column not in columns:
                con.execute("ALTER TABLE sessions ADD COLUMN " + column + " TEXT")
        con.execute("""CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('teacher','student')),
            password_salt TEXT NOT NULL, password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS auth_sessions (
            token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
            expires_at INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS classes (
            id TEXT PRIMARY KEY, teacher_id TEXT NOT NULL REFERENCES users(id),
            name TEXT NOT NULL, grade_label TEXT NOT NULL DEFAULT '',
            join_code TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS class_members (
            class_id TEXT NOT NULL REFERENCES classes(id),
            student_id TEXT NOT NULL REFERENCES users(id),
            joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(class_id, student_id)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS intervention_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id TEXT NOT NULL,
            concept_id TEXT NOT NULL,
            rating TEXT NOT NULL CHECK(rating IN ('helpful', 'partly_helpful', 'not_helpful')),
            note TEXT NOT NULL DEFAULT '',
            teacher_id TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        feedback_columns = {row["name"] for row in con.execute("PRAGMA table_info(intervention_feedback)")}
        if "teacher_id" not in feedback_columns:
            con.execute("ALTER TABLE intervention_feedback ADD COLUMN teacher_id TEXT")
        con.execute("""CREATE TABLE IF NOT EXISTS assignments (
            id TEXT PRIMARY KEY, teacher_id TEXT NOT NULL REFERENCES users(id),
            class_id TEXT NOT NULL REFERENCES classes(id), title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '', lesson_id TEXT NOT NULL,
            due_at TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS assignment_submissions (
            assignment_id TEXT NOT NULL REFERENCES assignments(id),
            student_id TEXT NOT NULL REFERENCES users(id),
            session_id TEXT NOT NULL REFERENCES sessions(id),
            submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(assignment_id, student_id)
        )""")
        session_columns = {row["name"] for row in con.execute("PRAGMA table_info(sessions)")}
        if "assignment_id" not in session_columns:
            con.execute("ALTER TABLE sessions ADD COLUMN assignment_id TEXT")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.middleware("http")
async def teacher_auth_guard(request: Request, call_next):
    token = request.cookies.get("pupil_session", "")
    user = None
    if token:
        with db() as con:
            user = con.execute(
                "SELECT u.id,u.email,u.display_name,u.role FROM auth_sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?",
                (token_digest(token), int(time.time())),
            ).fetchone()
    request.state.user = dict(user) if user else None
    path = request.url.path
    if path == "/teacher" or path.startswith("/api/teacher"):
        if not user or user["role"] != "teacher":
            if path == "/teacher":
                return HTMLResponse("<!doctype html><html lang=ar dir=rtl><meta charset=utf-8><body><h1>تسجيل دخول المدرّس مطلوب</h1><p><a href=/account>افتح صفحة الحسابات لتسجيل الدخول</a></p></body></html>", status_code=401)
            return JSONResponse({"detail": "Teacher authentication required"}, status_code=401)
    return await call_next(request)

def current_teacher(request: Request) -> dict[str, Any]:
    user = getattr(request.state, "user", None)
    if not user or user.get("role") != "teacher": raise HTTPException(401, "Teacher authentication required")
    return user

def current_student(request: Request) -> dict[str, Any]:
    user = getattr(request.state, "user", None)
    if not user or user.get("role") != "student": raise HTTPException(401, "Student authentication required")
    return user

@app.post("/api/auth/register-teacher", status_code=201)
def register_teacher(payload: TeacherRegisterRequest, response: Response) -> dict[str, Any]:
    email = payload.email.strip().lower()
    if "@" not in email: raise HTTPException(422, "Enter a valid email address")
    salt, digest = hash_password(payload.password)
    user_id, token = str(uuid.uuid4()), new_session_token()
    with db() as con:
        try: con.execute("INSERT INTO users(id,email,display_name,role,password_salt,password_hash) VALUES(?,?,?,'teacher',?,?)", (user_id,email,payload.display_name.strip(),salt,digest))
        except sqlite3.IntegrityError as exc: raise HTTPException(409,"An account with this email already exists") from exc
        con.execute("INSERT INTO auth_sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",(token_digest(token),user_id,int(time.time())+604800))
    response.set_cookie("pupil_session",token,httponly=True,samesite="strict",max_age=604800,path="/")
    return {"user":{"id":user_id,"email":email,"display_name":payload.display_name.strip(),"role":"teacher"}}

@app.post("/api/auth/login")
def login(payload: LoginRequest, response: Response) -> dict[str, Any]:
    with db() as con: user=con.execute("SELECT * FROM users WHERE email=?",(payload.email.strip().lower(),)).fetchone()
    if not user or not verify_password(payload.password,user["password_salt"],user["password_hash"]): raise HTTPException(401,"Invalid email or password")
    token=new_session_token()
    with db() as con: con.execute("INSERT INTO auth_sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",(token_digest(token),user["id"],int(time.time())+604800))
    response.set_cookie("pupil_session",token,httponly=True,samesite="strict",max_age=604800,path="/")
    return {"user":{"id":user["id"],"email":user["email"],"display_name":user["display_name"],"role":user["role"]}}

@app.get("/api/auth/me")
def auth_me(request: Request) -> dict[str, Any]:
    token = request.cookies.get("pupil_session", "")
    if not token:
        raise HTTPException(401, "Not authenticated")
    with db() as con:
        user = con.execute(
            "SELECT u.id,u.email,u.display_name,u.role FROM auth_sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?",
            (token_digest(token), int(time.time())),
        ).fetchone()
    if not user:
        raise HTTPException(401, "Not authenticated")
    return {"user": dict(user)}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response) -> dict[str,bool]:
    token=request.cookies.get("pupil_session","")
    if token:
        with db() as con: con.execute("DELETE FROM auth_sessions WHERE token_hash=?",(token_digest(token),))
    response.delete_cookie("pupil_session",path="/")
    return {"logged_out":True}

@app.post("/api/classes", status_code=201)
def create_class(payload: ClassCreateRequest, teacher: dict[str,Any] = Depends(current_teacher)) -> dict[str,Any]:
    class_id, code = str(uuid.uuid4()), new_join_code()
    with db() as con:
        while con.execute("SELECT 1 FROM classes WHERE join_code=?",(code,)).fetchone(): code=new_join_code()
        con.execute("INSERT INTO classes(id,teacher_id,name,grade_label,join_code) VALUES(?,?,?,?,?)",(class_id,teacher["id"],payload.name.strip(),payload.grade_label.strip(),code))
    return {"id":class_id,"name":payload.name.strip(),"grade_label":payload.grade_label.strip(),"join_code":code}

@app.get("/api/classes")
def list_classes(teacher: dict[str,Any] = Depends(current_teacher)) -> dict[str,Any]:
    with db() as con: rows=con.execute("SELECT c.id,c.name,c.grade_label,c.join_code,COUNT(m.student_id) AS student_count FROM classes c LEFT JOIN class_members m ON m.class_id=c.id WHERE c.teacher_id=? GROUP BY c.id",(teacher["id"],)).fetchall()
    return {"classes":[dict(row) for row in rows]}

@app.get("/api/student/classes")
def student_classes(student: dict[str,Any] = Depends(current_student)) -> dict[str,Any]:
    with db() as con:
        rows = con.execute("SELECT c.id,c.name,c.grade_label,c.teacher_id,u.display_name AS teacher_name FROM class_members m JOIN classes c ON c.id=m.class_id JOIN users u ON u.id=c.teacher_id WHERE m.student_id=? ORDER BY c.created_at DESC",(student["id"],)).fetchall()
    return {"classes":[dict(row) for row in rows]}

@app.get("/api/classes/{class_id}/members")
def class_members(class_id: str, teacher: dict[str,Any] = Depends(current_teacher)) -> dict[str,Any]:
    with db() as con:
        if not con.execute("SELECT 1 FROM classes WHERE id=? AND teacher_id=?",(class_id,teacher["id"])).fetchone(): raise HTTPException(404,"Class not found")
        rows=con.execute("SELECT u.id,u.display_name,u.email,m.joined_at FROM class_members m JOIN users u ON u.id=m.student_id WHERE m.class_id=?",(class_id,)).fetchall()
    return {"members":[dict(row) for row in rows]}

@app.post("/api/classes/join", status_code=201)
def join_class(payload: StudentJoinRequest, response: Response) -> dict[str,Any]:
    email=payload.email.strip().lower()
    if "@" not in email: raise HTTPException(422,"Enter a valid email address")
    with db() as con:
        classroom=con.execute("SELECT id,name FROM classes WHERE join_code=?",(payload.join_code.strip().upper(),)).fetchone()
        if not classroom: raise HTTPException(404,"Invalid class code")
        salt,digest=hash_password(payload.password); student_id=str(uuid.uuid4())
        try: con.execute("INSERT INTO users(id,email,display_name,role,password_salt,password_hash) VALUES(?,?,?,'student',?,?)",(student_id,email,payload.display_name.strip(),salt,digest))
        except sqlite3.IntegrityError as exc: raise HTTPException(409,"An account with this email already exists") from exc
        con.execute("INSERT INTO class_members(class_id,student_id) VALUES(?,?)",(classroom["id"],student_id))
        token = new_session_token()
        con.execute("INSERT INTO auth_sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",(token_digest(token),student_id,int(time.time())+604800))
    response.set_cookie("pupil_session",token,httponly=True,samesite="strict",max_age=604800,path="/")
    return {"student":{"id":student_id,"display_name":payload.display_name.strip()},"class":{"id":classroom["id"],"name":classroom["name"]}}

@app.post("/api/teacher/assignments", status_code=201)
def create_assignment(payload: AssignmentCreateRequest, teacher: dict[str,Any] = Depends(current_teacher)) -> dict[str,Any]:
    if not get_lesson(payload.lesson_id):
        raise HTTPException(404, "Lesson not found")
    assignment_id = str(uuid.uuid4())
    with db() as con:
        classroom = con.execute("SELECT id FROM classes WHERE id=? AND teacher_id=?", (payload.class_id, teacher["id"])).fetchone()
        if not classroom:
            raise HTTPException(404, "Class not found")
        con.execute("INSERT INTO assignments(id,teacher_id,class_id,title,description,lesson_id,due_at) VALUES(?,?,?,?,?,?,?)",
                    (assignment_id, teacher["id"], payload.class_id, payload.title.strip(), payload.description.strip(), payload.lesson_id, payload.due_at.strip()))
    return {"id": assignment_id, "title": payload.title.strip(), "class_id": payload.class_id, "lesson_id": payload.lesson_id, "due_at": payload.due_at.strip()}

@app.get("/api/teacher/assignments")
def teacher_assignments(class_id: str | None = Query(default=None), teacher: dict[str,Any] = Depends(current_teacher)) -> dict[str,Any]:
    with db() as con:
        query = """SELECT a.*, c.name AS class_name,
                   (SELECT COUNT(*) FROM class_members m WHERE m.class_id=a.class_id) AS student_count
                   FROM assignments a JOIN classes c ON c.id=a.class_id WHERE a.teacher_id=?"""
        params: list[Any] = [teacher["id"]]
        if class_id:
            if not con.execute("SELECT 1 FROM classes WHERE id=? AND teacher_id=?", (class_id, teacher["id"])).fetchone():
                raise HTTPException(404, "Class not found")
            query += " AND a.class_id=?"
            params.append(class_id)
        query += " ORDER BY a.created_at DESC"
        assignments = con.execute(query, tuple(params)).fetchall()
        results = []
        for assignment in assignments:
            submissions = con.execute("""SELECT u.id AS student_id,u.display_name,s.session_id,s.submitted_at,
                CASE WHEN s.student_id IS NULL THEN 0 ELSE 1 END AS submitted
                FROM class_members m JOIN users u ON u.id=m.student_id
                LEFT JOIN assignment_submissions s ON s.assignment_id=? AND s.student_id=u.id
                WHERE m.class_id=? ORDER BY u.display_name""", (assignment["id"], assignment["class_id"])).fetchall()
            results.append({**dict(assignment), "submitted_count": sum(item["submitted"] for item in submissions),
                            "students": [dict(item) for item in submissions]})
    return {"assignments": results}

@app.get("/api/student/assignments")
def student_assignments(class_id: str | None = Query(default=None), student: dict[str,Any] = Depends(current_student)) -> dict[str,Any]:
    with db() as con:
        query = """SELECT a.id,a.title,a.description,a.lesson_id,a.due_at,a.class_id,c.name AS class_name,
                   CASE WHEN sub.student_id IS NULL THEN 0 ELSE 1 END AS submitted,
                   sub.submitted_at,sub.session_id
                   FROM assignments a JOIN classes c ON c.id=a.class_id
                   JOIN class_members m ON m.class_id=a.class_id
                   LEFT JOIN assignment_submissions sub ON sub.assignment_id=a.id AND sub.student_id=?
                   WHERE m.student_id=?"""
        params: list[Any] = [student["id"], student["id"]]
        if class_id:
            query += " AND a.class_id=?"
            params.append(class_id)
        query += " ORDER BY CASE WHEN sub.student_id IS NULL THEN 0 ELSE 1 END, a.created_at DESC"
        rows = con.execute(query, tuple(params)).fetchall()
    return {"assignments": [dict(row) for row in rows]}

@app.get("/account", response_class=HTMLResponse)
def account_page() -> str:
    return (ROOT / "static" / "account.html").read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return (ROOT / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/teacher", response_class=HTMLResponse)
def teacher_home() -> str:
    return (ROOT / "static" / "teacher.html").read_text(encoding="utf-8")


@app.get("/api/teacher/sessions")
def teacher_sessions(limit: int = Query(default=30, ge=1, le=100), class_id: str | None = Query(default=None), teacher: dict[str,Any] = Depends(current_teacher)) -> dict[str, Any]:
    """List only sessions owned by this teacher, optionally narrowed to one owned class."""
    with db() as con:
        if class_id and not con.execute("SELECT 1 FROM classes WHERE id=? AND teacher_id=?", (class_id, teacher["id"])).fetchone():
            raise HTTPException(404, "Class not found")
        if class_id:
            rows = con.execute(
                "SELECT s.id, s.lesson_id, s.persona, s.transcript, s.created_at, s.class_id, c.name AS class_name FROM sessions s LEFT JOIN classes c ON c.id=s.class_id WHERE s.teacher_id=? AND s.class_id=? ORDER BY s.created_at DESC LIMIT ?", (teacher["id"], class_id, limit)
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT s.id, s.lesson_id, s.persona, s.transcript, s.created_at, s.class_id, c.name AS class_name FROM sessions s LEFT JOIN classes c ON c.id=s.class_id WHERE s.teacher_id=? ORDER BY s.created_at DESC LIMIT ?", (teacher["id"], limit)
            ).fetchall()
    items = []
    for row in rows:
        transcript = json.loads(row["transcript"])
        lesson = get_lesson(row["lesson_id"])
        if not lesson:
            continue
        report = assess_explanation(transcript, lesson)
        items.append({
            "session_id": row["id"],
            "short_id": row["id"][:8],
            "lesson": lesson["title_ar"],
            "persona": row["persona"],
            "created_at": row["created_at"],
            "class_id": row["class_id"],
            "class_name": row["class_name"],
            "student_turns": sum(1 for message in transcript if message.get("role") == "student"),
            "coverage_signal": report["coverage_signal"],
            "label": report["label"],
        })
    return {"sessions": items, "count": len(items), "notice": "Only sessions created within this teacher account are shown; legacy unassigned sessions are excluded."}


@app.get("/api/teacher/insights")
def teacher_insights(lesson_id: str | None = Query(default=None), class_id: str | None = Query(default=None), teacher: dict[str,Any] = Depends(current_teacher)) -> dict[str, Any]:
    """Aggregate cautious, session-level evidence signals for teacher review."""
    if lesson_id and not get_lesson(lesson_id):
        raise HTTPException(404, "Lesson not found")

    with db() as con:
        if class_id and not con.execute("SELECT 1 FROM classes WHERE id=? AND teacher_id=?", (class_id, teacher["id"])).fetchone():
            raise HTTPException(404, "Class not found")
        filters = ["teacher_id=?"]
        params: list[Any] = [teacher["id"]]
        if class_id:
            filters.append("class_id=?")
            params.append(class_id)
        if lesson_id:
            filters.append("lesson_id=?")
            params.append(lesson_id)
        rows = con.execute(
            "SELECT lesson_id, transcript, state_json FROM sessions WHERE " + " AND ".join(filters),
            tuple(params),
        ).fetchall()

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        lesson = get_lesson(row["lesson_id"])
        if not lesson:
            continue
        try:
            transcript = json.loads(row["transcript"] or "[]")
            state = json.loads(row["state_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        grouped.setdefault(row["lesson_id"], []).append({
            "lesson": lesson,
            "transcript": transcript if isinstance(transcript, list) else [],
            "state": state if isinstance(state, dict) else {},
        })

    summaries = []
    for current_id, records in grouped.items():
        lesson = records[0]["lesson"]
        concept_rows = []
        for concept in lesson.get("concepts", []):
            evidence_sessions = 0
            review_sessions = 0
            for record in records:
                report = assess_explanation(record["transcript"], lesson)
                if any(
                    item["concept_id"] == concept["id"] and item["status"] == "evidence_found"
                    for item in report["concepts"]
                ):
                    evidence_sessions += 1
                if concept["id"] in record["state"].get("review_targets", []):
                    review_sessions += 1
            concept_rows.append({
                "concept_id": concept["id"],
                "concept": concept["label_ar"],
                "sessions_with_keyword_evidence": evidence_sessions,
                "sessions_flagged_for_review": review_sessions,
                "review_signal": review_sessions > 0,
            })
        summaries.append({
            "lesson_id": current_id,
            "lesson": lesson["title_ar"],
            "session_count": len(records),
            "student_response_sessions": sum(
                any(m.get("role") == "student" for m in record["transcript"])
                for record in records
            ),
            "concepts": concept_rows,
            "notice": "Counts describe keyword matches and dialogue review flags, not class mastery or student grades.",
        })

    summaries.sort(key=lambda item: item["lesson"])
    return {
        "lesson_filter": lesson_id,
        "class_filter": class_id,
        "total_sessions": sum(item["session_count"] for item in summaries),
        "lessons": summaries,
        "notice": "Prototype aggregate based on local sessions only. Small samples, spelling, dialect, and keyword matching can distort signals; teacher review is required.",
    }

@app.get("/api/teacher/interventions")
def teacher_intervention_plan(lesson_id: str = Query(...), concept_id: str = Query(...), teacher: dict[str,Any] = Depends(current_teacher)) -> dict[str, Any]:
    """Create a teacher-reviewed suggestion from authored lesson material."""
    lesson = get_lesson(lesson_id)
    if not lesson:
        raise HTTPException(404, "Lesson not found")
    plan = build_intervention_plan(lesson, concept_id)
    if not plan:
        raise HTTPException(404, "Concept not found in this lesson")
    with db() as con:
        rows = con.execute(
            "SELECT rating, COUNT(*) AS count FROM intervention_feedback WHERE lesson_id=? AND concept_id=? AND teacher_id=? GROUP BY rating",
            (lesson_id, concept_id, teacher["id"]),
        ).fetchall()
    counts = {"helpful": 0, "partly_helpful": 0, "not_helpful": 0}
    for row in rows:
        counts[row["rating"]] = row["count"]
    plan["feedback_summary"] = {"total": sum(counts.values()), **counts}
    return plan


@app.post("/api/teacher/interventions/feedback", status_code=201)
def save_intervention_feedback(payload: InterventionFeedbackRequest, teacher: dict[str,Any] = Depends(current_teacher)) -> dict[str, Any]:
    """Store an anonymous teacher rating; notes are optional and never exposed in aggregates."""
    lesson = get_lesson(payload.lesson_id)
    if not lesson:
        raise HTTPException(404, "Lesson not found")
    if not any(item.get("id") == payload.concept_id for item in lesson.get("concepts", [])):
        raise HTTPException(404, "Concept not found in this lesson")
    with db() as con:
        con.execute(
            "INSERT INTO intervention_feedback(lesson_id, concept_id, rating, note, teacher_id) VALUES (?, ?, ?, ?, ?)",
            (payload.lesson_id, payload.concept_id, payload.rating, payload.note.strip(), teacher["id"]),
        )
    return {"saved": True, "message": "تم حفظ تقييم الخطة بدون بيانات تعريفية."}


@app.get("/api/teacher/interventions/feedback")
def intervention_feedback_summary(lesson_id: str = Query(...), concept_id: str = Query(...), teacher: dict[str,Any] = Depends(current_teacher)) -> dict[str, Any]:
    lesson = get_lesson(lesson_id)
    if not lesson:
        raise HTTPException(404, "Lesson not found")
    if not any(item.get("id") == concept_id for item in lesson.get("concepts", [])):
        raise HTTPException(404, "Concept not found in this lesson")
    with db() as con:
        rows = con.execute(
            "SELECT rating, COUNT(*) AS count FROM intervention_feedback WHERE lesson_id=? AND concept_id=? AND teacher_id=? GROUP BY rating",
            (lesson_id, concept_id, teacher["id"]),
        ).fetchall()
    counts = {"helpful": 0, "partly_helpful": 0, "not_helpful": 0}
    for row in rows:
        counts[row["rating"]] = row["count"]
    total = sum(counts.values())
    return {
        "lesson_id": lesson_id, "concept_id": concept_id,
        "total": total, **counts,
        "sample_notice": "العينة صغيرة؛ لا تستنتج نمطًا من أقل من 3 تقييمات." if total < 3 else "ملخص وصفي لتقييمات المدرسين، وليس مقياسًا لجودة التدريس أو تعلم الطلاب.",
    }


@app.get("/api/teacher/priorities")
def teacher_priorities(lesson_id: str | None = Query(default=None), class_id: str | None = Query(default=None), teacher: dict[str,Any] = Depends(current_teacher)) -> dict[str, Any]:
    """Return cautious review priorities within this teacher's account and optional class."""
    insights = teacher_insights(lesson_id=lesson_id, class_id=class_id, teacher=teacher)
    return build_review_priorities(insights)


@app.get("/api/learner/journey/{learner_id}")
def learner_journey(learner_id: str, request: Request) -> dict[str, Any]:
    """Return an anonymous learner's chronological evidence history."""
    try:
        learner_id = str(uuid.UUID(learner_id))
    except ValueError as exc:
        raise HTTPException(422, "learner_id must be a UUID") from exc
    with db() as con:
        user = getattr(request.state, "user", None)
        if user and user.get("role") == "student":
            if learner_id != user["id"]:
                raise HTTPException(403, "You can only view your own learning journey")
            rows = con.execute("SELECT id, lesson_id, transcript, created_at FROM sessions WHERE student_id=? ORDER BY created_at ASC, id ASC", (user["id"],)).fetchall()
        else:
            rows = con.execute("SELECT id, lesson_id, transcript, created_at FROM sessions WHERE learner_id=? AND student_id IS NULL ORDER BY created_at ASC, id ASC", (learner_id,)).fetchall()
    records = []
    for row in rows:
        lesson = get_lesson(row["lesson_id"])
        if not lesson:
            continue
        try:
            transcript = json.loads(row["transcript"] or "[]")
        except (TypeError, json.JSONDecodeError):
            transcript = []
        records.append({
            "session_id": row["id"], "lesson_id": row["lesson_id"],
            "lesson": lesson["title_ar"], "created_at": row["created_at"],
            "report": assess_explanation(transcript, lesson),
        })
    return {"learner_id": learner_id, **build_learning_journey(records)}


@app.get("/api/teacher/sessions/{session_id}")
def teacher_session_detail(session_id: str, teacher: dict[str,Any] = Depends(current_teacher)) -> dict[str, Any]:
    with db() as con:
        row = con.execute("SELECT * FROM sessions WHERE id=? AND teacher_id=?", (session_id, teacher["id"])).fetchone()
    if not row:
        raise HTTPException(404, "Session not found")
    transcript = json.loads(row["transcript"])
    lesson = get_lesson(row["lesson_id"])
    return {
        "session_id": row["id"],
        "lesson": lesson["title_ar"],
        "persona": row["persona"],
        "created_at": row["created_at"],
        "transcript": transcript,
        "report": assess_explanation(transcript, lesson),
        "dialogue_state": json.loads(row["state_json"] or "{}"),
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "product": "PUPIL ZERO", "version": "1.2.0", **public_status()}


@app.get("/api/lessons")
def lessons() -> list[dict[str, str]]:
    from app.curriculum import list_lessons
    return list_lessons()


@app.post("/api/sessions")
def start_session(payload: StartRequest, request: Request) -> dict[str, Any]:
    lesson = get_lesson(payload.lesson_id)
    if not lesson:
        raise HTTPException(404, "Lesson not found")
    if payload.persona not in {"milo", "noura", "zizo"}:
        raise HTTPException(422, "Unknown classmate persona")
    session_id = str(uuid.uuid4())
    user = getattr(request.state, "user", None)
    student_id = class_id = teacher_id = None
    if user and user.get("role") == "student":
        if not payload.class_id:
            raise HTTPException(422, "Choose a classroom before starting")
        with db() as con:
            membership = con.execute("SELECT c.id,c.teacher_id FROM class_members m JOIN classes c ON c.id=m.class_id WHERE m.class_id=? AND m.student_id=?", (payload.class_id, user["id"])).fetchone()
        if not membership:
            raise HTTPException(403, "You are not enrolled in this classroom")
        student_id, class_id, teacher_id = user["id"], membership["id"], membership["teacher_id"]
        learner_id = user["id"]
        if payload.assignment_id:
            with db() as con:
                assignment = con.execute("SELECT id,lesson_id,class_id FROM assignments WHERE id=? AND class_id=?", (payload.assignment_id, class_id)).fetchone()
                already = con.execute("SELECT 1 FROM assignment_submissions WHERE assignment_id=? AND student_id=?", (payload.assignment_id, student_id)).fetchone()
            if not assignment:
                raise HTTPException(404, "Assignment not found for this class")
            if assignment["lesson_id"] != payload.lesson_id:
                raise HTTPException(422, "Choose the lesson assigned by your teacher")
            if already:
                raise HTTPException(409, "This assignment has already been submitted")
    elif user and user.get("role") == "teacher":
        teacher_id = user["id"]
        learner_id = payload.learner_id or str(uuid.uuid4())
    else:
        learner_id = payload.learner_id or str(uuid.uuid4())
    try:
        learner_id = str(uuid.UUID(learner_id))
    except ValueError as exc:
        raise HTTPException(422, "learner_id must be a UUID") from exc
    with db() as con:
        if student_id:
            previous_states = con.execute("SELECT state_json FROM sessions WHERE student_id=? AND lesson_id=? ORDER BY created_at DESC LIMIT 10", (student_id, payload.lesson_id)).fetchall()
        else:
            previous_states = con.execute("SELECT state_json FROM sessions WHERE learner_id=? AND lesson_id=? AND teacher_id IS ? ORDER BY created_at DESC LIMIT 10", (learner_id, payload.lesson_id, teacher_id)).fetchall()
    prior_review_targets: list[str] = []
    for previous in previous_states:
        try:
            prior_state = json.loads(previous["state_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        for target in prior_state.get("review_targets", []):
            if isinstance(target, str) and target not in prior_review_targets:
                prior_review_targets.append(target)
    dialogue_state = initial_state(lesson, prior_review_targets)
    opening = lesson["scenarios"][dialogue_state["scenario_index"]]["prompt_ar"]
    transcript = [{"role": "ai", "text": opening}]
    with db() as con:
        con.execute(
            "INSERT INTO sessions(id, lesson_id, persona, transcript, state_json, learner_id, student_id, class_id, teacher_id, assignment_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, payload.lesson_id, payload.persona,
             json.dumps(transcript, ensure_ascii=False),
             json.dumps(dialogue_state, ensure_ascii=False), learner_id, student_id, class_id, teacher_id, payload.assignment_id if student_id else None),
        )
    return {
        "session_id": session_id,
        "learner_id": learner_id,
        "persona": payload.persona,
        "lesson": lesson["title_ar"],
        "reply": opening,
        "stage": dialogue_state["stage"],
        "adaptation": adaptation_summary(dialogue_state.get("adaptation_target"), lesson),
        "mode": public_status()["mode"],
    }


def make_demo_reply(student_text: str, count: int, lesson_title: str, stage: str) -> str:
    """Transparent dialogue scaffold; never presented as generated AI."""
    if stage == "reflect":
        return "قبل ما نقفل، ممكن تلخصلي أهم فكرة في الدرس وتقول إيه اللي بقى أوضح ليك؟"
    if stage == "transfer":
        return f"حلو! ممكن نطبّق اللي شرحته على مثال جديد من حياتنا اليومية في {lesson_title}؟"
    if len(student_text.strip()) < 8:
        return "ممكن تشرحلي أكتر؟ إيه أول خطوة فكرت فيها؟"
    if stage == "clarify":
        return "ممكن توريني مثال صغير أو تشرح ليه اخترت الطريقة دي؟"
    return "خليني أتأكد إني فهمت: ممكن تشرح الفكرة خطوة خطوة بمثال؟"


@app.post("/api/message")
async def send_message(payload: MessageRequest, request: Request) -> dict[str, Any]:
    with db() as con:
        row = con.execute("SELECT * FROM sessions WHERE id=?", (payload.session_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Session not found")
    user = getattr(request.state, "user", None)
    if row["student_id"] and (not user or user.get("id") != row["student_id"]):
        raise HTTPException(404, "Session not found")
    if row["teacher_id"] and (not user or user.get("id") != row["teacher_id"] and user.get("id") != row["student_id"]):
        raise HTTPException(404, "Session not found")
    if not row["teacher_id"] and not row["student_id"] and user:
        raise HTTPException(404, "Session not found")

    transcript = json.loads(row["transcript"])
    transcript.append({"role": "student", "text": payload.text})
    lesson = get_lesson(row["lesson_id"])
    student_count = sum(1 for item in transcript if item["role"] == "student")
    dialogue_state = advance_state(json.loads(row["state_json"] or "{}"), payload.text, lesson)
    context = state_context(dialogue_state, lesson)

    status = public_status()
    if status["mode"] == "live_ai":
        try:
            reply = await generate_reply(transcript, lesson, row["persona"], context)
        except Exception as exc:
            # Do not silently fall back: that would misrepresent demo text as AI.
            raise HTTPException(
                status_code=503,
                detail=f"Live AI is unavailable ({type(exc).__name__}). Check the local model server and settings.",
            ) from exc
        mode = "live_ai"
    else:
        reply = make_demo_reply(payload.text, student_count, lesson['title_ar'], dialogue_state["stage"])
        mode = "demo_fallback"

    transcript.append({"role": "ai", "text": reply})
    with db() as con:
        con.execute(
            "UPDATE sessions SET transcript=?, state_json=? WHERE id=?",
            (json.dumps(transcript, ensure_ascii=False),
             json.dumps(dialogue_state, ensure_ascii=False), payload.session_id),
        )
    return {"reply": reply, "mode": mode, "stage": dialogue_state["stage"], "turn": dialogue_state["turns"]}


@app.post("/api/finish")
def finish_session(payload: FinishRequest, request: Request) -> dict[str, Any]:
    with db() as con:
        row = con.execute("SELECT * FROM sessions WHERE id=?", (payload.session_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Session not found")
    user = getattr(request.state, "user", None)
    if row["student_id"] and (not user or user.get("id") != row["student_id"]):
        raise HTTPException(404, "Session not found")
    if row["teacher_id"] and (not user or user.get("id") != row["teacher_id"] and user.get("id") != row["student_id"]):
        raise HTTPException(404, "Session not found")
    if not row["teacher_id"] and not row["student_id"] and user:
        raise HTTPException(404, "Session not found")
    transcript = json.loads(row["transcript"])
    lesson = get_lesson(row["lesson_id"])
    if row["student_id"] and row["assignment_id"] and any(item.get("role") == "student" for item in transcript):
        with db() as con:
            con.execute("INSERT OR IGNORE INTO assignment_submissions(assignment_id,student_id,session_id) VALUES(?,?,?)",
                        (row["assignment_id"], row["student_id"], row["id"]))
    return {
        "transcript": transcript,
        "report": assess_explanation(transcript, lesson),
        "dialogue_state": json.loads(row["state_json"] or "{}"),
        "lesson": lesson["title_ar"],
        "mode": public_status()["mode"],
    }
