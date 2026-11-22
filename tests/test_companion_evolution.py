import json

from fastapi.testclient import TestClient

from app import main
from app.companion_evolution import (
    build_companion_progress,
    companion_evolution_guidance,
    count_completed_exchanges,
)


def test_companion_progress_uses_only_explicit_exchange_milestones():
    assert build_companion_progress(0)["level"] == 1
    assert build_companion_progress(2)["exchanges_to_next"] == 1
    assert build_companion_progress(3)["level"] == 2
    assert build_companion_progress(8)["level"] == 3
    final = build_companion_progress(15)
    assert final["level"] == 4
    assert final["next_milestone"] is None
    assert "لا يقيس الذكاء أو الإتقان" in final["notice"]


def test_personas_have_distinct_guidance_and_stage_evolves():
    milo = companion_evolution_guidance("step_by_step", "milo", 0)
    noura = companion_evolution_guidance("step_by_step", "noura", 0)
    zizo = companion_evolution_guidance("step_by_step", "zizo", 0)
    assert len({milo, noura, zizo}) == 3
    assert "MILO" in milo and "فضولي" in milo
    assert "NOURA" in noura and "تشبيه يومي" in noura
    assert "ZIZO" in zizo and "تحديًا صغيرًا" in zizo
    assert "شركاء التحدي" in companion_evolution_guidance("quiz_me", "zizo", 15)


def test_completed_exchange_counter_ignores_unanswered_student_turns():
    complete = json.dumps([
        {"role": "student", "text": "سؤال 1"},
        {"role": "ai", "text": "رد 1"},
        {"role": "student", "text": "سؤال 2"},
        {"role": "ai", "text": "رد 2"},
        {"role": "student", "text": "لم يتم الرد بعد"},
    ])
    assert count_completed_exchanges([complete, "not-json"]) == 2


def test_companion_evolution_is_account_scoped_and_progresses_with_completed_turns(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "companion-evolution.sqlite3")
    monkeypatch.setattr(main, "public_status", lambda: {
        "provider": "none", "model": None, "configured": False, "mode": "demo_fallback"
    })
    with TestClient(main.app) as teacher, TestClient(main.app) as student, TestClient(main.app) as other:
        teacher.post("/api/auth/register-teacher", json={
            "email": "evolution-teacher@example.test",
            "password": "TeacherPass123!",
            "display_name": "Teacher",
        })
        classroom = teacher.post("/api/classes", json={"name": "Evolution Class"}).json()
        for client, email, display_name in (
            (student, "evolution-student@example.test", "Student One"),
            (other, "evolution-other@example.test", "Student Two"),
        ):
            assert client.post("/api/classes/join", json={
                "join_code": classroom["join_code"],
                "display_name": display_name,
                "email": email,
                "password": "StudentPass123!",
            }).status_code == 201

        initial = student.get("/api/student/companion").json()
        assert initial["progress"]["level"] == 1
        assert {item["id"] for item in initial["persona_cards"]} == {"milo", "noura", "zizo"}
        student.put("/api/student/companion/profile", json={
            "persona": "noura", "learning_style": "example_first"
        })
        for expected in (1, 2, 3):
            response = student.post("/api/student/companion/messages", json={
                "lesson_id": "fractions",
                "text": "عايز أفهم الكسور بمثال من البيتزا",
            })
            assert response.status_code == 200
            assert response.json()["persona"] == "noura"
            assert response.json()["progress"]["exchange_count"] == expected
        assert response.json()["progress"]["level"] == 2
        assert student.get("/api/student/companion").json()["progress"]["level"] == 2
        assert other.get("/api/student/companion").json()["progress"]["exchange_count"] == 0
