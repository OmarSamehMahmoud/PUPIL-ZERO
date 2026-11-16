import sqlite3

from fastapi.testclient import TestClient

from app import main


def test_student_and_teacher_flow_uses_local_database(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    with TestClient(main.app) as client:
        teacher = client.post("/api/auth/register-teacher", json={
            "email": "teacher@example.test", "password": "StrongPass123!", "display_name": "Teacher One"
        })
        assert teacher.status_code == 201
        assert teacher.json()["user"]["role"] == "teacher"
        assert client.get("/api/auth/me").status_code == 200
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


        rejected = client.post("/api/sessions", json={"lesson_id": "decimals", "persona": "unknown"})
        assert rejected.status_code == 422

        classroom = client.post("/api/classes", json={"name": "Class 1", "grade_label": "Primary 5"})
        assert classroom.status_code == 201
        join_code = classroom.json()["join_code"]
        assert len(join_code) == 8
        assert client.get("/api/classes").json()["classes"][0]["student_count"] == 0
        joined = client.post("/api/classes/join", json={
            "join_code": join_code, "display_name": "Student One",
            "email": "student@example.test", "password": "StudentPass123!"
        })
        assert joined.status_code == 201
        assert joined.json()["class"]["name"] == "Class 1"
        # Joining creates a student login cookie; restore the teacher session for roster checks.
        assert client.get("/api/auth/me").json()["user"]["role"] == "student"
        assert client.post("/api/auth/login", json={
            "email": "teacher@example.test", "password": "StrongPass123!"
        }).status_code == 200
        members = client.get(f"/api/classes/{classroom.json()['id']}/members")
        assert members.status_code == 200
        assert len(members.json()["members"]) == 1
        assert members.json()["members"][0]["display_name"] == "Student One"

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

        second = client.post("/api/sessions", json={"lesson_id": "fractions", "persona": "milo", "learner_id": learner_id})
        assert second.status_code == 200
        updated_journey = client.get(f"/api/learner/journey/{learner_id}")
        assert updated_journey.json()["session_count"] == 2
        assert {item["lesson_id"] for item in updated_journey.json()["timeline"]} == {"decimals", "fractions"}

        plan = client.get("/api/teacher/interventions?lesson_id=decimals&concept_id=decimal_comparison")
        assert plan.status_code == 200
        assert plan.json()["teacher_decision_required"] is True
        assert len(plan.json()["steps"]) == 4
        assert plan.json()["feedback_summary"]["total"] == 0
        saved = client.post("/api/teacher/interventions/feedback", json={
            "lesson_id": "decimals", "concept_id": "decimal_comparison",
            "rating": "helpful", "note": "واضحة ومناسبة"
        })
        assert saved.status_code == 201
        assert saved.json()["saved"] is True
        for rating in ("partly_helpful", "not_helpful"):
            response = client.post("/api/teacher/interventions/feedback", json={
                "lesson_id": "decimals", "concept_id": "decimal_comparison", "rating": rating
            })
            assert response.status_code == 201
        summary = client.get("/api/teacher/interventions/feedback?lesson_id=decimals&concept_id=decimal_comparison")
        assert summary.status_code == 200
        assert summary.json()["total"] == 3
        assert summary.json()["helpful"] == 1
        assert "وصفي" in summary.json()["sample_notice"]
        assert "note" not in summary.json()
        assert client.post("/api/teacher/interventions/feedback", json={
            "lesson_id": "decimals", "concept_id": "decimal_comparison", "rating": "invalid"
        }).status_code == 422
        assert client.post("/api/teacher/interventions/feedback", json={
            "lesson_id": "unknown", "concept_id": "x", "rating": "helpful"
        }).status_code == 404
        assert client.get("/api/teacher/interventions/feedback?lesson_id=unknown&concept_id=x").status_code == 404
        assert client.get("/api/teacher/interventions?lesson_id=decimals&concept_id=missing").status_code == 404
        assert client.get("/api/teacher/interventions?lesson_id=missing&concept_id=x").status_code == 404
        assert client.get("/teacher").status_code == 200



def test_teacher_area_requires_login(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "auth.sqlite3")
    with TestClient(main.app) as client:
        assert client.get("/api/teacher/sessions").status_code == 401
        assert client.get("/teacher").status_code == 401
        assert client.post("/api/auth/login", json={"email": "none@example.test", "password": "wrong"}).status_code == 401
        registered = client.post("/api/auth/register-teacher", json={
            "email": "owner@example.test", "password": "AnotherStrong123!", "display_name": "Owner"
        })
        assert registered.status_code == 201
        assert client.get("/api/teacher/sessions").status_code == 200
        assert client.post("/api/auth/logout").json()["logged_out"] is True
        assert client.get("/api/teacher/sessions").status_code == 401


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
    assert {"learner_id", "student_id", "class_id", "teacher_id"} <= columns



def test_class_linked_student_sessions_are_scoped_to_their_teacher(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "class_scope.sqlite3")
    with TestClient(main.app) as teacher_a, TestClient(main.app) as student, TestClient(main.app) as teacher_b:
        a = teacher_a.post("/api/auth/register-teacher", json={
            "email": "a@example.test", "password": "TeacherPass123!", "display_name": "Teacher A"
        })
        assert a.status_code == 201
        classroom = teacher_a.post("/api/classes", json={"name": "A Class"})
        assert classroom.status_code == 201

        joined = student.post("/api/classes/join", json={
            "join_code": classroom.json()["join_code"], "display_name": "Learner",
            "email": "learner@example.test", "password": "StudentPass123!"
        })
        assert joined.status_code == 201
        student_id = joined.json()["student"]["id"]
        assert student.get("/api/auth/me").json()["user"]["role"] == "student"
        assert student.get("/api/student/classes").json()["classes"][0]["id"] == classroom.json()["id"]
        assert student.get("/api/teacher/sessions").status_code == 401

        started = student.post("/api/sessions", json={
            "lesson_id": "fractions", "persona": "milo", "class_id": classroom.json()["id"]
        })
        assert started.status_code == 200
        assert started.json()["learner_id"] == student_id
        session_id = started.json()["session_id"]
        assert student.get(f"/api/learner/journey/{student_id}").json()["session_count"] == 1
        assert student.get("/api/learner/journey/12345678-1234-4234-8234-123456789abc").status_code == 403
        assert student.post("/api/sessions", json={
            "lesson_id": "fractions", "persona": "milo", "class_id": "not-enrolled"
        }).status_code == 403

        assert teacher_a.get("/api/teacher/sessions").json()["count"] == 1
        assert teacher_a.get(f"/api/teacher/sessions/{session_id}").status_code == 200
        assert student.post("/api/message", json={
            "session_id": session_id, "text": "الكسر يمثل جزءًا من كل"
        }).status_code == 200

        teacher_b.post("/api/auth/register-teacher", json={
            "email": "b@example.test", "password": "TeacherPass123!", "display_name": "Teacher B"
        })
        assert teacher_b.get("/api/teacher/sessions").json()["count"] == 0
        assert teacher_b.get(f"/api/teacher/sessions/{session_id}").status_code == 404
        assert teacher_b.get(f"/api/classes/{classroom.json()['id']}/members").status_code == 404
