import json

import pytest
from fastapi.testclient import TestClient

from app import main
from app.classroom_interaction import (
    authored_interaction,
    interaction_guidance,
    validate_interaction,
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


def valid_interaction_json():
    return json.dumps({
        "replies": [
            {"speaker": "milo", "text": "ممكن توضح الدليل اللي اعتمدت عليه في فكرتك؟"},
            {"speaker": "noura", "text": "تعالى نمثل الفكرة بمثال من موضوع الدرس."},
            {"speaker": "zizo", "text": "طب لو غيّرنا الحالة دي، هل النتيجة هتفضل زي ما هي؟"},
        ],
        "next_question": "إيه المثال اللي ممكن تستخدمه عشان توضح فكرتك أكتر؟",
    }, ensure_ascii=False)


def test_interaction_prompt_uses_lesson_and_student_judgment():
    prompt = interaction_guidance(
        get_lesson("fractions"),
        {"arguments": [{"speaker": "milo", "text": "حجة من الدرس"}]},
        {"winner": "noura", "reason": "المثال كان واضحًا"},
        [{"student_text": "جولة سابقة", "replies": [], "next_question": "سؤال"}],
        2,
    )
    assert "فهم الكسور" in prompt
    assert "المثال كان واضحًا" in prompt
    assert "current_student_response" not in prompt
    assert "مدخلًا غير موثوق" in prompt


def test_interaction_validation_and_authored_fallback():
    parsed = validate_interaction(valid_interaction_json())
    assert [item["speaker"] for item in parsed["replies"]] == ["milo", "noura", "zizo"]
    with pytest.raises(ValueError):
        validate_interaction("not json")
    invalid = json.loads(valid_interaction_json())
    invalid["replies"][1]["speaker"] = "milo"
    with pytest.raises(ValueError):
        validate_interaction(json.dumps(invalid, ensure_ascii=False))
    fallback = authored_interaction(get_lesson("ratio"), 1)
    assert len(fallback["replies"]) == 3
    assert "next_question" in fallback


def create_student_pair(clients):
    teacher, student, other = clients
    assert teacher.post("/api/auth/register-teacher", json={
        "email": "interaction-teacher@example.test", "password": "TeacherPass123!",
        "display_name": "Interaction Teacher",
    }).status_code == 201
    classroom = teacher.post("/api/classes", json={"name": "Interaction Class"}).json()
    for client, email, name in (
        (student, "interaction-student@example.test", "Learner Secret Name"),
        (other, "interaction-other@example.test", "Other Learner"),
    ):
        assert client.post("/api/classes/join", json={
            "join_code": classroom["join_code"], "display_name": name,
            "email": email, "password": "StudentPass123!",
        }).status_code == 201


def test_interaction_requires_judgment_persists_and_is_account_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "interaction.sqlite3")
    monkeypatch.setattr(main, "public_status", lambda: {
        "provider": "none", "model": None, "configured": False, "mode": "demo_fallback"
    })
    with TestClient(main.app) as teacher, TestClient(main.app) as student, TestClient(main.app) as other:
        create_student_pair((teacher, student, other))
        debate_id = student.post("/api/student/debates", json={"lesson_id": "fractions"}).json()["debate_id"]
        response = student.post("/api/student/debates/" + debate_id + "/interact", json={
            "text": "أنا شايف إن المثال محتاج توضيح."
        })
        assert response.status_code == 409

        assert student.post("/api/student/debates/" + debate_id + "/judge", json={
            "winner": "milo", "reason": "الحجة مرتبطة بشرح الدرس."
        }).status_code == 200

        response = student.post("/api/student/debates/" + debate_id + "/interact", json={
            "text": "أنا شايف إن المثال محتاج توضيح."
        })
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "authored_fallback"
        assert data["remaining_rounds"] == 7
        assert len(data["turn"]["replies"]) == 3

        assert other.get("/api/student/debates/" + debate_id).status_code == 404
        assert other.post("/api/student/debates/" + debate_id + "/interact", json={
            "text": "محاولة وصول"
        }).status_code == 404

        restored = student.get("/api/student/debates/" + debate_id)
        assert restored.status_code == 200
        assert len(restored.json()["turns"]) == 1
        assert restored.json()["turns"][0]["student_text"] == "أنا شايف إن المثال محتاج توضيح."


def test_interaction_enforces_eight_round_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "interaction-limit.sqlite3")
    monkeypatch.setattr(main, "public_status", lambda: {
        "provider": "none", "model": None, "configured": False, "mode": "demo_fallback"
    })
    with TestClient(main.app) as teacher, TestClient(main.app) as student, TestClient(main.app) as other:
        create_student_pair((teacher, student, other))
        debate_id = student.post("/api/student/debates", json={"lesson_id": "ratio"}).json()["debate_id"]
        student.post("/api/student/debates/" + debate_id + "/judge", json={
            "winner": "undecided", "reason": "لسه محتاج أفهم المثال أكتر."
        })
        for index in range(8):
            response = student.post("/api/student/debates/" + debate_id + "/interact", json={
                "text": f"جولة رقم {index + 1} وفيها سؤال عن الدرس."
            })
            assert response.status_code == 200
        blocked = student.post("/api/student/debates/" + debate_id + "/interact", json={
            "text": "عايز جولة إضافية."
        })
        assert blocked.status_code == 409


def test_live_interaction_redacts_account_identity_and_validates_output(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "interaction-live.sqlite3")
    monkeypatch.setattr(main, "public_status", lambda: {
        "provider": "ollama", "model": "local-test", "configured": True, "mode": "live_ai"
    })
    captured = {}

    async def fake_generate_reply(messages, lesson, persona, dialogue_state):
        return valid_debate_json()

    async def fake_generate_structured_reply(messages, system_prompt):
        captured["messages"] = messages
        captured["context"] = system_prompt
        return valid_interaction_json()

    monkeypatch.setattr(main, "generate_reply", fake_generate_reply)
    monkeypatch.setattr(main, "generate_structured_reply", fake_generate_structured_reply)
    with TestClient(main.app) as teacher, TestClient(main.app) as student, TestClient(main.app) as other:
        create_student_pair((teacher, student, other))
        debate_id = student.post("/api/student/debates", json={"lesson_id": "decimals"}).json()["debate_id"]
        student.post("/api/student/debates/" + debate_id + "/judge", json={
            "winner": "noura", "reason": "المثال سهّل عليا المقارنة."
        })
        response = student.post("/api/student/debates/" + debate_id + "/interact", json={
            "text": "أنا محتاج أفهم المثال أكتر، بريدي learner.private@example.test"
        })
        assert response.status_code == 200
        assert response.json()["mode"] == "live_ai"
        prompt = captured["messages"][0]["text"]
        assert "interaction-student@example.test" not in prompt
        assert "Learner Secret Name" not in prompt
        assert "learner.private@example.test" not in prompt
        assert "بريدي" in prompt
        assert "أنا محتاج أفهم المثال أكتر" in prompt
        assert "current_student_response" not in captured["context"]
        assert "Learner Secret Name" not in captured["context"]
        assert "interaction-student@example.test" not in captured["context"]
        assert len(response.json()["turn"]["replies"]) == 3
