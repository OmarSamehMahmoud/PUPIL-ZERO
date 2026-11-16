from __future__ import annotations
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from app.curriculum import get_lesson
from app.assessment import assess_explanation

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "pupil_zero.db"
app = FastAPI(title="PUPIL ZERO", version="0.1.0", description="Voice-first AI classmate learning MVP")
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
            transcript TEXT NOT NULL DEFAULT '[]', created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")

@app.on_event("startup")
def startup() -> None:
    init_db()

@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return (ROOT / "static" / "index.html").read_text(encoding="utf-8")

@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "product": "PUPIL ZERO", "version": "0.1.0"}

@app.get("/api/lessons")
def lessons() -> list[dict[str, str]]:
    lesson = get_lesson("fractions")
    return [{"id": lesson["id"], "title_ar": lesson["title_ar"], "title_en": lesson["title_en"], "grade": lesson["grade"]}]

@app.post("/api/sessions")
def start_session(payload: StartRequest) -> dict[str, Any]:
    lesson = get_lesson(payload.lesson_id)
    if not lesson:
        raise HTTPException(404, "Lesson not found")
    session_id = str(uuid.uuid4())
    opening = lesson["scenarios"][0]["prompt_ar"]
    transcript = [{"role": "ai", "text": opening}]
    with db() as con:
        con.execute("INSERT INTO sessions(id, lesson_id, persona, transcript) VALUES (?, ?, ?, ?)",
                    (session_id, payload.lesson_id, payload.persona, json.dumps(transcript, ensure_ascii=False)))
    return {"session_id": session_id, "persona": payload.persona, "lesson": lesson["title_ar"], "reply": opening}

def make_reply(student_text: str, lesson: dict[str, Any], count: int) -> str:
    text = student_text.strip()
    if len(text) < 8:
        return "ممكن تشرحلي أكتر؟ اديني مثال من الحياة اليومية عشان أفهم."
    if count == 1:
        return "طيب، خليني أتأكد إني فهمت... هل كلامك يفضل صحيح لو حجم البيتزا اتغير؟ وليه؟"
    if count == 2:
        return "طب ممكن تشرحلي الفرق بين ١/٢ و٢/٤ برسمة أو مثال بسيط؟"
    return "أنا بدأت أفهم! ممكن تسألني سؤال صغير تتأكد بيه إني استوعبت الفكرة؟"

@app.post("/api/message")
def send_message(payload: MessageRequest) -> dict[str, str]:
    with db() as con:
        row = con.execute("SELECT * FROM sessions WHERE id=?", (payload.session_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Session not found")
        transcript = json.loads(row["transcript"])
        transcript.append({"role": "student", "text": payload.text})
        lesson = get_lesson(row["lesson_id"])
        student_count = sum(1 for m in transcript if m["role"] == "student")
        reply = make_reply(payload.text, lesson, student_count)
        transcript.append({"role": "ai", "text": reply})
        con.execute("UPDATE sessions SET transcript=? WHERE id=?",
                    (json.dumps(transcript, ensure_ascii=False), payload.session_id))
    return {"reply": reply}

@app.post("/api/finish")
def finish_session(payload: FinishRequest) -> dict[str, Any]:
    with db() as con:
        row = con.execute("SELECT * FROM sessions WHERE id=?", (payload.session_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Session not found")
    transcript = json.loads(row["transcript"])
    lesson = get_lesson(row["lesson_id"])
    return {"transcript": transcript, "report": assess_explanation(transcript, lesson), "lesson": lesson["title_ar"]}
