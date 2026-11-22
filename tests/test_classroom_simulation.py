import json

import pytest
from fastapi.testclient import TestClient

from app import main
from app.classroom_simulation import (
    authored_roundtable,
    classroom_guidance,
    format_roundtable,
    validate_roundtable,
)


def test_classroom_guidance_defines_three_distinct_grounded_roles():
    from app.curriculum import get_lesson

    guidance = classroom_guidance(get_lesson("fractions"))
    assert "MILO" in guidance
    assert "NOURA" in guidance
    assert "ZIZO" in guidance
    assert "مصدر الحقائق الوحيد" in guidance
    assert "JSON فقط" in guidance


def test_roundtable_output_validation_requires_all_speakers_and_followup():
    raw = json.dumps({
        "contributions": [
            {"speaker": "milo", "text": "خلينا نبدأ بسؤال بسيط عن الفكرة."},
            {"speaker": "noura", "text": "ممكن نستخدم مثالًا من الحياة اليومية."},
            {"speaker": "zizo", "text": "عندي تحدي صغير واختياري ليك."},
        ],
        "teacher_question": "تحب تشرح الفكرة بطريقتك؟",
    }, ensure_ascii=False)
    parsed = validate_roundtable(raw)
    assert [row["speaker"] for row in parsed["contributions"]] == ["milo", "noura", "zizo"]
    assert "سؤال الفصل" in format_roundtable(parsed)
    with pytest.raises(ValueError):
        validate_roundtable("not json")
    malformed = json.loads(raw)
    malformed["contributions"][1]["speaker"] = "milo"
    with pytest.raises(ValueError):
        validate_roundtable(json.dumps(malformed, ensure_ascii=False))


def test_authored_fallback_has_three_classmates_and_no_ai_claim():
    from app.curriculum import get_lesson

    roundtable = authored_roundtable("عايز أفهم الدرس", get_lesson("fractions"))
    assert [row["speaker"] for row in roundtable["contributions"]] == ["milo", "noura", "zizo"]
    assert roundtable["teacher_question"]


def test_classroom_sessions_are_private_persistent_and_lesson_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "classroom.sqlite3")
    monkeypatch.setattr(main, "public_status", lambda: {
        "provider": "none", "model": None, "configured": False, "mode": "demo_fallback"
    })
    with TestClient(main.app) as teacher, TestClient(main.app) as first, TestClient(main.app) as second:
        assert teacher.post("/api/auth/register-teacher", json={
            "email": "room-teacher@example.test", "password": "TeacherPass123!",
            "display_name": "Room Teacher",
        }).status_code == 201
        classroom = teacher.post("/api/classes", json={"name": "Room Class"}).json()
        for client, email, name in (
            (first, "room-first@example.test", "First Learner"),
            (second, "room-second@example.test", "Second Learner"),
        ):
            assert client.post("/api/classes/join", json={
                "join_code": classroom["join_code"], "display_name": name,
                "email": email, "password": "StudentPass123!",
            }).status_code == 201

        sent = first.post("/api/student/classroom/messages", json={
            "lesson_id": "fractions", "text": "ممكن نتناقش في معنى الكسر؟",
        })
        assert sent.status_code == 200
        data = sent.json()
        assert data["mode"] == "authored_fallback"
        assert [row["speaker"] for row in data["contributions"]] == ["milo", "noura", "zizo"]
        assert len(data["transcript"]) == 2
        session_id = data["session_id"]

        listing = first.get("/api/student/classroom")
        assert listing.status_code == 200
        assert listing.json()["sessions"][0]["session_id"] == session_id
        restored = first.get("/api/student/classroom/" + session_id)
        assert restored.status_code == 200
        assert restored.json()["transcript"] == data["transcript"]

        followup = first.post("/api/student/classroom/messages", json={
            "session_id": session_id, "text": "عايز مثال كمان",
        })
        assert followup.status_code == 200
        assert len(followup.json()["transcript"]) == 4
        assert second.get("/api/student/classroom/" + session_id).status_code == 404
        assert second.post("/api/student/classroom/messages", json={
            "session_id": session_id, "text": "محاولة وصول لحساب آخر",
        }).status_code == 404
        assert second.get("/api/student/classroom").json()["sessions"] == []
        assert first.post("/api/student/classroom/messages", json={
            "lesson_id": "not-a-lesson", "text": "اختبار",
        }).status_code == 404


def test_classroom_live_model_receives_redacted_text_and_validates_output(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "classroom-live.sqlite3")
    monkeypatch.setattr(main, "public_status", lambda: {
        "provider": "ollama", "model": "local-test", "configured": True, "mode": "live_ai"
    })
    captured = {}

    async def fake_generate_reply(messages, lesson, persona, dialogue_state):
        captured["messages"] = messages
        captured["guidance"] = dialogue_state
        return json.dumps({
            "contributions": [
                {"speaker": "milo", "text": "خلينا نكتشف الفكرة مع بعض."},
                {"speaker": "noura", "text": "نستخدم مثالًا بسيطًا من الدرس."},
                {"speaker": "zizo", "text": "عندي تحدي اختياري صغير."},
            ],
            "teacher_question": "إيه رأيك تشرحها بطريقتك؟",
        }, ensure_ascii=False)

    monkeypatch.setattr(main, "generate_reply", fake_generate_reply)
    with TestClient(main.app) as teacher, TestClient(main.app) as student:
        teacher.post("/api/auth/register-teacher", json={
            "email": "live-room-teacher@example.test", "password": "TeacherPass123!",
            "display_name": "Live Room Teacher",
        })
        classroom = teacher.post("/api/classes", json={"name": "Live Room"}).json()
        student.post("/api/classes/join", json={
            "join_code": classroom["join_code"], "display_name": "Private Learner",
            "email": "private-room@example.test", "password": "StudentPass123!",
        })
        response = student.post("/api/student/classroom/messages", json={
            "lesson_id": "fractions",
            "text": "أنا Private Learner وبريدي private-room@example.test ورقمي 01012345678",
        })
        assert response.status_code == 200
        assert response.json()["mode"] == "live_ai"
        joined = " ".join(item["text"] for item in captured["messages"])
        assert "Private Learner" not in joined
        assert "private-room@example.test" not in joined
        assert "01012345678" not in joined
        assert "MILO" in captured["guidance"] and "NOURA" in captured["guidance"]
