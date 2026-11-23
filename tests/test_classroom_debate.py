import json

import pytest
from fastapi.testclient import TestClient

from app import main
from app.classroom_debate import (
    authored_debate,
    build_judgment,
    debate_guidance,
    validate_debate,
)
from app.curriculum import get_lesson


def valid_debate_json():
    return json.dumps({
        "arguments": [
            {"speaker": "milo", "text": "خلينا نبدأ بالحجة الأساسية من الدرس."},
            {"speaker": "noura", "text": "المثال ده يساعدنا نختبر الفكرة بشكل واضح."},
            {"speaker": "zizo", "text": "طب هل الحجة تفضل صحيحة لو غيرنا حالة المثال؟"},
        ],
        "judge_question": "مين حجته أقنعتك أكتر؟ وضح السبب بكلماتك.",
    }, ensure_ascii=False)


def test_debate_guidance_is_grounded_and_has_three_distinct_roles():
    prompt = debate_guidance(get_lesson("fractions"))
    assert "MILO" in prompt and "NOURA" in prompt and "ZIZO" in prompt
    assert "مصدر الحقائق الوحيد" in prompt
    assert "لا تذكر إجابة صحيحة أو فائزًا" in prompt


def test_debate_validation_rejects_missing_speaker_and_invalid_json():
    parsed = validate_debate(valid_debate_json())
    assert [item["speaker"] for item in parsed["arguments"]] == ["milo", "noura", "zizo"]
    with pytest.raises(ValueError):
        validate_debate("not json")
    invalid = json.loads(valid_debate_json())
    invalid["arguments"][2]["speaker"] = "noura"
    with pytest.raises(ValueError):
        validate_debate(json.dumps(invalid, ensure_ascii=False))


def test_authored_debate_and_judgment_are_not_grades():
    debate = authored_debate(get_lesson("fractions"))
    assert len(debate["arguments"]) == 3
    assert "لسه مش متأكد" in debate["judge_question"]
    judgment = build_judgment("milo", "لأن الحجة مرتبطة بشرح الدرس.")
    assert judgment["winner"] == "milo"
    assert "مش درجة" in judgment["reflection"]
    with pytest.raises(ValueError):
        build_judgment("unknown", "سبب كافي")
    with pytest.raises(ValueError):
        build_judgment("zizo", "لا")


def test_student_debate_persistence_judgment_and_account_isolation(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "debates.sqlite3")
    monkeypatch.setattr(main, "public_status", lambda: {
        "provider": "none", "model": None, "configured": False, "mode": "demo_fallback"
    })
    with TestClient(main.app) as teacher, TestClient(main.app) as first, TestClient(main.app) as second:
        assert teacher.post("/api/auth/register-teacher", json={
            "email": "debate-teacher@example.test", "password": "TeacherPass123!",
            "display_name": "Debate Teacher",
        }).status_code == 201
        classroom = teacher.post("/api/classes", json={"name": "Debate Class"}).json()
        for client, email, name in (
            (first, "debate-first@example.test", "First Learner"),
            (second, "debate-second@example.test", "Second Learner"),
        ):
            assert client.post("/api/classes/join", json={
                "join_code": classroom["join_code"], "display_name": name,
                "email": email, "password": "StudentPass123!",
            }).status_code == 201

        started = first.post("/api/student/debates", json={"lesson_id": "fractions"})
        assert started.status_code == 201
        data = started.json()
        assert data["mode"] == "authored_fallback"
        assert data["status"] == "awaiting_judgment"
        debate_id = data["debate_id"]

        assert second.get("/api/student/debates/" + debate_id).status_code == 404
        assert second.post("/api/student/debates/" + debate_id + "/judge", json={
            "winner": "milo", "reason": "محاولة وصول لحساب تاني"
        }).status_code == 404

        judged = first.post("/api/student/debates/" + debate_id + "/judge", json={
            "winner": "noura", "reason": "المثال وضح الفكرة وربطها بالدرس."
        })
        assert judged.status_code == 200
        assert judged.json()["status"] == "completed"
        assert first.post("/api/student/debates/" + debate_id + "/judge", json={
            "winner": "zizo", "reason": "حجة تانية"
        }).status_code == 409

        restored = first.get("/api/student/debates/" + debate_id)
        assert restored.status_code == 200
        assert restored.json()["judgment"]["winner"] == "noura"
        assert restored.json()["judgment"]["reason"] == "المثال وضح الفكرة وربطها بالدرس."
        assert first.get("/api/student/debates").json()["debates"][0]["status"] == "completed"
        assert second.get("/api/student/debates").json()["debates"] == []


def test_live_debate_uses_validated_local_model_output(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "debates-live.sqlite3")
    monkeypatch.setattr(main, "public_status", lambda: {
        "provider": "ollama", "model": "local-test", "configured": True, "mode": "live_ai"
    })
    captured = {}

    async def fake_generate_reply(messages, lesson, persona, dialogue_state):
        captured["messages"] = messages
        captured["guidance"] = dialogue_state
        return valid_debate_json()

    monkeypatch.setattr(main, "generate_reply", fake_generate_reply)
    with TestClient(main.app) as teacher, TestClient(main.app) as student:
        teacher.post("/api/auth/register-teacher", json={
            "email": "debate-live-teacher@example.test", "password": "TeacherPass123!",
            "display_name": "Debate Live Teacher",
        })
        classroom = teacher.post("/api/classes", json={"name": "Live Debate"}).json()
        student.post("/api/classes/join", json={
            "join_code": classroom["join_code"], "display_name": "Learner",
            "email": "debate-live-student@example.test", "password": "StudentPass123!",
        })
        response = student.post("/api/student/debates", json={"lesson_id": "ratio"})
        assert response.status_code == 201
        assert response.json()["mode"] == "live_ai"
        assert len(response.json()["debate"]["arguments"]) == 3
        assert "MILO" in captured["guidance"]
        assert captured["messages"][0]["role"] == "user"
