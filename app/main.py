from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.assessment import assess_explanation
from app.curriculum import get_lesson
from app.llm import generate_reply, public_status
from app.pedagogy import advance_state, initial_state, state_context

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "pupil_zero.db"
app = FastAPI(title="PUPIL ZERO", version="0.3.0", description="Local-first learning-by-teaching MVP")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


class StartRequest(BaseModel):
    lesson_id: str = "fractions"
    persona: str = "milo"


class MessageRequest(BaseModel):
    session_id: str
    text: str = Field(min_length=1, max_length=3000)


class FinishRequest(BaseModel):
    session_id: str


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY, lesson_id TEXT NOT NULL, persona TEXT NOT NULL,
            transcript TEXT NOT NULL DEFAULT '[]', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            state_json TEXT NOT NULL DEFAULT '{}'
        )""")
        columns = {row["name"] for row in con.execute("PRAGMA table_info(sessions)")}
        if "state_json" not in columns:
            con.execute("ALTER TABLE sessions ADD COLUMN state_json TEXT NOT NULL DEFAULT '{}'")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return (ROOT / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/teacher", response_class=HTMLResponse)
def teacher_home() -> str:
    return (ROOT / "static" / "teacher.html").read_text(encoding="utf-8")


@app.get("/api/teacher/sessions")
def teacher_sessions(limit: int = Query(default=30, ge=1, le=100)) -> dict[str, Any]:
    """Local prototype dashboard; protect the host before exposing beyond localhost."""
    with db() as con:
        rows = con.execute(
            "SELECT id, lesson_id, persona, transcript, created_at FROM sessions "
            "ORDER BY created_at DESC LIMIT ?", (limit,)
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
            "student_turns": sum(1 for message in transcript if message.get("role") == "student"),
            "coverage_signal": report["coverage_signal"],
            "label": report["label"],
        })
    return {"sessions": items, "count": len(items), "notice": "Prototype dashboard: no login or role-based access yet. Keep the server on localhost."}


@app.get("/api/teacher/sessions/{session_id}")
def teacher_session_detail(session_id: str) -> dict[str, Any]:
    with db() as con:
        row = con.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
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
    return {"status": "ok", "product": "PUPIL ZERO", "version": "0.3.0", **public_status()}


@app.get("/api/lessons")
def lessons() -> list[dict[str, str]]:
    from app.curriculum import list_lessons
    return list_lessons()


@app.post("/api/sessions")
def start_session(payload: StartRequest) -> dict[str, Any]:
    lesson = get_lesson(payload.lesson_id)
    if not lesson:
        raise HTTPException(404, "Lesson not found")
    if payload.persona not in {"milo", "noura", "zizo"}:
        raise HTTPException(422, "Unknown classmate persona")
    session_id = str(uuid.uuid4())
    opening = lesson["scenarios"][0]["prompt_ar"]
    transcript = [{"role": "ai", "text": opening}]
    dialogue_state = initial_state(lesson)
    with db() as con:
        con.execute(
            "INSERT INTO sessions(id, lesson_id, persona, transcript, state_json) VALUES (?, ?, ?, ?, ?)",
            (session_id, payload.lesson_id, payload.persona,
             json.dumps(transcript, ensure_ascii=False),
             json.dumps(dialogue_state, ensure_ascii=False)),
        )
    return {
        "session_id": session_id,
        "persona": payload.persona,
        "lesson": lesson["title_ar"],
        "reply": opening,
        "stage": dialogue_state["stage"],
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
async def send_message(payload: MessageRequest) -> dict[str, Any]:
    with db() as con:
        row = con.execute("SELECT * FROM sessions WHERE id=?", (payload.session_id,)).fetchone()
    if not row:
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
def finish_session(payload: FinishRequest) -> dict[str, Any]:
    with db() as con:
        row = con.execute("SELECT * FROM sessions WHERE id=?", (payload.session_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Session not found")
    transcript = json.loads(row["transcript"])
    lesson = get_lesson(row["lesson_id"])
    return {
        "transcript": transcript,
        "report": assess_explanation(transcript, lesson),
        "dialogue_state": json.loads(row["state_json"] or "{}"),
        "lesson": lesson["title_ar"],
        "mode": public_status()["mode"],
    }
