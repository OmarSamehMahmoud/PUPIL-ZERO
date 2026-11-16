from fastapi.testclient import TestClient

from app import main


def test_student_and_teacher_flow_uses_local_database(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    with TestClient(main.app) as client:
        lessons = client.get("/api/lessons")
        assert lessons.status_code == 200
        lesson_ids = {lesson["id"] for lesson in lessons.json()}
        assert {"fractions", "decimals", "ratio"} <= lesson_ids

        started = client.post("/api/sessions", json={"lesson_id": "decimals", "persona": "noura"})
        assert started.status_code == 200
        session_id = started.json()["session_id"]

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

        assert client.get("/teacher").status_code == 200
