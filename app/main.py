from __future__ import annotations

import json
import sqlite3
import hashlib
import secrets
import io
import uuid
import time
from pathlib import Path
from datetime import date
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, Response, Depends
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.auth import hash_password, verify_password, new_session_token, token_digest, new_join_code
from app.assessment import assess_explanation
from app.intervention_planner import build_intervention_plan
from app.adaptive import adaptation_summary
from app.curriculum import get_lesson
from app.llm import generate_reply, public_status, generate_formative_quiz, generate_learning_feedback, generate_teacher_review_suggestions
from app.learning_journey import build_learning_journey
from app.pedagogy import advance_state, initial_state, state_context
from app.teacher_intelligence import build_review_priorities
from app.learning_engine import build_study_plan, get_quiz_questions, grade_quiz, validate_question_set

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "pupil_zero.db"
app = FastAPI(title="PUPIL ZERO", version="2.2.0", description="Local-first learning-by-teaching MVP")
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

class ParentRegisterRequest(BaseModel):
    invite_token: str = Field(min_length=30, max_length=200)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(min_length=2, max_length=80)

class SchoolAdminRegisterRequest(BaseModel):
    school_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(min_length=2, max_length=80)

class SchoolTeacherLinkRequest(BaseModel):
    teacher_email: str = Field(min_length=5, max_length=254)

class SchoolTeacherInviteRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)

class SchoolNameRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)

class SchoolSubjectRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    department_id: str | None = None

class SchoolClassGradeRequest(BaseModel):
    class_id: str = Field(min_length=1, max_length=64)
    grade_level_id: str = Field(min_length=1, max_length=64)

class SchoolTeachingAssignmentRequest(BaseModel):
    class_id: str = Field(min_length=1, max_length=64)
    subject_id: str = Field(min_length=1, max_length=64)
    teacher_id: str = Field(min_length=1, max_length=64)

class SchoolTimetableRequest(BaseModel):
    teaching_assignment_id: str = Field(min_length=1, max_length=64)
    day_of_week: int = Field(ge=0, le=6)
    start_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")

class SchoolAttendanceRequest(BaseModel):
    class_id: str = Field(min_length=1, max_length=64)
    student_id: str = Field(min_length=1, max_length=64)
    attendance_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    status: str = Field(pattern=r"^(present|absent|late|excused)$")

class QuizStartRequest(BaseModel):
    lesson_id: str = Field(min_length=1, max_length=64)


class QuizSubmitRequest(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)


class SchoolLessonRecordRequest(BaseModel):
    timetable_id: str = Field(min_length=1, max_length=64)
    lesson_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    status: str = Field(pattern=r"^(completed|cancelled|missed)$")
    topic: str = Field(default="", max_length=160)
    notes: str = Field(default="", max_length=1000)

class InvitedTeacherRegisterRequest(BaseModel):
    invite_token: str = Field(min_length=30, max_length=200)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(min_length=2, max_length=80)


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
        con.execute("""CREATE TABLE IF NOT EXISTS parent_accounts (
            id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
            password_salt TEXT NOT NULL, password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS schools (
            id TEXT PRIMARY KEY, name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS school_admin_accounts (
            id TEXT PRIMARY KEY, school_id TEXT NOT NULL UNIQUE REFERENCES schools(id),
            email TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
            password_salt TEXT NOT NULL, password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS school_teachers (
            school_id TEXT NOT NULL REFERENCES schools(id),
            teacher_id TEXT NOT NULL REFERENCES users(id),
            linked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(school_id, teacher_id)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS school_classes (
            school_id TEXT NOT NULL REFERENCES schools(id),
            class_id TEXT NOT NULL REFERENCES classes(id),
            PRIMARY KEY(school_id, class_id)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS school_departments (
            id TEXT PRIMARY KEY, school_id TEXT NOT NULL REFERENCES schools(id),
            name TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(school_id, name)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS school_grade_levels (
            id TEXT PRIMARY KEY, school_id TEXT NOT NULL REFERENCES schools(id),
            name TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(school_id, name)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS school_subjects (
            id TEXT PRIMARY KEY, school_id TEXT NOT NULL REFERENCES schools(id),
            department_id TEXT REFERENCES school_departments(id),
            name TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(school_id, name)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS school_class_grades (
            school_id TEXT NOT NULL REFERENCES schools(id),
            class_id TEXT NOT NULL REFERENCES classes(id),
            grade_level_id TEXT NOT NULL REFERENCES school_grade_levels(id),
            assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(school_id, class_id)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS school_teaching_assignments (
            id TEXT PRIMARY KEY, school_id TEXT NOT NULL REFERENCES schools(id),
            class_id TEXT NOT NULL REFERENCES classes(id),
            subject_id TEXT NOT NULL REFERENCES school_subjects(id),
            teacher_id TEXT NOT NULL REFERENCES users(id),
            assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(school_id, class_id, subject_id)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS school_timetable (
            id TEXT PRIMARY KEY, school_id TEXT NOT NULL REFERENCES schools(id),
            teaching_assignment_id TEXT NOT NULL REFERENCES school_teaching_assignments(id),
            day_of_week INTEGER NOT NULL CHECK(day_of_week BETWEEN 0 AND 6),
            start_time TEXT NOT NULL, end_time TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK(start_time < end_time)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS school_attendance (
            school_id TEXT NOT NULL REFERENCES schools(id),
            class_id TEXT NOT NULL REFERENCES classes(id),
            student_id TEXT NOT NULL REFERENCES users(id),
            attendance_date TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('present','absent','late','excused')),
            marked_by TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(school_id,class_id,student_id,attendance_date)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS school_lesson_records (
            id TEXT PRIMARY KEY, school_id TEXT NOT NULL REFERENCES schools(id),
            timetable_id TEXT NOT NULL REFERENCES school_timetable(id),
            lesson_date TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('completed','cancelled','missed')),
            topic TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
            recorded_by TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(school_id,timetable_id,lesson_date)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS user_notifications (
            id TEXT PRIMARY KEY, recipient_id TEXT NOT NULL, recipient_role TEXT NOT NULL,
            kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
            read_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_user_notifications_recipient ON user_notifications(recipient_role,recipient_id,created_at)")
        con.execute("""CREATE TABLE IF NOT EXISTS student_quizzes (
            id TEXT PRIMARY KEY, student_id TEXT NOT NULL REFERENCES users(id),
            lesson_id TEXT NOT NULL, questions_json TEXT NOT NULL,
            submitted_at TEXT, result_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_student_quizzes_student ON student_quizzes(student_id,created_at)")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_school_teachers_single_school ON school_teachers(teacher_id)")
        con.execute("""CREATE TABLE IF NOT EXISTS school_teacher_invites (
            token_hash TEXT PRIMARY KEY, school_id TEXT NOT NULL REFERENCES schools(id),
            email TEXT NOT NULL, expires_at INTEGER NOT NULL, used_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS guardian_invites (
            token_hash TEXT PRIMARY KEY, student_id TEXT NOT NULL, class_id TEXT NOT NULL,
            teacher_id TEXT NOT NULL, expires_at INTEGER NOT NULL, used_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS parent_student_links (
            parent_id TEXT NOT NULL, student_id TEXT NOT NULL, class_id TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(parent_id,student_id,class_id)
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
                "SELECT id,email,display_name,role FROM (SELECT u.id,u.email,u.display_name,u.role,s.token_hash,s.expires_at FROM auth_sessions s JOIN users u ON u.id=s.user_id UNION ALL SELECT p.id,p.email,p.display_name,'parent' AS role,s.token_hash,s.expires_at FROM auth_sessions s JOIN parent_accounts p ON p.id=s.user_id UNION ALL SELECT a.id,a.email,a.display_name,'school_admin' AS role,s.token_hash,s.expires_at FROM auth_sessions s JOIN school_admin_accounts a ON a.id=s.user_id) WHERE token_hash=? AND expires_at>?",
                (token_digest(token), int(time.time())),
            ).fetchone()
    request.state.user = dict(user) if user else None
    path = request.url.path
    if path == "/student" or path.startswith("/api/student"):
        if not user or user["role"] != "student":
            if path == "/student":
                return HTMLResponse((ROOT / "static" / "student.html").read_text(encoding="utf-8"))
            return JSONResponse({"detail": "Student authentication required"}, status_code=401)
    if path == "/teacher" or path.startswith("/api/teacher"):
        if not user or user["role"] != "teacher":
            if path == "/teacher":
                return HTMLResponse("<!doctype html><html lang=ar dir=rtl><meta charset=utf-8><body><h1>تسجيل دخول المدرّس مطلوب</h1><p><a href=/account>افتح صفحة الحسابات لتسجيل الدخول</a></p></body></html>", status_code=401)
            return JSONResponse({"detail": "Teacher authentication required"}, status_code=401)
    if path == "/parent" or path.startswith("/api/parent"):
        if not user or user["role"] != "parent":
            if path == "/parent":
                return HTMLResponse((ROOT / "static" / "parent.html").read_text(encoding="utf-8"))
            return JSONResponse({"detail": "Parent authentication required"}, status_code=401)
    if path == "/school-admin" or path.startswith("/api/school-admin"):
        if not user or user["role"] != "school_admin":
            if path == "/school-admin":
                return HTMLResponse((ROOT / "static" / "school_admin.html").read_text(encoding="utf-8"))
            return JSONResponse({"detail": "School administrator authentication required"}, status_code=401)
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
    with db() as con:
        email = payload.email.strip().lower()
        user=con.execute("SELECT id,email,display_name,role,password_salt,password_hash FROM users WHERE email=? UNION ALL SELECT id,email,display_name,'parent' AS role,password_salt,password_hash FROM parent_accounts WHERE email=? UNION ALL SELECT id,email,display_name,'school_admin' AS role,password_salt,password_hash FROM school_admin_accounts WHERE email=?",(email,email,email)).fetchone()
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
            "SELECT id,email,display_name,role FROM (SELECT u.id,u.email,u.display_name,u.role,s.token_hash,s.expires_at FROM auth_sessions s JOIN users u ON u.id=s.user_id UNION ALL SELECT p.id,p.email,p.display_name,'parent' AS role,s.token_hash,s.expires_at FROM auth_sessions s JOIN parent_accounts p ON p.id=s.user_id UNION ALL SELECT a.id,a.email,a.display_name,'school_admin' AS role,s.token_hash,s.expires_at FROM auth_sessions s JOIN school_admin_accounts a ON a.id=s.user_id) WHERE token_hash=? AND expires_at>?",
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
        for link in con.execute("SELECT school_id FROM school_teachers WHERE teacher_id=?", (teacher["id"],)).fetchall():
            con.execute("INSERT OR IGNORE INTO school_classes(school_id,class_id) VALUES(?,?)", (link["school_id"], class_id))
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
    with db() as con:
        members = con.execute("SELECT student_id FROM class_members WHERE class_id=?", (payload.class_id,)).fetchall()
        for member in members:
            con.execute("""INSERT INTO user_notifications(id,recipient_id,recipient_role,kind,title,body)
                VALUES(?,?,'student','assignment','New assignment',?)""",
                (str(uuid.uuid4()), member["student_id"], payload.title.strip()))
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


@app.get("/api/student/study-plan/{lesson_id}")
def student_study_plan(lesson_id: str, student: dict[str, Any] = Depends(current_student)) -> dict[str, Any]:
    lesson = get_lesson(lesson_id)
    if not lesson:
        raise HTTPException(404, "Lesson not found")
    with db() as con:
        rows = con.execute("""SELECT transcript,created_at FROM sessions
            WHERE student_id=? AND lesson_id=? ORDER BY created_at DESC LIMIT 20""",
            (student["id"], lesson_id)).fetchall()
    reports = []
    for row in rows:
        try:
            transcript = json.loads(row["transcript"] or "[]")
            reports.append({"report": assess_explanation(transcript, lesson), "created_at": row["created_at"]})
        except (TypeError, json.JSONDecodeError):
            continue
    return build_study_plan(lesson, reports)


@app.post("/api/student/quizzes", status_code=201)
async def create_student_quiz(payload: QuizStartRequest,
                              student: dict[str, Any] = Depends(current_student)) -> dict[str, Any]:
    lesson = get_lesson(payload.lesson_id)
    if not lesson:
        raise HTTPException(404, "Lesson not found")
    status = public_status()
    if status.get("configured"):
        try:
            questions = validate_question_set(await generate_formative_quiz(lesson, count=3), lesson)
        except Exception as exc:
            raise HTTPException(503, "Local AI quiz generation failed. Check the configured model and try again.") from exc
        source = "local_ai"
        generation_notice = "تم توليد الأسئلة بواسطة النموذج المحلي، ويجب مراجعتها من المعلم قبل استخدامها رسميًا."
    else:
        questions = get_quiz_questions(payload.lesson_id)
        source = "authored_bank"
        generation_notice = "النموذج المحلي غير مفعّل؛ هذه أسئلة تدريبية مكتوبة مسبقًا وليست مولّدة بالذكاء الاصطناعي."
    if not questions:
        raise HTTPException(404, "No formative questions are available for this lesson")
    quiz_id = str(uuid.uuid4())
    with db() as con:
        con.execute("INSERT INTO student_quizzes(id,student_id,lesson_id,questions_json) VALUES(?,?,?,?)",
                    (quiz_id, student["id"], payload.lesson_id, json.dumps(questions, ensure_ascii=False)))
    public_questions = [{k: v for k, v in question.items() if k not in ("correct_option", "explanation")}
                        for question in questions]
    return {"quiz_id": quiz_id, "lesson_id": payload.lesson_id, "lesson": lesson["title_ar"],
            "questions": public_questions, "source": source, "generation_notice": generation_notice,
            "notice": "اختبار تدريبي قصير، وليس امتحانًا رسميًا أو درجة مدرسية."}


@app.post("/api/student/quizzes/{quiz_id}/submit")
async def submit_student_quiz(quiz_id: str, payload: QuizSubmitRequest,
                              student: dict[str, Any] = Depends(current_student)) -> dict[str, Any]:
    with db() as con:
        row = con.execute("SELECT * FROM student_quizzes WHERE id=? AND student_id=?",
                          (quiz_id, student["id"])).fetchone()
        if not row:
            raise HTTPException(404, "Quiz not found")
        if row["submitted_at"]:
            raise HTTPException(409, "This quiz has already been submitted")
        questions = json.loads(row["questions_json"])
        allowed = {q["id"] for q in questions}
        if set(payload.answers) - allowed:
            raise HTTPException(422, "Answers contain an unknown question id")
        result = grade_quiz(questions, payload.answers)
        lesson = get_lesson(row["lesson_id"])
        concept_map = {item["id"]: item for item in (lesson or {}).get("concepts", [])}
        option_maps = {q["id"]: {o["id"]: o["text"] for o in q.get("options", [])} for q in questions}
        incorrect_items = []
        for question, detail in zip(questions, result["details"]):
            if detail["correct"]:
                continue
            concept = concept_map.get(question["concept_id"], {})
            incorrect_items.append({
                "question_id": question["id"], "concept_id": question["concept_id"],
                "question": question["prompt"],
                "selected_answer": option_maps[question["id"]].get(detail["selected_option"], "لم يتم اختيار إجابة"),
                "correct_answer": option_maps[question["id"]].get(question["correct_option"], ""),
                "authored_explanation": question["explanation"],
                "concept_explanation": concept.get("correction", ""),
            })
        feedback_source = "authored_guidance"
        for detail in result["details"]:
            if not detail["correct"]:
                concept = concept_map.get(detail["concept_id"], {})
                detail["learning_feedback"] = {
                    "feedback": "خلّينا نبص على الفكرة من زاوية تانية.",
                    "alternative_explanation": concept.get("correction") or detail["explanation"],
                    "practice_prompt": "جرّب تشرح الفكرة بمثال جديد من عندك.",
                }
        if incorrect_items and public_status().get("configured"):
            try:
                generated = await generate_learning_feedback(lesson, incorrect_items)
                generated_by_id = {item["question_id"]: item for item in generated}
                for detail in result["details"]:
                    if not detail["correct"] and detail["question_id"] in generated_by_id:
                        detail["learning_feedback"] = {k:v for k,v in generated_by_id[detail["question_id"]].items() if k!="question_id"}
                feedback_source = "local_ai"
            except Exception:
                # Safe authored explanation remains available if the local model is offline.
                feedback_source = "authored_guidance_fallback"
        result["feedback_source"] = feedback_source
        result["notice"] += " الشرح الإضافي اقتراح تعليمي آلي أو مكتوب مسبقًا ويحتاج مراجعة المعلم."
        result_json = json.dumps(result, ensure_ascii=False)
        updated = con.execute("UPDATE student_quizzes SET submitted_at=CURRENT_TIMESTAMP,result_json=? WHERE id=? AND student_id=? AND submitted_at IS NULL",
                              (result_json, quiz_id, student["id"]))
        if updated.rowcount != 1:
            raise HTTPException(409, "This quiz has already been submitted")
    return result


@app.get("/api/student/quizzes/history")
def student_quiz_history(student: dict[str, Any] = Depends(current_student)) -> dict[str, Any]:
    with db() as con:
        rows = con.execute("""SELECT id,lesson_id,submitted_at,result_json,created_at
            FROM student_quizzes WHERE student_id=? AND submitted_at IS NOT NULL
            ORDER BY submitted_at DESC LIMIT 30""", (student["id"],)).fetchall()
    history = []
    for row in rows:
        try:
            result = json.loads(row["result_json"] or "{}")
        except json.JSONDecodeError:
            result = {}
        history.append({"quiz_id": row["id"], "lesson_id": row["lesson_id"],
                        "submitted_at": row["submitted_at"], "score": result.get("score"),
                        "total": result.get("total")})
    return {"history": history, "notice": "نتائج تدريبية للمراجعة الذاتية وليست درجات مدرسية."}


def current_parent(request: Request) -> dict[str, Any]:
    user = getattr(request.state, "user", None)
    if not user or user.get("role") != "parent":
        raise HTTPException(401, "Parent authentication required")
    return user


@app.get("/api/student/dashboard")
def student_dashboard(student: dict[str, Any] = Depends(current_student)) -> dict[str, Any]:
    today = date.today().isoformat()
    with db() as con:
        timetable = con.execute("""SELECT t.id,t.day_of_week,t.start_time,t.end_time,c.id AS class_id,c.name AS class_name,
            s.name AS subject_name,u.display_name AS teacher_name
            FROM class_members m JOIN school_classes sc ON sc.class_id=m.class_id
            JOIN school_timetable t ON t.school_id=sc.school_id
            JOIN school_teaching_assignments a ON a.id=t.teaching_assignment_id AND a.class_id=m.class_id
            JOIN classes c ON c.id=a.class_id JOIN school_subjects s ON s.id=a.subject_id
            JOIN users u ON u.id=a.teacher_id WHERE m.student_id=? ORDER BY t.day_of_week,t.start_time""",
            (student["id"],)).fetchall()
        attendance = con.execute("""SELECT attendance_date,status,c.name AS class_name
            FROM school_attendance sa JOIN classes c ON c.id=sa.class_id
            WHERE sa.student_id=? ORDER BY attendance_date DESC LIMIT 20""", (student["id"],)).fetchall()
        notifications = con.execute("""SELECT id,kind,title,body,read_at,created_at FROM user_notifications
            WHERE recipient_id=? AND recipient_role='student' ORDER BY created_at DESC LIMIT 30""", (student["id"],)).fetchall()
    assignments = student_assignments(None, student)["assignments"]
    return {"today": today, "timetable": [dict(x) for x in timetable],
            "assignments": assignments, "attendance": [dict(x) for x in attendance],
            "notifications": [dict(x) for x in notifications]}


@app.get("/api/teacher/operations")
def teacher_operations(teacher: dict[str, Any] = Depends(current_teacher)) -> dict[str, Any]:
    with db() as con:
        timetable = con.execute("""SELECT t.id,t.day_of_week,t.start_time,t.end_time,a.class_id,c.name AS class_name,
            a.subject_id,s.name AS subject_name,u.display_name AS teacher_name
            FROM school_timetable t JOIN school_teaching_assignments a ON a.id=t.teaching_assignment_id
            JOIN school_teachers st ON st.school_id=t.school_id AND st.teacher_id=a.teacher_id
            JOIN classes c ON c.id=a.class_id JOIN school_subjects s ON s.id=a.subject_id
            JOIN users u ON u.id=a.teacher_id WHERE a.teacher_id=? ORDER BY t.day_of_week,t.start_time""",
            (teacher["id"],)).fetchall()
        classes = con.execute("""SELECT DISTINCT c.id,c.name FROM school_teaching_assignments a
            JOIN school_teachers st ON st.school_id=a.school_id AND st.teacher_id=a.teacher_id
            JOIN school_classes sc ON sc.school_id=a.school_id AND sc.class_id=a.class_id
            JOIN classes c ON c.id=a.class_id WHERE a.teacher_id=? ORDER BY c.name""",
            (teacher["id"],)).fetchall()
    return {"timetable": [dict(x) for x in timetable], "classes": [dict(x) for x in classes]}


@app.post("/api/teacher/attendance", status_code=201)
def teacher_mark_attendance(payload: SchoolAttendanceRequest,
                            teacher: dict[str, Any] = Depends(current_teacher)) -> dict[str, Any]:
    try:
        date.fromisoformat(payload.attendance_date)
    except ValueError as exc:
        raise HTTPException(422, "Invalid attendance date") from exc
    with db() as con:
        assignment = con.execute("""SELECT a.school_id FROM school_teaching_assignments a
            JOIN school_teachers st ON st.school_id=a.school_id AND st.teacher_id=a.teacher_id
            JOIN school_classes sc ON sc.school_id=a.school_id AND sc.class_id=a.class_id
            WHERE a.class_id=? AND a.teacher_id=? LIMIT 1""", (payload.class_id, teacher["id"])).fetchone()
        if not assignment:
            raise HTTPException(404, "Class is not assigned to this teacher in a linked school")
        if not con.execute("SELECT 1 FROM class_members WHERE class_id=? AND student_id=?",
                           (payload.class_id, payload.student_id)).fetchone():
            raise HTTPException(404, "Student is not enrolled in this class")
        sid = assignment["school_id"]
        con.execute("""INSERT INTO school_attendance(school_id,class_id,student_id,attendance_date,status,marked_by)
            VALUES(?,?,?,?,?,?) ON CONFLICT(school_id,class_id,student_id,attendance_date)
            DO UPDATE SET status=excluded.status,marked_by=excluded.marked_by,updated_at=CURRENT_TIMESTAMP""",
            (sid,payload.class_id,payload.student_id,payload.attendance_date,payload.status,teacher["id"]))
        recipients = con.execute("SELECT parent_id FROM parent_student_links WHERE student_id=? AND class_id=?",
                                 (payload.student_id,payload.class_id)).fetchall()
        con.execute("""INSERT INTO user_notifications(id,recipient_id,recipient_role,kind,title,body)
            VALUES(?,?,'student','attendance','Attendance updated',?)""",
            (str(uuid.uuid4()),payload.student_id,payload.status))
        for recipient in recipients:
            con.execute("""INSERT INTO user_notifications(id,recipient_id,recipient_role,kind,title,body)
                VALUES(?,?,'parent','attendance','Student attendance updated',?)""",
                (str(uuid.uuid4()),recipient["parent_id"],payload.status))
    return {"saved": True, "class_id": payload.class_id, "student_id": payload.student_id,
            "attendance_date": payload.attendance_date, "status": payload.status}


@app.get("/api/student/notifications")
def student_notifications(student: dict[str, Any] = Depends(current_student)) -> dict[str, Any]:
    with db() as con:
        rows=con.execute("SELECT id,kind,title,body,read_at,created_at FROM user_notifications WHERE recipient_id=? AND recipient_role='student' ORDER BY created_at DESC LIMIT 50",(student["id"],)).fetchall()
    return {"notifications":[dict(x) for x in rows]}


@app.get("/api/teacher/notifications")
def teacher_notifications(teacher: dict[str, Any] = Depends(current_teacher)) -> dict[str, Any]:
    with db() as con:
        rows=con.execute("SELECT id,kind,title,body,read_at,created_at FROM user_notifications WHERE recipient_id=? AND recipient_role='teacher' ORDER BY created_at DESC LIMIT 50",(teacher["id"],)).fetchall()
    return {"notifications":[dict(x) for x in rows]}


@app.get("/api/parent/students/{student_id}/school-summary")
def parent_student_school_summary(student_id: str, class_id: str = Query(...),
                                  parent: dict[str, Any] = Depends(current_parent)) -> dict[str, Any]:
    with db() as con:
        link=con.execute("SELECT 1 FROM parent_student_links WHERE parent_id=? AND student_id=? AND class_id=?",
                         (parent["id"],student_id,class_id)).fetchone()
        if not link: raise HTTPException(404,"Linked student report not found")
        attendance=con.execute("""SELECT attendance_date,status FROM school_attendance
            WHERE student_id=? AND class_id=? ORDER BY attendance_date DESC LIMIT 30""",(student_id,class_id)).fetchall()
        timetable=con.execute("""SELECT t.day_of_week,t.start_time,t.end_time,s.name AS subject_name
            FROM school_timetable t JOIN school_teaching_assignments a ON a.id=t.teaching_assignment_id
            JOIN school_classes sc ON sc.school_id=t.school_id AND sc.class_id=a.class_id
            JOIN school_subjects s ON s.id=a.subject_id WHERE a.class_id=? ORDER BY t.day_of_week,t.start_time""",
            (class_id,)).fetchall()
        notifications=con.execute("""SELECT id,title,body,read_at,created_at FROM user_notifications
            WHERE recipient_id=? AND recipient_role='parent' ORDER BY created_at DESC LIMIT 20""",(parent["id"],)).fetchall()
    return {"attendance":[dict(x) for x in attendance],"timetable":[dict(x) for x in timetable],
            "notifications":[dict(x) for x in notifications]}


@app.post("/api/notifications/{notification_id}/read")
def mark_notification_read(notification_id: str, request: Request) -> dict[str, Any]:
    user=getattr(request.state,"user",None)
    if not user: raise HTTPException(401,"Authentication required")
    role=user["role"]
    if role not in ("student","teacher","parent"): raise HTTPException(403,"Notifications unavailable for this role")
    with db() as con:
        cur=con.execute("""UPDATE user_notifications SET read_at=CURRENT_TIMESTAMP
            WHERE id=? AND recipient_id=? AND recipient_role=?""",(notification_id,user["id"],role))
        if cur.rowcount==0: raise HTTPException(404,"Notification not found")
    return {"read":True}


def current_school_admin(request: Request) -> dict[str, Any]:
    user = getattr(request.state, "user", None)
    if not user or user.get("role") != "school_admin":
        raise HTTPException(401, "School administrator authentication required")
    return user


@app.post("/api/auth/register-school-admin", status_code=201)
def register_school_admin(payload: SchoolAdminRegisterRequest, response: Response) -> dict[str, Any]:
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "Enter a valid email address")
    school_id, admin_id, token = str(uuid.uuid4()), str(uuid.uuid4()), new_session_token()
    salt, digest = hash_password(payload.password)
    with db() as con:
        try:
            con.execute("INSERT INTO schools(id,name) VALUES(?,?)", (school_id, payload.school_name.strip()))
            con.execute("INSERT INTO school_admin_accounts(id,school_id,email,display_name,password_salt,password_hash) VALUES(?,?,?,?,?,?)",
                        (admin_id, school_id, email, payload.display_name.strip(), salt, digest))
            con.execute("INSERT INTO auth_sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",
                        (token_digest(token), admin_id, int(time.time()) + 604800))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "An account with this email already exists") from exc
    response.set_cookie("pupil_session", token, httponly=True, samesite="strict", max_age=604800, path="/")
    return {"user": {"id": admin_id, "email": email, "display_name": payload.display_name.strip(), "role": "school_admin"},
            "school": {"id": school_id, "name": payload.school_name.strip()}}


@app.post("/api/school-admin/teacher-invites", status_code=201)
def create_school_teacher_invite(payload: SchoolTeacherInviteRequest, admin: dict[str, Any] = Depends(current_school_admin)) -> dict[str, Any]:
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "Enter a valid email address")
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with db() as con:
        school = con.execute("SELECT school_id FROM school_admin_accounts WHERE id=?", (admin["id"],)).fetchone()
        if con.execute("SELECT 1 FROM (SELECT email FROM users UNION ALL SELECT email FROM parent_accounts UNION ALL SELECT email FROM school_admin_accounts) WHERE email=?", (email,)).fetchone():
            raise HTTPException(409, "This email already has an account. Link the existing teacher instead.")
        con.execute("INSERT INTO school_teacher_invites(token_hash,school_id,email,expires_at) VALUES(?,?,?,?)",
                    (digest, school["school_id"], email, int(time.time()) + 7 * 86400))
    return {"invite_token": token, "email": email, "expires_in_days": 7,
            "registration_path": "/account?teacher_invite=" + token}


@app.post("/api/auth/register-invited-teacher", status_code=201)
def register_invited_teacher(payload: InvitedTeacherRegisterRequest, response: Response) -> dict[str, Any]:
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "Enter a valid email address")
    digest = hashlib.sha256(payload.invite_token.encode("utf-8")).hexdigest()
    salt, password_hash = hash_password(payload.password)
    teacher_id, session_token = str(uuid.uuid4()), new_session_token()
    with db() as con:
        invite = con.execute("SELECT school_id,email,expires_at,used_at FROM school_teacher_invites WHERE token_hash=?", (digest,)).fetchone()
        if not invite or invite["used_at"] or invite["expires_at"] <= int(time.time()) or invite["email"] != email:
            raise HTTPException(400, "Invitation is invalid, expired, already used, or belongs to another email")
        if con.execute("SELECT 1 FROM (SELECT email FROM users UNION ALL SELECT email FROM parent_accounts UNION ALL SELECT email FROM school_admin_accounts) WHERE email=?", (email,)).fetchone():
            raise HTTPException(409, "This email already has an account")
        try:
            con.execute("INSERT INTO users(id,email,display_name,role,password_salt,password_hash) VALUES(?,?,?,'teacher',?,?)",
                        (teacher_id, email, payload.display_name.strip(), salt, password_hash))
            con.execute("INSERT INTO school_teachers(school_id,teacher_id) VALUES(?,?)", (invite["school_id"], teacher_id))
            con.execute("UPDATE school_teacher_invites SET used_at=CURRENT_TIMESTAMP WHERE token_hash=? AND used_at IS NULL", (digest,))
            con.execute("INSERT INTO auth_sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",
                        (token_digest(session_token), teacher_id, int(time.time()) + 604800))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "This email is already registered or the teacher is linked elsewhere") from exc
    response.set_cookie("pupil_session", session_token, httponly=True, samesite="strict", max_age=604800, path="/")
    return {"user": {"id": teacher_id, "email": email, "display_name": payload.display_name.strip(), "role": "teacher"}}


@app.delete("/api/school-admin/teachers/{teacher_id}")
def unlink_school_teacher(teacher_id: str, admin: dict[str, Any] = Depends(current_school_admin)) -> dict[str, bool]:
    with db() as con:
        school = con.execute("SELECT school_id FROM school_admin_accounts WHERE id=?", (admin["id"],)).fetchone()
        linked = con.execute("SELECT 1 FROM school_teachers WHERE school_id=? AND teacher_id=?", (school["school_id"], teacher_id)).fetchone()
        if not linked:
            raise HTTPException(404, "Teacher not found in this school")
        con.execute("DELETE FROM school_classes WHERE school_id=? AND class_id IN (SELECT id FROM classes WHERE teacher_id=?)",
                    (school["school_id"], teacher_id))
        con.execute("DELETE FROM school_teachers WHERE school_id=? AND teacher_id=?", (school["school_id"], teacher_id))
    return {"unlinked": True}


@app.post("/api/school-admin/teachers", status_code=201)
def link_school_teacher(payload: SchoolTeacherLinkRequest, admin: dict[str, Any] = Depends(current_school_admin)) -> dict[str, Any]:
    email = payload.teacher_email.strip().lower()
    with db() as con:
        school = con.execute("SELECT school_id FROM school_admin_accounts WHERE id=?", (admin["id"],)).fetchone()
        teacher = con.execute("SELECT id,email,display_name FROM users WHERE email=? AND role='teacher'", (email,)).fetchone()
        if not teacher:
            raise HTTPException(404, "Teacher account not found. The teacher must register first.")
        try:
            con.execute("INSERT INTO school_teachers(school_id,teacher_id) VALUES(?,?)", (school["school_id"], teacher["id"]))
            con.execute("INSERT OR IGNORE INTO school_classes(school_id,class_id) SELECT ?,id FROM classes WHERE teacher_id=?",
                        (school["school_id"], teacher["id"]))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Teacher is already linked to a school workspace")
    return {"linked": True, "teacher": {"id": teacher["id"], "email": teacher["email"], "display_name": teacher["display_name"]}}


@app.get("/api/school-admin/overview")
def school_admin_overview(admin: dict[str, Any] = Depends(current_school_admin)) -> dict[str, Any]:
    with db() as con:
        school = con.execute("SELECT s.id,s.name FROM schools s JOIN school_admin_accounts a ON a.school_id=s.id WHERE a.id=?", (admin["id"],)).fetchone()
        teachers = con.execute("""SELECT u.id,u.display_name,u.email,COUNT(DISTINCT sc.class_id) AS class_count
            FROM school_teachers st JOIN users u ON u.id=st.teacher_id
            LEFT JOIN school_classes sc ON sc.school_id=st.school_id
            LEFT JOIN classes c ON c.id=sc.class_id AND c.teacher_id=u.id
            WHERE st.school_id=? GROUP BY u.id ORDER BY u.display_name""", (school["id"],)).fetchall()
        classes = con.execute("""SELECT c.id,c.name,c.grade_label,u.display_name AS teacher_name,
            COUNT(DISTINCT m.student_id) AS student_count, gl.name AS academic_grade
            FROM school_classes sc JOIN classes c ON c.id=sc.class_id
            JOIN users u ON u.id=c.teacher_id LEFT JOIN class_members m ON m.class_id=c.id
            LEFT JOIN school_class_grades cg ON cg.school_id=sc.school_id AND cg.class_id=c.id
            LEFT JOIN school_grade_levels gl ON gl.id=cg.grade_level_id
            WHERE sc.school_id=? GROUP BY c.id ORDER BY c.created_at DESC""", (school["id"],)).fetchall()
        departments = con.execute("SELECT id,name FROM school_departments WHERE school_id=? ORDER BY name", (school["id"],)).fetchall()
        grade_levels = con.execute("SELECT id,name,sort_order FROM school_grade_levels WHERE school_id=? ORDER BY sort_order,name", (school["id"],)).fetchall()
        subjects = con.execute("""SELECT s.id,s.name,s.department_id,d.name AS department_name
            FROM school_subjects s LEFT JOIN school_departments d ON d.id=s.department_id
            WHERE s.school_id=? ORDER BY s.name""", (school["id"],)).fetchall()
        teaching_assignments = con.execute("""SELECT a.id,a.class_id,a.subject_id,a.teacher_id,
            c.name AS class_name,s.name AS subject_name,u.display_name AS teacher_name
            FROM school_teaching_assignments a JOIN classes c ON c.id=a.class_id
            JOIN school_subjects s ON s.id=a.subject_id JOIN users u ON u.id=a.teacher_id
            WHERE a.school_id=? ORDER BY c.name,s.name""", (school["id"],)).fetchall()
        timetable = con.execute("""SELECT t.id,t.day_of_week,t.start_time,t.end_time,a.id AS teaching_assignment_id,
            a.class_id,a.subject_id,a.teacher_id,c.name AS class_name,s.name AS subject_name,u.display_name AS teacher_name
            FROM school_timetable t JOIN school_teaching_assignments a ON a.id=t.teaching_assignment_id
            JOIN classes c ON c.id=a.class_id JOIN school_subjects s ON s.id=a.subject_id
            JOIN users u ON u.id=a.teacher_id WHERE t.school_id=? ORDER BY t.day_of_week,t.start_time""",
            (school["id"],)).fetchall()
    return {"school": dict(school), "teacher_count": len(teachers), "class_count": len(classes),
            "student_enrollments": sum(row["student_count"] for row in classes),
            "teachers": [dict(row) for row in teachers], "classes": [dict(row) for row in classes],
            "departments": [dict(row) for row in departments], "grade_levels": [dict(row) for row in grade_levels],
            "subjects": [dict(row) for row in subjects], "teaching_assignments": [dict(row) for row in teaching_assignments],
            "timetable": [dict(row) for row in timetable],
            "notice": "Operational counts only; academic assignments are administrative records, not evidence of student mastery."}


@app.post("/api/school-admin/departments", status_code=201)
def school_admin_create_department(payload: SchoolNameRequest, admin: dict[str, Any] = Depends(current_school_admin)) -> dict[str, Any]:
    department_id = str(uuid.uuid4())
    with db() as con:
        school = con.execute("SELECT school_id FROM school_admin_accounts WHERE id=?", (admin["id"],)).fetchone()
        try:
            con.execute("INSERT INTO school_departments(id,school_id,name) VALUES(?,?,?)",
                        (department_id, school["school_id"], payload.name.strip()))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "A department with this name already exists") from exc
    return {"id": department_id, "name": payload.name.strip()}


@app.post("/api/school-admin/grade-levels", status_code=201)
def school_admin_create_grade_level(payload: SchoolNameRequest, sort_order: int = Query(0, ge=0, le=1000),
                                    admin: dict[str, Any] = Depends(current_school_admin)) -> dict[str, Any]:
    grade_id = str(uuid.uuid4())
    with db() as con:
        school = con.execute("SELECT school_id FROM school_admin_accounts WHERE id=?", (admin["id"],)).fetchone()
        try:
            con.execute("INSERT INTO school_grade_levels(id,school_id,name,sort_order) VALUES(?,?,?,?)",
                        (grade_id, school["school_id"], payload.name.strip(), sort_order))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "A grade level with this name already exists") from exc
    return {"id": grade_id, "name": payload.name.strip(), "sort_order": sort_order}


@app.post("/api/school-admin/subjects", status_code=201)
def school_admin_create_subject(payload: SchoolSubjectRequest, admin: dict[str, Any] = Depends(current_school_admin)) -> dict[str, Any]:
    subject_id = str(uuid.uuid4())
    with db() as con:
        school = con.execute("SELECT school_id FROM school_admin_accounts WHERE id=?", (admin["id"],)).fetchone()
        if payload.department_id and not con.execute(
            "SELECT 1 FROM school_departments WHERE id=? AND school_id=?",
            (payload.department_id, school["school_id"])
        ).fetchone():
            raise HTTPException(404, "Department not found in this school")
        try:
            con.execute("INSERT INTO school_subjects(id,school_id,department_id,name) VALUES(?,?,?,?)",
                        (subject_id, school["school_id"], payload.department_id, payload.name.strip()))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "A subject with this name already exists") from exc
    return {"id": subject_id, "name": payload.name.strip(), "department_id": payload.department_id}


@app.post("/api/school-admin/class-grades", status_code=201)
def school_admin_assign_class_grade(payload: SchoolClassGradeRequest,
                                    admin: dict[str, Any] = Depends(current_school_admin)) -> dict[str, Any]:
    with db() as con:
        school = con.execute("SELECT school_id FROM school_admin_accounts WHERE id=?", (admin["id"],)).fetchone()
        if not con.execute("SELECT 1 FROM school_classes WHERE school_id=? AND class_id=?",
                           (school["school_id"], payload.class_id)).fetchone():
            raise HTTPException(404, "Class not found in this school")
        if not con.execute("SELECT 1 FROM school_grade_levels WHERE school_id=? AND id=?",
                           (school["school_id"], payload.grade_level_id)).fetchone():
            raise HTTPException(404, "Grade level not found in this school")
        con.execute("""INSERT INTO school_class_grades(school_id,class_id,grade_level_id) VALUES(?,?,?)
            ON CONFLICT(school_id,class_id) DO UPDATE SET grade_level_id=excluded.grade_level_id,assigned_at=CURRENT_TIMESTAMP""",
                    (school["school_id"], payload.class_id, payload.grade_level_id))
    return {"assigned": True, "class_id": payload.class_id, "grade_level_id": payload.grade_level_id}


@app.post("/api/school-admin/teaching-assignments", status_code=201)
def school_admin_assign_subject_teacher(payload: SchoolTeachingAssignmentRequest,
                                        admin: dict[str, Any] = Depends(current_school_admin)) -> dict[str, Any]:
    assignment_id = str(uuid.uuid4())
    with db() as con:
        school = con.execute("SELECT school_id FROM school_admin_accounts WHERE id=?", (admin["id"],)).fetchone()
        sid = school["school_id"]
        if not con.execute("SELECT 1 FROM school_classes WHERE school_id=? AND class_id=?", (sid, payload.class_id)).fetchone():
            raise HTTPException(404, "Class not found in this school")
        if not con.execute("SELECT 1 FROM school_subjects WHERE school_id=? AND id=?", (sid, payload.subject_id)).fetchone():
            raise HTTPException(404, "Subject not found in this school")
        if not con.execute("SELECT 1 FROM school_teachers WHERE school_id=? AND teacher_id=?", (sid, payload.teacher_id)).fetchone():
            raise HTTPException(404, "Teacher is not linked to this school")
        con.execute("""INSERT INTO school_teaching_assignments(id,school_id,class_id,subject_id,teacher_id)
            VALUES(?,?,?,?,?) ON CONFLICT(school_id,class_id,subject_id) DO UPDATE SET
            teacher_id=excluded.teacher_id,assigned_at=CURRENT_TIMESTAMP""",
                    (assignment_id, sid, payload.class_id, payload.subject_id, payload.teacher_id))
        row = con.execute("""SELECT a.id,c.name AS class_name,s.name AS subject_name,u.display_name AS teacher_name
            FROM school_teaching_assignments a JOIN classes c ON c.id=a.class_id
            JOIN school_subjects s ON s.id=a.subject_id JOIN users u ON u.id=a.teacher_id
            WHERE a.school_id=? AND a.class_id=? AND a.subject_id=?""",
                          (sid, payload.class_id, payload.subject_id)).fetchone()
    return {"assignment": dict(row)}


@app.post("/api/school-admin/timetable", status_code=201)
def school_admin_create_timetable(payload: SchoolTimetableRequest,
                                  admin: dict[str, Any] = Depends(current_school_admin)) -> dict[str, Any]:
    if payload.start_time >= payload.end_time:
        raise HTTPException(422, "End time must be later than start time")
    slot_id = str(uuid.uuid4())
    with db() as con:
        school = con.execute("SELECT school_id FROM school_admin_accounts WHERE id=?", (admin["id"],)).fetchone()
        assignment = con.execute("SELECT id,class_id,teacher_id FROM school_teaching_assignments WHERE id=? AND school_id=?",
                                 (payload.teaching_assignment_id, school["school_id"])).fetchone()
        if not assignment:
            raise HTTPException(404, "Teaching assignment not found in this school")
        conflict = con.execute("""SELECT t.id FROM school_timetable t
            JOIN school_teaching_assignments a ON a.id=t.teaching_assignment_id
            WHERE t.school_id=? AND t.day_of_week=? AND t.start_time < ? AND t.end_time > ?
            AND (a.teacher_id=? OR a.class_id=?) LIMIT 1""",
            (school["school_id"], payload.day_of_week, payload.end_time, payload.start_time,
             assignment["teacher_id"], assignment["class_id"])).fetchone()
        if conflict:
            raise HTTPException(409, "Timetable conflict: this teacher or class already has a lesson in that time range")
        con.execute("INSERT INTO school_timetable(id,school_id,teaching_assignment_id,day_of_week,start_time,end_time) VALUES(?,?,?,?,?,?)",
                    (slot_id, school["school_id"], assignment["id"], payload.day_of_week, payload.start_time, payload.end_time))
        row = con.execute("""SELECT t.id,t.day_of_week,t.start_time,t.end_time,c.name AS class_name,
            s.name AS subject_name,u.display_name AS teacher_name
            FROM school_timetable t JOIN school_teaching_assignments a ON a.id=t.teaching_assignment_id
            JOIN classes c ON c.id=a.class_id JOIN school_subjects s ON s.id=a.subject_id
            JOIN users u ON u.id=a.teacher_id WHERE t.id=?""", (slot_id,)).fetchone()
    return {"slot": dict(row)}


@app.get("/api/school-admin/classes/{class_id}/students")
def school_admin_class_students(class_id: str, admin: dict[str, Any] = Depends(current_school_admin)) -> dict[str, Any]:
    with db() as con:
        school = con.execute("SELECT school_id FROM school_admin_accounts WHERE id=?", (admin["id"],)).fetchone()
        if not con.execute("SELECT 1 FROM school_classes WHERE school_id=? AND class_id=?",
                           (school["school_id"], class_id)).fetchone():
            raise HTTPException(404, "Class not found in this school")
        rows = con.execute("SELECT u.id,u.display_name FROM class_members m JOIN users u ON u.id=m.student_id WHERE m.class_id=? ORDER BY u.display_name",
                           (class_id,)).fetchall()
    return {"students": [dict(row) for row in rows]}


@app.post("/api/school-admin/attendance", status_code=201)
def school_admin_mark_attendance(payload: SchoolAttendanceRequest,
                                 admin: dict[str, Any] = Depends(current_school_admin)) -> dict[str, Any]:
    try:
        date.fromisoformat(payload.attendance_date)
    except ValueError as exc:
        raise HTTPException(422, "Invalid attendance date") from exc
    with db() as con:
        school = con.execute("SELECT school_id FROM school_admin_accounts WHERE id=?", (admin["id"],)).fetchone()
        sid = school["school_id"]
        if not con.execute("SELECT 1 FROM school_classes WHERE school_id=? AND class_id=?", (sid, payload.class_id)).fetchone():
            raise HTTPException(404, "Class not found in this school")
        if not con.execute("SELECT 1 FROM class_members WHERE class_id=? AND student_id=?",
                           (payload.class_id, payload.student_id)).fetchone():
            raise HTTPException(404, "Student is not enrolled in this class")
        con.execute("""INSERT INTO school_attendance(school_id,class_id,student_id,attendance_date,status,marked_by)
            VALUES(?,?,?,?,?,?) ON CONFLICT(school_id,class_id,student_id,attendance_date)
            DO UPDATE SET status=excluded.status,marked_by=excluded.marked_by,updated_at=CURRENT_TIMESTAMP""",
            (sid, payload.class_id, payload.student_id, payload.attendance_date, payload.status, admin["id"]))
        con.execute("""INSERT INTO user_notifications(id,recipient_id,recipient_role,kind,title,body)
            VALUES(?,?,'student','attendance','Attendance updated',?)""",
            (str(uuid.uuid4()),payload.student_id,payload.status))
        parents=con.execute("SELECT parent_id FROM parent_student_links WHERE student_id=? AND class_id=?",
                            (payload.student_id,payload.class_id)).fetchall()
        for recipient in parents:
            con.execute("""INSERT INTO user_notifications(id,recipient_id,recipient_role,kind,title,body)
                VALUES(?,?,'parent','attendance','Student attendance updated',?)""",
                (str(uuid.uuid4()),recipient["parent_id"],payload.status))
    return {"saved": True, "class_id": payload.class_id, "student_id": payload.student_id,
            "attendance_date": payload.attendance_date, "status": payload.status}


@app.post("/api/school-admin/lesson-records", status_code=201)
def school_admin_record_lesson(payload: SchoolLessonRecordRequest,
                               admin: dict[str, Any] = Depends(current_school_admin)) -> dict[str, Any]:
    try:
        date.fromisoformat(payload.lesson_date)
    except ValueError as exc:
        raise HTTPException(422, "Invalid lesson date") from exc
    record_id = str(uuid.uuid4())
    with db() as con:
        school = con.execute("SELECT school_id FROM school_admin_accounts WHERE id=?", (admin["id"],)).fetchone()
        sid = school["school_id"]
        if not con.execute("SELECT 1 FROM school_timetable WHERE id=? AND school_id=?",
                           (payload.timetable_id, sid)).fetchone():
            raise HTTPException(404, "Timetable slot not found in this school")
        con.execute("""INSERT INTO school_lesson_records(id,school_id,timetable_id,lesson_date,status,topic,notes,recorded_by)
            VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(school_id,timetable_id,lesson_date) DO UPDATE SET
            status=excluded.status,topic=excluded.topic,notes=excluded.notes,recorded_by=excluded.recorded_by""",
            (record_id, sid, payload.timetable_id, payload.lesson_date, payload.status,
             payload.topic.strip(), payload.notes.strip(), admin["id"]))
        row = con.execute("""SELECT r.id,r.lesson_date,r.status,r.topic,r.notes,c.name AS class_name,
            s.name AS subject_name,u.display_name AS teacher_name
            FROM school_lesson_records r JOIN school_timetable t ON t.id=r.timetable_id
            JOIN school_teaching_assignments a ON a.id=t.teaching_assignment_id
            JOIN classes c ON c.id=a.class_id JOIN school_subjects s ON s.id=a.subject_id
            JOIN users u ON u.id=a.teacher_id WHERE r.school_id=? AND r.timetable_id=? AND r.lesson_date=?""",
            (sid, payload.timetable_id, payload.lesson_date)).fetchone()
    return {"record": dict(row)}


@app.get("/api/school-admin/operations-report")
def school_admin_operations_report(date_from: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
                                   date_to: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
                                   admin: dict[str, Any] = Depends(current_school_admin)) -> dict[str, Any]:
    try:
        date.fromisoformat(date_from)
        date.fromisoformat(date_to)
    except ValueError as exc:
        raise HTTPException(422, "Invalid report date") from exc
    if date_from > date_to:
        raise HTTPException(422, "date_from must not be after date_to")
    with db() as con:
        school = con.execute("SELECT school_id FROM school_admin_accounts WHERE id=?", (admin["id"],)).fetchone()
        sid = school["school_id"]
        attendance = con.execute("SELECT status,COUNT(*) AS count FROM school_attendance WHERE school_id=? AND attendance_date BETWEEN ? AND ? GROUP BY status",
                                 (sid, date_from, date_to)).fetchall()
        lessons = con.execute("SELECT status,COUNT(*) AS count FROM school_lesson_records WHERE school_id=? AND lesson_date BETWEEN ? AND ? GROUP BY status",
                              (sid, date_from, date_to)).fetchall()
        daily = con.execute("SELECT attendance_date AS day,status,COUNT(*) AS count FROM school_attendance WHERE school_id=? AND attendance_date BETWEEN ? AND ? GROUP BY attendance_date,status ORDER BY attendance_date",
                            (sid, date_from, date_to)).fetchall()
    return {"date_from": date_from, "date_to": date_to,
            "attendance": {row["status"]: row["count"] for row in attendance},
            "lessons": {row["status"]: row["count"] for row in lessons},
            "daily_attendance": [dict(row) for row in daily],
            "notice": "Operational records only. Attendance and lesson delivery counts do not measure learning or mastery."}


@app.post("/api/teacher/students/{student_id}/guardian-invite", status_code=201)
def create_guardian_invite(student_id: str, class_id: str = Query(...), teacher: dict[str, Any] = Depends(current_teacher)) -> dict[str, Any]:
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with db() as con:
        member = con.execute("SELECT 1 FROM class_members m JOIN classes c ON c.id=m.class_id WHERE m.student_id=? AND m.class_id=? AND c.teacher_id=?", (student_id, class_id, teacher["id"])).fetchone()
        if not member:
            raise HTTPException(404, "Student not found in a class owned by this teacher")
        con.execute("INSERT INTO guardian_invites(token_hash,student_id,class_id,teacher_id,expires_at) VALUES(?,?,?,?,?)", (digest, student_id, class_id, teacher["id"], int(time.time()) + 7 * 86400))
    return {"invite_token": token, "expires_in_days": 7, "registration_path": "/parent?invite=" + token}


@app.post("/api/auth/register-parent", status_code=201)
def register_parent(payload: ParentRegisterRequest, response: Response) -> dict[str, Any]:
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "Enter a valid email address")
    invite_hash = hashlib.sha256(payload.invite_token.encode("utf-8")).hexdigest()
    salt, password_hash = hash_password(payload.password)
    parent_id, token = str(uuid.uuid4()), new_session_token()
    with db() as con:
        invite = con.execute("SELECT * FROM guardian_invites WHERE token_hash=? AND used_at IS NULL AND expires_at>?", (invite_hash, int(time.time()))).fetchone()
        if not invite:
            raise HTTPException(400, "Invitation is invalid, expired, or already used")
        if con.execute("SELECT 1 FROM users WHERE email=? UNION ALL SELECT 1 FROM parent_accounts WHERE email=?", (email,email)).fetchone():
            raise HTTPException(409, "An account with this email already exists")
        try:
            con.execute("INSERT INTO parent_accounts(id,email,display_name,password_salt,password_hash) VALUES(?,?,?,?,?)", (parent_id,email,payload.display_name.strip(),salt,password_hash))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "An account with this email already exists") from exc
        con.execute("INSERT INTO parent_student_links(parent_id,student_id,class_id) VALUES(?,?,?)", (parent_id,invite["student_id"],invite["class_id"]))
        con.execute("UPDATE guardian_invites SET used_at=CURRENT_TIMESTAMP WHERE token_hash=?", (invite_hash,))
        con.execute("INSERT INTO auth_sessions(token_hash,user_id,expires_at) VALUES(?,?,?)", (token_digest(token),parent_id,int(time.time())+604800))
    response.set_cookie("pupil_session",token,httponly=True,samesite="strict",max_age=604800,path="/")
    return {"user":{"id":parent_id,"email":email,"display_name":payload.display_name.strip(),"role":"parent"}}


def _parent_progress(parent_id: str, student_id: str, class_id: str) -> dict[str, Any]:
    with db() as con:
        link = con.execute("""SELECT u.display_name AS student_name,c.name AS class_name,t.display_name AS teacher_name
            FROM parent_student_links l JOIN users u ON u.id=l.student_id
            JOIN classes c ON c.id=l.class_id JOIN users t ON t.id=c.teacher_id
            WHERE l.parent_id=? AND l.student_id=? AND l.class_id=?""", (parent_id,student_id,class_id)).fetchone()
        if not link:
            raise HTTPException(404, "Linked student report not found")
        sessions = con.execute("SELECT id,lesson_id,transcript,created_at FROM sessions WHERE student_id=? AND class_id=? ORDER BY created_at,id", (student_id,class_id)).fetchall()
        assignments = con.execute("""SELECT a.title,a.lesson_id,a.due_at,
            CASE WHEN sub.student_id IS NULL THEN 0 ELSE 1 END AS submitted,sub.submitted_at
            FROM assignments a LEFT JOIN assignment_submissions sub ON sub.assignment_id=a.id AND sub.student_id=?
            WHERE a.class_id=? ORDER BY a.created_at DESC""", (student_id,class_id)).fetchall()
    records=[]
    for row in sessions:
        lesson=get_lesson(row["lesson_id"])
        if not lesson: continue
        try: transcript=json.loads(row["transcript"] or "[]")
        except (TypeError,json.JSONDecodeError): transcript=[]
        records.append({"session_id":row["id"],"lesson_id":row["lesson_id"],"lesson":lesson["title_ar"],"created_at":row["created_at"],"report":assess_explanation(transcript if isinstance(transcript,list) else [],lesson)})
    journey=build_learning_journey(records)
    return {"student":dict(link),"class_id":class_id,"session_count":journey["session_count"],"lessons":sorted({x["lesson_id"] for x in records}),"concepts":journey["concepts"],"timeline":journey["timeline"],"assignments":[dict(x) for x in assignments],"notice":"تقرير وصفي محدود بالفصل المرتبط. إشارات مطابقة الكلمات ليست درجات أو تشخيصًا أو إثباتًا للإتقان."}


@app.get("/api/parent/students")
def parent_students(parent: dict[str, Any] = Depends(current_parent)) -> dict[str, Any]:
    with db() as con:
        rows=con.execute("""SELECT l.student_id,l.class_id,u.display_name AS student_name,c.name AS class_name,t.display_name AS teacher_name
            FROM parent_student_links l JOIN users u ON u.id=l.student_id JOIN classes c ON c.id=l.class_id
            JOIN users t ON t.id=c.teacher_id WHERE l.parent_id=? ORDER BY c.name,u.display_name""",(parent["id"],)).fetchall()
    return {"students":[dict(x) for x in rows]}


@app.get("/api/parent/students/{student_id}/progress")
def parent_student_progress(student_id: str, class_id: str = Query(...), parent: dict[str, Any] = Depends(current_parent)) -> dict[str, Any]:
    return _parent_progress(parent["id"],student_id,class_id)


@app.get("/api/parent/students/{student_id}/report.pdf")
def parent_student_report_pdf(student_id: str, class_id: str = Query(...), parent: dict[str, Any] = Depends(current_parent)):
    report=_parent_progress(parent["id"],student_id,class_id)
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    def safe(value: Any) -> str:
        return str(value).encode("ascii","replace").decode("ascii").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    buffer=io.BytesIO()
    doc=SimpleDocTemplate(buffer,pagesize=A4,rightMargin=18*mm,leftMargin=18*mm,topMargin=18*mm,bottomMargin=18*mm)
    styles=getSampleStyleSheet()
    story=[Paragraph("PUPIL ZERO - Student Activity Report",styles["Title"]),Spacer(1,8),
        Paragraph("Student: "+safe(report["student"]["student_name"]),styles["Normal"]),
        Paragraph("Class: "+safe(report["student"]["class_name"]),styles["Normal"]),
        Paragraph("Teacher: "+safe(report["student"]["teacher_name"]),styles["Normal"]),
        Paragraph("Recorded sessions: "+str(report["session_count"]),styles["Normal"]),
        Paragraph("Lesson IDs: "+(", ".join(safe(x) for x in report["lessons"]) or "None"),styles["Normal"]),
        Spacer(1,10),Paragraph("Assignments",styles["Heading2"])]
    data=[["Assignment","Lesson ID","Status"]]+[[safe(a["title"]),safe(a["lesson_id"]),"Submitted" if a["submitted"] else "Pending"] for a in report["assignments"]]
    if len(data)==1:data.append(["No assignments","-","-"])
    table=Table(data,repeatRows=1,colWidths=[85*mm,45*mm,35*mm])
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#24324b")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.4,colors.lightgrey),("PADDING",(0,0),(-1,-1),7)]))
    story.extend([table,Spacer(1,10),Paragraph("Keyword evidence signals (not grades)",styles["Heading2"])])
    concepts=[["Concept ID","Sessions with evidence","Sessions observed"]]+[[safe(c["concept_id"]),str(c["sessions_with_evidence"]),str(c["sessions_observed"])] for c in report["concepts"]]
    if len(concepts)==1:concepts.append(["No evidence yet","-","-"])
    ct=Table(concepts,repeatRows=1,colWidths=[55*mm,65*mm,45*mm])
    ct.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#24324b")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.4,colors.lightgrey),("PADDING",(0,0),(-1,-1),7)]))
    story.extend([ct,Spacer(1,10),Paragraph(safe(report["notice"]),styles["Normal"]),Paragraph("Not a grade, diagnosis, or validated measure of learning.",styles["Italic"])])
    doc.build(story);buffer.seek(0)
    return StreamingResponse(buffer,media_type="application/pdf",headers={"Content-Disposition":'attachment; filename="pupil-zero-student-report.pdf"'})

@app.get("/account", response_class=HTMLResponse)
def account_page() -> str:
    return (ROOT / "static" / "account.html").read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return (ROOT / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/student", response_class=HTMLResponse)
def student_home() -> str:
    return (ROOT / "static" / "student.html").read_text(encoding="utf-8")


@app.get("/teacher", response_class=HTMLResponse)
def teacher_home() -> str:
    return (ROOT / "static" / "teacher.html").read_text(encoding="utf-8")


@app.get("/parent", response_class=HTMLResponse)
def parent_home() -> str:
    return (ROOT / "static" / "parent.html").read_text(encoding="utf-8")


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


def _student_progress(student_id: str, class_id: str | None = None) -> dict[str, Any]:
    with db() as con:
        query = "SELECT id,lesson_id,transcript,created_at FROM sessions WHERE student_id=?"
        params: list[Any] = [student_id]
        if class_id:
            query += " AND class_id=?"
            params.append(class_id)
        query += " ORDER BY created_at ASC,id ASC"
        rows = con.execute(query, tuple(params)).fetchall()
    records = []
    lesson_counts: dict[str, dict[str, Any]] = {}
    for row in rows:
        lesson = get_lesson(row["lesson_id"])
        if not lesson:
            continue
        try:
            transcript = json.loads(row["transcript"] or "[]")
        except (TypeError, json.JSONDecodeError):
            transcript = []
        report = assess_explanation(transcript if isinstance(transcript, list) else [], lesson)
        records.append({
            "session_id": row["id"], "lesson_id": row["lesson_id"],
            "lesson": lesson["title_ar"], "created_at": row["created_at"],
            "report": report,
        })
        item = lesson_counts.setdefault(row["lesson_id"], {
            "lesson_id": row["lesson_id"], "lesson": lesson["title_ar"],
            "sessions": 0, "sessions_with_student_responses": 0,
        })
        item["sessions"] += 1
        if any(message.get("role") == "student" for message in transcript if isinstance(message, dict)):
            item["sessions_with_student_responses"] += 1
    journey = build_learning_journey(records)
    return {
        "student_id": student_id,
        "class_id": class_id,
        "session_count": journey["session_count"],
        "lessons": sorted(lesson_counts.values(), key=lambda item: item["lesson"]),
        "concepts": journey["concepts"],
        "timeline": journey["timeline"],
        "notice": journey["notice"],
        "interpretation_warning": "هذه مؤشرات وصفية مبنية على مطابقة كلمات فقط؛ لا تمثل درجات أو تشخيصًا أو إثباتًا للإتقان.",
    }


@app.get("/api/student/progress")
def student_progress(class_id: str | None = Query(default=None), student: dict[str, Any] = Depends(current_student)) -> dict[str, Any]:
    if class_id:
        with db() as con:
            membership = con.execute(
                "SELECT 1 FROM class_members WHERE class_id=? AND student_id=?",
                (class_id, student["id"]),
            ).fetchone()
        if not membership:
            raise HTTPException(404, "Class not found")
    return _student_progress(student["id"], class_id)


@app.get("/api/teacher/classes/{class_id}/progress")
def teacher_class_progress(class_id: str, teacher: dict[str, Any] = Depends(current_teacher)) -> dict[str, Any]:
    with db() as con:
        classroom = con.execute(
            "SELECT id,name FROM classes WHERE id=? AND teacher_id=?",
            (class_id, teacher["id"]),
        ).fetchone()
        if not classroom:
            raise HTTPException(404, "Class not found")
        students = con.execute(
            "SELECT u.id,u.display_name,u.email,m.joined_at FROM class_members m JOIN users u ON u.id=m.student_id WHERE m.class_id=? ORDER BY u.display_name",
            (class_id,),
        ).fetchall()
    results = []
    for student in students:
        progress = _student_progress(student["id"], class_id)
        results.append({
            "student_id": student["id"], "display_name": student["display_name"],
            "joined_at": student["joined_at"], "session_count": progress["session_count"],
            "lesson_count": len(progress["lessons"]),
            "evidence_concepts": sum(item["sessions_with_evidence"] for item in progress["concepts"]),
            "concepts_observed": len(progress["concepts"]),
        })
    return {
        "class_id": class_id, "class_name": classroom["name"],
        "student_count": len(results), "students": results,
        "notice": "مؤشرات وصفية من الجلسات المسجلة فقط. عدم وجود جلسة لا يعني عدم التعلم، ومطابقة الكلمات ليست درجة أو مقياس إتقان.",
    }


@app.get("/api/teacher/classes/{class_id}/review-suggestions")
async def teacher_class_review_suggestions(class_id: str, teacher: dict[str, Any] = Depends(current_teacher)) -> dict[str, Any]:
    with db() as con:
        classroom = con.execute("SELECT id,name FROM classes WHERE id=? AND teacher_id=?",
                                (class_id, teacher["id"])).fetchone()
        if not classroom:
            raise HTTPException(404, "Class not found")
        rows = con.execute("""SELECT q.lesson_id,q.result_json FROM student_quizzes q
            JOIN class_members m ON m.student_id=q.student_id
            WHERE m.class_id=? AND q.submitted_at IS NOT NULL ORDER BY q.submitted_at DESC LIMIT 500""",
            (class_id,)).fetchall()
    counts: dict[tuple[str,str],dict[str,int]] = {}
    for row in rows:
        try:
            result=json.loads(row["result_json"] or "{}")
        except (TypeError,json.JSONDecodeError):
            continue
        for detail in result.get("details",[]):
            key=(row["lesson_id"],detail.get("concept_id",""))
            if not key[1]:
                continue
            bucket=counts.setdefault(key,{"attempts":0,"incorrect":0})
            bucket["attempts"]+=1
            bucket["incorrect"]+=int(not bool(detail.get("correct")))
    suggestions=[]
    for (lesson_id,concept_id),stats in counts.items():
        if stats["incorrect"] < 2:
            continue
        lesson=get_lesson(lesson_id)
        if not lesson:
            continue
        concept=next((item for item in lesson.get("concepts",[]) if item["id"]==concept_id),None)
        if not concept:
            continue
        suggestions.append({"lesson_id":lesson_id,"lesson":lesson["title_ar"],
            "concept_id":concept_id,"concept":concept["label_ar"],
            "attempts":stats["attempts"],"incorrect_answers":stats["incorrect"],
            "activity":"استخدم مثالًا محسوسًا، ثم اطلب من الطلاب مقارنة طريقتين للحل.",
            "teacher_question":"ما الذي يتغير إذا غيّرنا قيمة واحدة فقط؟"})
    suggestions.sort(key=lambda item:(-item["incorrect_answers"],item["lesson"],item["concept"]))
    source="authored_guidance"
    if suggestions and public_status().get("configured"):
        grouped={}
        for item in suggestions:
            grouped.setdefault(item["lesson_id"],[]).append(item)
        try:
            for lesson_id,items in grouped.items():
                lesson=get_lesson(lesson_id)
                patterns=[{"concept_id":x["concept_id"],"concept":x["concept"],
                           "incorrect_answers":x["incorrect_answers"],"attempts":x["attempts"],
                           "authored_correction":next(c["correction"] for c in lesson["concepts"] if c["id"]==x["concept_id"])}
                          for x in items]
                generated=await generate_teacher_review_suggestions(lesson,patterns)
                by_id={x["concept_id"]:x for x in generated}
                for item in items:
                    if item["concept_id"] in by_id:
                        item["activity"]=by_id[item["concept_id"]]["activity"]
                        item["teacher_question"]=by_id[item["concept_id"]]["teacher_question"]
            source="local_ai"
        except Exception:
            source="authored_guidance_fallback"
    return {"class_id":class_id,"class_name":classroom["name"],"suggestions":suggestions,
        "source":source,
        "notice":"تجميع على مستوى الفصل من إجابات الاختبارات التدريبية فقط. لا يعرض أسماء الطلاب ولا يشخّص سوء فهم أو يقيس الإتقان. لا تظهر فكرة إلا بعد تسجيل إجابتين غير صحيحتين على الأقل، ويجب مراجعة المعلم للاقتراح."}


@app.get("/api/teacher/students/{student_id}/progress")
def teacher_student_progress(student_id: str, class_id: str = Query(...), teacher: dict[str, Any] = Depends(current_teacher)) -> dict[str, Any]:
    with db() as con:
        membership = con.execute(
            "SELECT 1 FROM class_members m JOIN classes c ON c.id=m.class_id WHERE m.student_id=? AND m.class_id=? AND c.teacher_id=?",
            (student_id, class_id, teacher["id"]),
        ).fetchone()
    if not membership:
        raise HTTPException(404, "Student progress not found")
    progress = _student_progress(student_id, class_id)
    progress["notice"] += " هذا العرض مقتصر على الفصل المحدد."
    return progress


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
    return {"status": "ok", "product": "PUPIL ZERO", "version": "1.4.0", **public_status()}


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
