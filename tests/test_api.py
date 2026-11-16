import sqlite3

from fastapi.testclient import TestClient

from app import main


def test_student_and_teacher_flow_uses_local_database(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    with TestClient(main.app) as client:
        lessons = client.get("/api/lessons")
        assert lessons.status_code == 200
        lesson_ids = {lesson["id"] for lesson in lessons.json()}
        assert {"fractions", "decimals", "ratio"} <= lesson_ids

        learner_id = "12345678-1234-4234-8234-123456789abc"
        started = client.post("/api/sessions", json={"lesson_id": "decimals", "persona": "noura", "learner_id": learner_id})
        assert started.status_code == 200
        session_id = started.json()["session_id"]
        assert started.json()["learner_id"] == learner_id
        journey = client.get(f"/api/learner/journey/{learner_id}")
        assert journey.status_code == 200
        assert journey.json()["session_count"] == 1
        assert journey.json()["timeline"][0]["session_id"] == session_id
        assert client.get("/api/learner/journey/not-a-uuid").status_code == 422

        second = client.post("/api/sessions", json={"lesson_id": "fractions", "persona": "milo", "learner_id": learner_id})
        assert second.status_code == 200
        assert client.get(f"/api/learner/journey/{learner_id}").json()["session_count"] == 2

        rejected = client.post("/api/sessions", json={"lesson_id": "decimals", "persona": "unknown"})
        assert rejected.status_code == 422

        listing = client.get("/api/teacher/sessions")
        assert listing.status_code == 200
        assert listing.json()["count"] == 1
        assert listing.json()["sessions"][0]["persona"] == "noura"

        detail = client.get(f"/api/teacher/sessions/{session_id}")
        assert detail.status_code == 200
        assert detail.json()["lesson"] == "فهم الأعداد العشرية"
        assert detail.json()["transcript"][0]["role"] == "ai"
        assert detail.json()["dialogue_state"]["stage"] == "elicit"

        message = client.post("/api/message", json={"session_id": session_id, "text": "0.80 أكبر من 0.75 بالمقارنة"})
        assert message.status_code == 200
        assert message.json()["stage"] == "transfer"
        updated = client.get(f"/api/teacher/sessions/{session_id}")
        assert updated.json()["dialogue_state"]["scenario_index"] == 1

        insights = client.get("/api/teacher/insights")
        assert insights.status_code == 200
        assert insights.json()["total_sessions"] == 1
        assert insights.json()["lessons"][0]["lesson_id"] == "decimals"
        assert len(insights.json()["lessons"][0]["concepts"]) == 2

        filtered = client.get("/api/teacher/insights?lesson_id=fractions")
        assert filtered.status_code == 200
        assert filtered.json()["total_sessions"] == 0
        unknown = client.get("/api/teacher/insights?lesson_id=unknown")
        assert unknown.status_code == 404

        priorities = client.get("/api/teacher/priorities")
        assert priorities.status_code == 200
        assert priorities.json()["priorities"] == []
        assert "ليست تشخيصًا" in priorities.json()["notice"]

        unknown_priorities = client.get("/api/teacher/priorities?lesson_id=unknown")
        assert unknown_priorities.status_code == 404

        assert client.get("/teacher").status_code == 200



def test_init_db_migrates_legacy_sessions_table(tmp_path, monkeypatch):
    path = tmp_path / "legacy.sqlite3"
    monkeypatch.setattr(main, "DB_PATH", path)
    with sqlite3.connect(path) as con:
        con.execute("""CREATE TABLE sessions (
            id TEXT PRIMARY KEY, lesson_id TEXT NOT NULL, persona TEXT NOT NULL,
            transcript TEXT NOT NULL DEFAULT '[]', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            state_json TEXT NOT NULL DEFAULT '{}'
        )""")
    main.init_db()
    with sqlite3.connect(path) as con:
        columns = {row[1] for row in con.execute("PRAGMA table_info(sessions)")}
    assert "learner_id" in columns
