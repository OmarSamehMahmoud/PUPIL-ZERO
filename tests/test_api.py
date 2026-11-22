from datetime import date
import sqlite3
import json

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
        assert teacher_a.get("/api/teacher/sessions?class_id=" + classroom.json()["id"]).json()["count"] == 1
        assert teacher_a.get("/api/teacher/insights?class_id=not-owned").status_code == 404
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


def test_assignment_lifecycle_and_class_isolation(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "assignments.sqlite3")
    with TestClient(main.app) as teacher, TestClient(main.app) as student, TestClient(main.app) as outsider:
        assert teacher.post("/api/auth/register-teacher", json={
            "email": "assign-teacher@example.test", "password": "TeacherPass123!", "display_name": "Assignment Teacher"
        }).status_code == 201
        classroom = teacher.post("/api/classes", json={"name": "Math A"})
        assert classroom.status_code == 201
        joined = student.post("/api/classes/join", json={
            "join_code": classroom.json()["join_code"], "display_name": "Student One",
            "email": "assignment-student@example.test", "password": "StudentPass123!"
        })
        assert joined.status_code == 201

        created = teacher.post("/api/teacher/assignments", json={
            "class_id": classroom.json()["id"], "title": "Explain fractions",
            "description": "Use an example from daily life.", "lesson_id": "fractions"
        })
        assert created.status_code == 201
        assignment_id = created.json()["id"]
        assert teacher.get("/api/teacher/assignments").json()["assignments"][0]["student_count"] == 1
        assert outsider.get("/api/teacher/assignments").status_code == 401
        assert student.get("/api/student/assignments").json()["assignments"][0]["submitted"] == 0

        wrong_lesson = student.post("/api/sessions", json={
            "lesson_id": "decimals", "persona": "milo", "class_id": classroom.json()["id"],
            "assignment_id": assignment_id
        })
        assert wrong_lesson.status_code == 422
        started = student.post("/api/sessions", json={
            "lesson_id": "fractions", "persona": "milo", "class_id": classroom.json()["id"],
            "assignment_id": assignment_id
        })
        assert started.status_code == 200
        session_id = started.json()["session_id"]
        assert student.post("/api/message", json={
            "session_id": session_id, "text": "الكسر نصف يعني جزء من جزأين متساويين"
        }).status_code == 200
        assert student.post("/api/finish", json={"session_id": session_id}).status_code == 200
        student_task = student.get("/api/student/assignments").json()["assignments"][0]
        assert student_task["submitted"] == 1
        assert student_task["session_id"] == session_id
        teacher_task = teacher.get("/api/teacher/assignments").json()["assignments"][0]
        assert teacher_task["submitted_count"] == 1
        assert teacher_task["students"][0]["display_name"] == "Student One"
        duplicate = student.post("/api/sessions", json={
            "lesson_id": "fractions", "persona": "milo", "class_id": classroom.json()["id"],
            "assignment_id": assignment_id
        })
        assert duplicate.status_code == 409

        assert outsider.post("/api/teacher/assignments", json={
            "class_id": classroom.json()["id"], "title": "Cross class", "lesson_id": "fractions"
        }).status_code == 401
        assert teacher.post("/api/teacher/assignments", json={
            "class_id": "not-owned", "title": "Cross class", "lesson_id": "fractions"
        }).status_code == 404


def test_student_progress_and_teacher_class_analytics_are_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "progress.sqlite3")
    with TestClient(main.app) as teacher, TestClient(main.app) as student, TestClient(main.app) as other_teacher, TestClient(main.app) as other_student:
        assert teacher.post("/api/auth/register-teacher", json={
            "email": "progress-teacher@example.test", "password": "TeacherPass123!", "display_name": "Progress Teacher"
        }).status_code == 201
        classroom = teacher.post("/api/classes", json={"name": "Progress Class"})
        assert classroom.status_code == 201
        joined = student.post("/api/classes/join", json={
            "join_code": classroom.json()["join_code"], "display_name": "Progress Learner",
            "email": "progress-student@example.test", "password": "StudentPass123!"
        })
        assert joined.status_code == 201
        student_id = joined.json()["student"]["id"]

        started = student.post("/api/sessions", json={
            "lesson_id": "fractions", "persona": "milo", "class_id": classroom.json()["id"]
        })
        assert started.status_code == 200
        sid = started.json()["session_id"]
        assert student.post("/api/message", json={
            "session_id": sid, "text": "النصف هو جزء من جزأين متساويين في الكل"
        }).status_code == 200

        own = student.get("/api/student/progress")
        assert own.status_code == 200
        assert own.json()["session_count"] == 1
        assert own.json()["lessons"][0]["lesson_id"] == "fractions"
        assert own.json()["interpretation_warning"]

        class_report = teacher.get(f"/api/teacher/classes/{classroom.json()['id']}/progress")
        assert class_report.status_code == 200
        assert class_report.json()["student_count"] == 1
        assert class_report.json()["students"][0]["student_id"] == student_id
        assert class_report.json()["students"][0]["session_count"] == 1

        individual = teacher.get(f"/api/teacher/students/{student_id}/progress?class_id={classroom.json()['id']}")
        assert individual.status_code == 200
        assert individual.json()["session_count"] == 1

        assert other_teacher.post("/api/auth/register-teacher", json={
            "email": "other-progress@example.test", "password": "TeacherPass123!", "display_name": "Other Teacher"
        }).status_code == 201
        assert other_teacher.get(f"/api/teacher/classes/{classroom.json()['id']}/progress").status_code == 404
        assert other_teacher.get(f"/api/teacher/students/{student_id}/progress?class_id={classroom.json()['id']}").status_code == 404

        other_class = other_teacher.post("/api/classes", json={"name": "Other Class"})
        assert other_class.status_code == 201
        other_join = other_student.post("/api/classes/join", json={
            "join_code": other_class.json()["join_code"], "display_name": "Other Learner",
            "email": "other-progress-student@example.test", "password": "StudentPass123!"
        })
        assert other_join.status_code == 201
        assert student.get("/api/student/progress?class_id=" + other_class.json()["id"]).status_code == 404


def test_guardian_invite_parent_portal_and_pdf_are_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "parents.sqlite3")
    with TestClient(main.app) as teacher, TestClient(main.app) as student, TestClient(main.app) as parent, TestClient(main.app) as other_parent, TestClient(main.app) as other_teacher:
        assert teacher.post("/api/auth/register-teacher", json={
            "email": "guardian-teacher@example.test", "password": "TeacherPass123!", "display_name": "Class Teacher"
        }).status_code == 201
        classroom = teacher.post("/api/classes", json={"name": "Guardian Class"})
        assert classroom.status_code == 201
        joined = student.post("/api/classes/join", json={
            "join_code": classroom.json()["join_code"], "display_name": "Learner One",
            "email": "guardian-student@example.test", "password": "StudentPass123!"
        })
        assert joined.status_code == 201
        student_id = joined.json()["student"]["id"]
        started = student.post("/api/sessions", json={
            "lesson_id": "fractions", "persona": "milo", "class_id": classroom.json()["id"]
        })
        assert started.status_code == 200
        assert student.post("/api/message", json={
            "session_id": started.json()["session_id"], "text": "النصف جزء من جزأين متساويين"
        }).status_code == 200

        invite = teacher.post(
            f"/api/teacher/students/{student_id}/guardian-invite?class_id={classroom.json()['id']}"
        )
        assert invite.status_code == 201
        token = invite.json()["invite_token"]
        assert len(token) >= 30
        assert other_teacher.post("/api/auth/register-teacher", json={
            "email": "guardian-other-teacher@example.test", "password": "TeacherPass123!", "display_name": "Other Teacher"
        }).status_code == 201
        assert other_teacher.post(
            f"/api/teacher/students/{student_id}/guardian-invite?class_id={classroom.json()['id']}"
        ).status_code == 404

        registration = parent.post("/api/auth/register-parent", json={
            "invite_token": token, "email": "guardian-parent@example.test",
            "password": "ParentPass123!", "display_name": "Parent One"
        })
        assert registration.status_code == 201
        assert registration.json()["user"]["role"] == "parent"
        assert parent.get("/api/auth/me").json()["user"]["role"] == "parent"
        assert parent.get("/api/parent/students").json()["students"][0]["student_id"] == student_id

        progress = parent.get(
            f"/api/parent/students/{student_id}/progress?class_id={classroom.json()['id']}"
        )
        assert progress.status_code == 200
        assert progress.json()["session_count"] == 1
        assert progress.json()["assignments"] == []
        assert parent.get(
            "/api/parent/students/" + "12345678-1234-4234-8234-123456789abc" +
            "?class_id=" + classroom.json()["id"]
        ).status_code == 404

        pdf = parent.get(
            f"/api/parent/students/{student_id}/report.pdf?class_id={classroom.json()['id']}"
        )
        assert pdf.status_code == 200
        assert pdf.headers["content-type"] == "application/pdf"
        assert pdf.content.startswith(b"%PDF")

        assert other_parent.post("/api/auth/login", json={
            "email": "guardian-parent@example.test", "password": "ParentPass123!"
        }).status_code == 200
        assert other_parent.get("/api/parent/students").json()["students"][0]["student_id"] == student_id
        assert other_parent.post("/api/auth/logout").status_code == 200
        assert other_parent.get("/api/parent/students").status_code == 401

        reused = other_parent.post("/api/auth/register-parent", json={
            "invite_token": token, "email": "second-parent@example.test",
            "password": "ParentPass123!", "display_name": "Second Parent"
        })
        assert reused.status_code == 400
        assert student.get("/api/parent/students").status_code == 401
        assert teacher.get("/api/parent/students").status_code == 401


def test_school_admin_workspace_and_school_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "schools.sqlite3")
    with TestClient(main.app) as admin_a, TestClient(main.app) as teacher, TestClient(main.app) as student, TestClient(main.app) as admin_b:
        created = admin_a.post("/api/auth/register-school-admin", json={
            "school_name": "North School", "email": "admin-a@example.test",
            "password": "SchoolAdmin123!", "display_name": "School Admin"
        })
        assert created.status_code == 201
        assert created.json()["user"]["role"] == "school_admin"
        assert admin_a.get("/api/auth/me").json()["user"]["role"] == "school_admin"
        assert admin_a.get("/api/school-admin/overview").json()["school"]["name"] == "North School"
        assert admin_a.get("/api/teacher/sessions").status_code == 401

        assert teacher.post("/api/auth/register-teacher", json={
            "email": "school-teacher@example.test", "password": "TeacherPass123!", "display_name": "School Teacher"
        }).status_code == 201
        linked = admin_a.post("/api/school-admin/teachers", json={"teacher_email": "school-teacher@example.test"})
        assert linked.status_code == 201
        assert admin_a.post("/api/school-admin/teachers", json={"teacher_email": "school-teacher@example.test"}).status_code == 409
        classroom = teacher.post("/api/classes", json={"name": "North Grade 5"})
        assert classroom.status_code == 201

        joined = student.post("/api/classes/join", json={
            "join_code": classroom.json()["join_code"], "display_name": "Learner",
            "email": "school-learner@example.test", "password": "StudentPass123!"
        })
        assert joined.status_code == 201
        overview = admin_a.get("/api/school-admin/overview")
        assert overview.status_code == 200
        assert overview.json()["teacher_count"] == 1
        assert overview.json()["class_count"] == 1
        assert overview.json()["student_enrollments"] == 1
        assert overview.json()["classes"][0]["teacher_name"] == "School Teacher"

        second = admin_b.post("/api/auth/register-school-admin", json={
            "school_name": "South School", "email": "admin-b@example.test",
            "password": "SchoolAdmin456!", "display_name": "Other Admin"
        })
        assert second.status_code == 201
        assert admin_b.get("/api/school-admin/overview").json()["class_count"] == 0
        assert admin_b.post("/api/school-admin/teachers", json={"teacher_email": "school-teacher@example.test"}).status_code == 409
        assert admin_b.post("/api/school-admin/teachers", json={"teacher_email": "missing@example.test"}).status_code == 404
        assert teacher.get("/api/school-admin/overview").status_code == 401
        assert admin_a.post("/api/auth/logout").status_code == 200
        assert admin_a.get("/api/school-admin/overview").status_code == 401


def test_school_teacher_invite_registration_and_unlink_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "school_invites.sqlite3")
    with TestClient(main.app) as admin, TestClient(main.app) as invited_teacher, TestClient(main.app) as outsider:
        created = admin.post("/api/auth/register-school-admin", json={
            "school_name": "Invite Academy", "email": "invite-admin@example.test",
            "password": "SchoolAdmin123!", "display_name": "Admin"
        })
        assert created.status_code == 201

        invite = admin.post("/api/school-admin/teacher-invites", json={"email": "new-teacher@example.test"})
        assert invite.status_code == 201
        token = invite.json()["invite_token"]
        assert invite.json()["expires_in_days"] == 7

        wrong_email = invited_teacher.post("/api/auth/register-invited-teacher", json={
            "invite_token": token, "email": "someone-else@example.test",
            "password": "TeacherPass123!", "display_name": "Wrong Person"
        })
        assert wrong_email.status_code == 400

        registered = invited_teacher.post("/api/auth/register-invited-teacher", json={
            "invite_token": token, "email": "NEW-TEACHER@example.test",
            "password": "TeacherPass123!", "display_name": "Invited Teacher"
        })
        assert registered.status_code == 201
        teacher_id = registered.json()["user"]["id"]
        assert invited_teacher.get("/api/auth/me").json()["user"]["role"] == "teacher"

        replay = outsider.post("/api/auth/register-invited-teacher", json={
            "invite_token": token, "email": "new-teacher@example.test",
            "password": "TeacherPass456!", "display_name": "Replay"
        })
        assert replay.status_code == 400

        classroom = invited_teacher.post("/api/classes", json={"name": "Invited Class"})
        assert classroom.status_code == 201
        overview = admin.get("/api/school-admin/overview").json()
        assert overview["teacher_count"] == 1
        assert overview["class_count"] == 1

        unlinked = admin.delete(f"/api/school-admin/teachers/{teacher_id}")
        assert unlinked.status_code == 200
        assert unlinked.json()["unlinked"] is True
        after = admin.get("/api/school-admin/overview").json()
        assert after["teacher_count"] == 0
        assert after["class_count"] == 0
        # Unlinking is a school relationship change, not account or class deletion.
        assert invited_teacher.get("/api/classes").status_code == 200
        assert invited_teacher.get(f"/api/classes/{classroom.json()['id']}/members").status_code == 200
        assert admin.delete(f"/api/school-admin/teachers/{teacher_id}").status_code == 404



def test_school_academic_structure_and_assignment_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "school_academics.sqlite3")
    with TestClient(main.app) as admin, TestClient(main.app) as teacher, TestClient(main.app) as student, TestClient(main.app) as other_admin:
        assert admin.post("/api/auth/register-school-admin", json={
            "school_name": "Academic School", "email": "academic-admin@example.test",
            "password": "SchoolAdmin123!", "display_name": "Academic Admin"
        }).status_code == 201
        assert teacher.post("/api/auth/register-teacher", json={
            "email": "academic-teacher@example.test", "password": "TeacherPass123!", "display_name": "Math Teacher"
        }).status_code == 201
        assert admin.post("/api/school-admin/teachers", json={"teacher_email": "academic-teacher@example.test"}).status_code == 201
        classroom = teacher.post("/api/classes", json={"name": "Grade 5 A", "grade_label": "Primary 5"})
        assert classroom.status_code == 201

        department = admin.post("/api/school-admin/departments", json={"name": "Mathematics"})
        grade = admin.post("/api/school-admin/grade-levels?sort_order=5", json={"name": "Primary 5"})
        subject = admin.post("/api/school-admin/subjects", json={
            "name": "Fractions", "department_id": department.json()["id"]
        })
        assert department.status_code == grade.status_code == subject.status_code == 201
        assert admin.post("/api/school-admin/class-grades", json={
            "class_id": classroom.json()["id"], "grade_level_id": grade.json()["id"]
        }).status_code == 201
        assigned = admin.post("/api/school-admin/teaching-assignments", json={
            "class_id": classroom.json()["id"], "subject_id": subject.json()["id"],
            "teacher_id": admin.get("/api/school-admin/overview").json()["teachers"][0]["id"]
        })
        assert assigned.status_code == 201
        assert assigned.json()["assignment"]["teacher_name"] == "Math Teacher"

        overview = admin.get("/api/school-admin/overview").json()
        assert overview["departments"][0]["name"] == "Mathematics"
        assert overview["grade_levels"][0]["name"] == "Primary 5"
        assert overview["classes"][0]["academic_grade"] == "Primary 5"
        assert overview["teaching_assignments"][0]["subject_name"] == "Fractions"

        assert student.get("/api/school-admin/overview").status_code == 401
        assert other_admin.post("/api/auth/register-school-admin", json={
            "school_name": "Other Academic School", "email": "other-academic-admin@example.test",
            "password": "SchoolAdmin456!", "display_name": "Other Admin"
        }).status_code == 201
        assert other_admin.post("/api/school-admin/subjects", json={
            "name": "Foreign subject", "department_id": department.json()["id"]
        }).status_code == 404
        assert other_admin.post("/api/school-admin/class-grades", json={
            "class_id": classroom.json()["id"], "grade_level_id": grade.json()["id"]
        }).status_code == 404
        assert other_admin.post("/api/school-admin/teaching-assignments", json={
            "class_id": classroom.json()["id"], "subject_id": subject.json()["id"],
            "teacher_id": overview["teachers"][0]["id"]
        }).status_code == 404
        assert admin.post("/api/school-admin/departments", json={"name": "Mathematics"}).status_code == 409



def test_school_timetable_attendance_and_lesson_operations_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "school_operations.sqlite3")
    with TestClient(main.app) as admin, TestClient(main.app) as teacher, TestClient(main.app) as student, TestClient(main.app) as other_admin:
        assert admin.post("/api/auth/register-school-admin", json={
            "school_name": "Operations School", "email": "ops-admin@example.test",
            "password": "SchoolAdmin123!", "display_name": "Ops Admin"
        }).status_code == 201
        assert teacher.post("/api/auth/register-teacher", json={
            "email": "ops-teacher@example.test", "password": "TeacherPass123!", "display_name": "Ops Teacher"
        }).status_code == 201
        assert admin.post("/api/school-admin/teachers", json={"teacher_email": "ops-teacher@example.test"}).status_code == 201
        classroom = teacher.post("/api/classes", json={"name": "Ops Class"})
        joined = student.post("/api/classes/join", json={
            "join_code": classroom.json()["join_code"], "display_name": "Ops Learner",
            "email": "ops-learner@example.test", "password": "StudentPass123!"
        })
        assert joined.status_code == 201
        department = admin.post("/api/school-admin/departments", json={"name": "Science"})
        subject = admin.post("/api/school-admin/subjects", json={"name": "Biology", "department_id": department.json()["id"]})
        overview = admin.get("/api/school-admin/overview").json()
        assignment = admin.post("/api/school-admin/teaching-assignments", json={
            "class_id": classroom.json()["id"], "subject_id": subject.json()["id"],
            "teacher_id": overview["teachers"][0]["id"]
        })
        assert assignment.status_code == 201
        assignment_id = assignment.json()["assignment"]["id"]

        slot = admin.post("/api/school-admin/timetable", json={
            "teaching_assignment_id": assignment_id, "day_of_week": 0,
            "start_time": "08:00", "end_time": "08:45"
        })
        assert slot.status_code == 201
        assert admin.post("/api/school-admin/timetable", json={
            "teaching_assignment_id": assignment_id, "day_of_week": 0,
            "start_time": "08:30", "end_time": "09:00"
        }).status_code == 409
        assert admin.post("/api/school-admin/timetable", json={
            "teaching_assignment_id": assignment_id, "day_of_week": 0,
            "start_time": "09:00", "end_time": "08:30"
        }).status_code == 422

        roster = admin.get(f"/api/school-admin/classes/{classroom.json()['id']}/students")
        student_id = roster.json()["students"][0]["id"]
        marked = admin.post("/api/school-admin/attendance", json={
            "class_id": classroom.json()["id"], "student_id": student_id,
            "attendance_date": "2026-11-17", "status": "present"
        })
        assert marked.status_code == 201
        assert admin.post("/api/school-admin/attendance", json={
            "class_id": classroom.json()["id"], "student_id": student_id,
            "attendance_date": "2026-11-17", "status": "late"
        }).status_code == 201
        assert admin.post("/api/school-admin/lesson-records", json={
            "timetable_id": slot.json()["slot"]["id"], "lesson_date": "2026-11-17",
            "status": "completed", "topic": "Cells", "notes": "Lab activity"
        }).status_code == 201

        report = admin.get("/api/school-admin/operations-report?date_from=2026-11-01&date_to=2026-11-30")
        assert report.status_code == 200
        assert report.json()["attendance"]["late"] == 1
        assert report.json()["lessons"]["completed"] == 1
        assert report.json()["daily_attendance"][0]["day"] == "2026-11-17"

        assert student.get("/api/school-admin/operations-report?date_from=2026-11-01&date_to=2026-11-30").status_code == 401
        assert other_admin.post("/api/auth/register-school-admin", json={
            "school_name": "Other Ops", "email": "other-ops-admin@example.test",
            "password": "SchoolAdmin456!", "display_name": "Other Ops Admin"
        }).status_code == 201
        assert other_admin.get(f"/api/school-admin/classes/{classroom.json()['id']}/students").status_code == 404
        assert other_admin.post("/api/school-admin/lesson-records", json={
            "timetable_id": slot.json()["slot"]["id"], "lesson_date": "2026-11-17",
            "status": "completed"
        }).status_code == 404
        assert other_admin.get("/api/school-admin/operations-report?date_from=2026-11-01&date_to=2026-11-30").json()["attendance"] == {}



def test_daily_learning_experience_and_role_scoped_notifications(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "daily_learning.sqlite3")
    with TestClient(main.app) as admin, TestClient(main.app) as teacher, TestClient(main.app) as student:
        assert admin.post("/api/auth/register-school-admin", json={
            "school_name":"Daily School","email":"daily-admin@example.test",
            "password":"SchoolAdmin123!","display_name":"Daily Admin"}).status_code == 201
        assert teacher.post("/api/auth/register-teacher", json={
            "email":"daily-teacher@example.test","password":"TeacherPass123!","display_name":"Daily Teacher"}).status_code == 201
        assert admin.post("/api/school-admin/teachers", json={"teacher_email":"daily-teacher@example.test"}).status_code == 201
        classroom=teacher.post("/api/classes",json={"name":"Daily Class"})
        joined=student.post("/api/classes/join",json={"join_code":classroom.json()["join_code"],
            "display_name":"Daily Student","email":"daily-student@example.test","password":"StudentPass123!"})
        student_id=joined.json()["student"]["id"]
        department=admin.post("/api/school-admin/departments",json={"name":"Languages"})
        subject=admin.post("/api/school-admin/subjects",json={"name":"English","department_id":department.json()["id"]})
        overview=admin.get("/api/school-admin/overview").json()
        assignment=admin.post("/api/school-admin/teaching-assignments",json={"class_id":classroom.json()["id"],
            "subject_id":subject.json()["id"],"teacher_id":overview["teachers"][0]["id"]})
        slot=admin.post("/api/school-admin/timetable",json={"teaching_assignment_id":assignment.json()["assignment"]["id"],
            "day_of_week":date.today().weekday(),"start_time":"10:00","end_time":"10:45"})
        assert slot.status_code==201
        task=teacher.post("/api/teacher/assignments",json={"class_id":classroom.json()["id"],
            "title":"Reading practice","description":"Read the passage","lesson_id":"fractions","due_at":"2026-11-20T17:00"})
        assert task.status_code==201
        student_dash=student.get("/api/student/dashboard")
        assert student_dash.status_code==200
        assert any(x["subject_name"]=="English" for x in student_dash.json()["timetable"])
        assert any(x["title"]=="Reading practice" for x in student_dash.json()["assignments"])
        assert student_dash.json()["notifications"][0]["kind"]=="assignment"
        assert teacher.get("/api/teacher/operations").json()["timetable"][0]["subject_name"]=="English"
        mark=teacher.post("/api/teacher/attendance",json={"class_id":classroom.json()["id"],
            "student_id":student_id,"attendance_date":date.today().isoformat(),"status":"present"})
        assert mark.status_code==201
        assert student.get("/api/student/dashboard").json()["attendance"][0]["status"]=="present"
        notification=student.get("/api/student/notifications").json()["notifications"][0]
        assert notification["kind"]=="attendance"
        assert student.post(f"/api/notifications/{notification['id']}/read",json={}).status_code==200
        assert student.get("/api/parent/students").status_code==401



def test_student_adaptive_study_plan_and_single_use_quiz(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "learning_engine.sqlite3")
    with TestClient(main.app) as teacher, TestClient(main.app) as student:
        assert teacher.post("/api/auth/register-teacher", json={
            "email":"engine-teacher@example.test","password":"TeacherPass123!","display_name":"Teacher"}).status_code==201
        classroom=teacher.post("/api/classes",json={"name":"Engine Class"})
        joined=student.post("/api/classes/join",json={"join_code":classroom.json()["join_code"],
            "display_name":"Engine Student","email":"engine-student@example.test","password":"StudentPass123!"})
        assert joined.status_code==201
        plan=student.get("/api/student/study-plan/fractions")
        assert plan.status_code==200
        assert len(plan.json()["steps"])==3
        assert all(x["priority"]=="practice" for x in plan.json()["steps"])
        created=student.post("/api/student/quizzes",json={"lesson_id":"fractions"})
        assert created.status_code==201
        quiz=created.json()
        assert len(quiz["questions"])==3
        assert "correct_option" not in quiz["questions"][0]
        answers={q["id"]:q["options"][0]["id"] for q in quiz["questions"]}
        submitted=student.post(f"/api/student/quizzes/{quiz['quiz_id']}/submit",json={"answers":answers})
        assert submitted.status_code==200
        assert submitted.json()["total"]==3
        assert len(submitted.json()["details"])==3
        assert student.post(f"/api/student/quizzes/{quiz['quiz_id']}/submit",json={"answers":answers}).status_code==409
        history=student.get("/api/student/quizzes/history")
        assert history.status_code==200 and len(history.json()["history"])==1
        assert teacher.get(f"/api/student/study-plan/fractions").status_code==401



def test_quiz_uses_local_ai_generator_when_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "ai_quiz.sqlite3")
    monkeypatch.setattr(main, "public_status", lambda: {"configured": True, "mode": "live_ai"})
    async def fake_generate(lesson, count=3):
        return [{
            "id": f"ai_test_{i}", "concept_id": lesson["concepts"][i % len(lesson["concepts"])]["id"],
            "prompt": f"سؤال تجريبي صالح رقم {i + 1}؟",
            "options": [{"id":"a","text":"اختيار أول"},{"id":"b","text":"اختيار ثان"},{"id":"c","text":"اختيار ثالث"}],
            "correct_option":"b", "explanation":"هذا تفسير تدريبي واضح للإجابة الصحيحة."
        } for i in range(count)]
    monkeypatch.setattr(main, "generate_formative_quiz", fake_generate)
    with TestClient(main.app) as teacher, TestClient(main.app) as student:
        assert teacher.post("/api/auth/register-teacher", json={
            "email":"ai-engine-teacher@example.test","password":"TeacherPass123!","display_name":"Teacher"}).status_code==201
        classroom=teacher.post("/api/classes",json={"name":"AI Engine Class"})
        joined=student.post("/api/classes/join",json={"join_code":classroom.json()["join_code"],
            "display_name":"AI Learner","email":"ai-engine-student@example.test","password":"StudentPass123!"})
        assert joined.status_code==201
        response=student.post("/api/student/quizzes",json={"lesson_id":"fractions"})
        assert response.status_code==201
        data=response.json()
        assert data["source"]=="local_ai"
        assert len(data["questions"])==3
        assert "correct_option" not in data["questions"][0]
        assert data["questions"][0]["options"][1]["id"]=="b"


def test_invalid_local_ai_question_set_is_rejected(tmp_path, monkeypatch):
    from app.learning_engine import validate_question_set
    from app.curriculum import get_lesson
    invalid=[{"id":"bad","concept_id":"not_a_lesson_concept","prompt":"سؤال غير صالح؟",
              "options":[{"id":"a","text":"أ"},{"id":"b","text":"ب"},{"id":"c","text":"ج"}],
              "correct_option":"a","explanation":"تفسير صالح"}]
    try:
        validate_question_set(invalid, get_lesson("fractions"))
        assert False, "Expected invalid generated question to be rejected"
    except ValueError:
        pass



def test_student_gets_private_alternative_feedback_and_teacher_aggregate(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "v22_feedback.sqlite3")
    monkeypatch.setattr(main, "public_status", lambda: {"configured": True, "mode": "live_ai"})
    async def fake_generate(lesson, incorrect_items):
        return [{"question_id":item["question_id"],"feedback":"اختيارك مفهوم، وخلّينا نفكر فيها بهدوء.",
                 "alternative_explanation":"تخيّل نفس البيتزا مقسمة إلى أجزاء متساوية.",
                 "practice_prompt":"ارسم بيتزا مقسمة إلى أربعة أجزاء."} for item in incorrect_items]
    async def fake_teacher(lesson, patterns):
        return [{"concept_id":item["concept_id"],"activity":"اعرض نموذجًا بصريًا وقارن بين طريقتين.",
                 "teacher_question":"كيف نعرف حجم الجزء عندما يزيد عدد الأجزاء؟"} for item in patterns]
    async def fake_quiz(lesson, count=3):
        from app.learning_engine import get_quiz_questions
        return get_quiz_questions(lesson["id"])[:count]
    monkeypatch.setattr(main, "generate_formative_quiz", fake_quiz)
    monkeypatch.setattr(main, "generate_learning_feedback", fake_generate)
    monkeypatch.setattr(main, "generate_teacher_review_suggestions", fake_teacher)
    with TestClient(main.app) as teacher, TestClient(main.app) as student:
        assert teacher.post("/api/auth/register-teacher",json={"email":"v22teacher@example.test",
            "password":"TeacherPass123!","display_name":"Teacher"}).status_code==201
        classroom=teacher.post("/api/classes",json={"name":"Review Class"})
        code=classroom.json()["join_code"]
        assert student.post("/api/classes/join",json={"join_code":code,"display_name":"Learner One",
            "email":"v22student1@example.test","password":"StudentPass123!"}).status_code==201
        quiz=student.post("/api/student/quizzes",json={"lesson_id":"fractions"}).json()
        answers={q["id"]:"a" for q in quiz["questions"]}
        # Ensure at least one wrong answer independent of option order.
        stored=main.db()
        try:
            qs=stored.execute("SELECT questions_json FROM student_quizzes WHERE id=?",(quiz["quiz_id"],)).fetchone()
            questions=__import__("json").loads(qs["questions_json"])
        finally:
            stored.close()
        answers={q["id"]:next(o["id"] for o in q["options"] if o["id"]!=q["correct_option"]) for q in questions}
        submitted=student.post(f"/api/student/quizzes/{quiz['quiz_id']}/submit",json={"answers":answers})
        assert submitted.status_code==200
        assert submitted.json()["feedback_source"]=="local_ai"
        assert all("learning_feedback" in d for d in submitted.json()["details"] if not d["correct"])
        second_quiz=student.post("/api/student/quizzes",json={"lesson_id":"fractions"}).json()
        second_answers={}
        for q in second_quiz["questions"]:
            original=next(x for x in questions if x["id"]==q["id"])
            second_answers[q["id"]]=next(o["id"] for o in original["options"] if o["id"]!=original["correct_option"])
        assert student.post(f"/api/student/quizzes/{second_quiz['quiz_id']}/submit",json={"answers":second_answers}).status_code==200
        suggestions=teacher.get(f"/api/teacher/classes/{classroom.json()['id']}/review-suggestions")
        assert suggestions.status_code==200
        assert suggestions.json()["source"]=="local_ai"
        assert suggestions.json()["suggestions"]
        assert "student_id" not in str(suggestions.json())
        assert student.get(f"/api/teacher/classes/{classroom.json()['id']}/review-suggestions").status_code==401


def test_review_suggestions_are_class_scoped_and_require_two_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "v22_scope.sqlite3")
    monkeypatch.setattr(main, "public_status", lambda: {"configured": False})
    with TestClient(main.app) as teacher, TestClient(main.app) as student:
        teacher.post("/api/auth/register-teacher",json={"email":"scope22teacher@example.test",
            "password":"TeacherPass123!","display_name":"Teacher"})
        classroom=teacher.post("/api/classes",json={"name":"Private Class"}).json()
        student.post("/api/classes/join",json={"join_code":classroom["join_code"],"display_name":"Student",
            "email":"scope22student@example.test","password":"StudentPass123!"})
        result=teacher.get(f"/api/teacher/classes/{classroom['id']}/review-suggestions")
        assert result.status_code==200
        assert result.json()["suggestions"]==[]
        assert teacher.get("/api/teacher/classes/not-owned/review-suggestions").status_code==404


def test_open_response_analysis_is_private_lesson_scoped_and_has_authored_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "v23_open_response.sqlite3")
    monkeypatch.setattr(main, "public_status", lambda: {"configured": False})
    with TestClient(main.app) as teacher, TestClient(main.app) as student:
        teacher.post("/api/auth/register-teacher", json={
            "email":"v23teacher@example.test","password":"TeacherPass123!","display_name":"Teacher"})
        classroom=teacher.post("/api/classes",json={"name":"V23 Class"}).json()
        joined=student.post("/api/classes/join",json={"join_code":classroom["join_code"],
            "display_name":"Learner","email":"v23student@example.test","password":"StudentPass123!"})
        assert joined.status_code==201
        response=student.post("/api/student/open-response",json={"lesson_id":"fractions",
            "answer":"البسط والمقام بيوضحوا أجزاء متساوية من نفس الحجم"})
        assert response.status_code==200
        data=response.json()
        assert data["source"]=="authored_keyword_signal"
        assert any(x["concept_id"]=="numerator_denominator" and x["status"]=="evidence_found" for x in data["signals"])
        assert len(data["suggested_path"])==3
        assert "ليست تشخيصًا" in data["notice"]
        assert "student_id" not in str(data) and "Learner" not in str(data)
        assert student.post("/api/student/open-response",json={"lesson_id":"not-a-lesson",
            "answer":"شرح طويل بما يكفي"}).status_code==404
        assert student.post("/api/student/open-response",json={"lesson_id":"fractions","answer":"قصير"}).status_code==422
        assert teacher.post("/api/student/open-response",json={"lesson_id":"fractions",
            "answer":"البسط والمقام أجزاء متساوية"}).status_code==401


def test_open_response_model_failure_uses_labelled_keyword_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "v23_invalid_quote.sqlite3")
    monkeypatch.setattr(main, "public_status", lambda: {"configured": True})
    async def invalid_analysis(lesson, answer):
        raise RuntimeError("Model output failed evidence validation")
    monkeypatch.setattr(main, "generate_open_response_analysis", invalid_analysis)
    with TestClient(main.app) as student:
        teacher = TestClient(main.app)
        teacher.post("/api/auth/register-teacher", json={"email":"fallbackteacher@example.test",
            "password":"TeacherPass123!","display_name":"Teacher"})
        classroom=teacher.post("/api/classes",json={"name":"Fallback Class"}).json()
        student.post("/api/classes/join",json={"join_code":classroom["join_code"],
            "display_name":"Learner","email":"fallbackstudent@example.test","password":"StudentPass123!"})
        response=student.post("/api/student/open-response",json={"lesson_id":"fractions",
            "answer":"البسط والمقام أجزاء متساوية من نفس الحجم"})
        assert response.status_code==200
        assert response.json()["source"]=="authored_keyword_fallback"


def test_learning_graph_is_authored_and_teacher_owned(tmp_path, monkeypatch):
    monkeypatch.setattr(main,"DB_PATH",tmp_path/"v24_graph.sqlite3")
    with TestClient(main.app) as teacher, TestClient(main.app) as outsider:
        teacher.post("/api/auth/register-teacher",json={"email":"graphowner@example.test",
            "password":"TeacherPass123!","display_name":"Owner"})
        outsider.post("/api/auth/register-teacher",json={"email":"graphother@example.test",
            "password":"TeacherPass123!","display_name":"Other"})
        classroom=teacher.post("/api/classes",json={"name":"Graph Class"}).json()
        graph=teacher.get(f"/api/teacher/classes/{classroom['id']}/learning-graph?lesson_id=fractions")
        assert graph.status_code==200
        data=graph.json()
        assert {"from":"numerator_denominator","to":"unit_fraction","type":"prerequisite",
                "source":"curriculum_author"} in data["edges"]
        assert outsider.get(f"/api/teacher/classes/{classroom['id']}/learning-graph?lesson_id=fractions").status_code==404
        assert teacher.get(f"/api/teacher/classes/{classroom['id']}/learning-graph?lesson_id=unknown").status_code==404


def test_learning_path_proposal_requires_teacher_approval_before_assignment(tmp_path, monkeypatch):
    monkeypatch.setattr(main,"DB_PATH",tmp_path/"v24_approval.sqlite3")
    with TestClient(main.app) as teacher, TestClient(main.app) as student:
        teacher.post("/api/auth/register-teacher",json={"email":"approveowner@example.test",
            "password":"TeacherPass123!","display_name":"Owner"})
        classroom=teacher.post("/api/classes",json={"name":"Approval Class"}).json()
        student.post("/api/classes/join",json={"join_code":classroom["join_code"],
            "display_name":"Learner","email":"approvelearner@example.test","password":"StudentPass123!"})
        body={"class_id":classroom["id"],"lesson_id":"fractions","concept_id":"unit_fraction",
              "title":"Review unit fractions","description":"Practice with visual examples"}
        proposal=teacher.post("/api/teacher/learning-path-proposals",json=body)
        assert proposal.status_code==201
        proposal_id=proposal.json()["id"]
        assert proposal.json()["status"]=="pending"
        assert teacher.get("/api/teacher/assignments").json()["assignments"]==[]
        assert student.get("/api/student/assignments").json()["assignments"]==[]
        assert teacher.post("/api/teacher/learning-path-proposals",json={**body,"concept_id":"not-in-lesson"}).status_code==422
        approved=teacher.post(f"/api/teacher/learning-path-proposals/{proposal_id}/approve")
        assert approved.status_code==200
        assert approved.json()["status"]=="approved"
        assert len(student.get("/api/student/assignments").json()["assignments"])==1
        assert teacher.post(f"/api/teacher/learning-path-proposals/{proposal_id}/approve").status_code==409
        assert teacher.post(f"/api/teacher/learning-path-proposals/{proposal_id}/reject").status_code==409


def test_rejected_proposal_never_creates_assignment_and_other_teacher_cannot_review(tmp_path, monkeypatch):
    monkeypatch.setattr(main,"DB_PATH",tmp_path/"v24_reject.sqlite3")
    with TestClient(main.app) as owner, TestClient(main.app) as other:
        owner.post("/api/auth/register-teacher",json={"email":"rejectowner@example.test",
            "password":"TeacherPass123!","display_name":"Owner"})
        other.post("/api/auth/register-teacher",json={"email":"rejectother@example.test",
            "password":"TeacherPass123!","display_name":"Other"})
        classroom=owner.post("/api/classes",json={"name":"Reject Class"}).json()
        body={"class_id":classroom["id"],"lesson_id":"ratio","concept_id":"equivalent_ratio",
              "title":"Ratio practice","description":"Use equivalent ratios"}
        proposal=owner.post("/api/teacher/learning-path-proposals",json=body).json()
        assert other.post(f"/api/teacher/learning-path-proposals/{proposal['id']}/approve").status_code==404
        rejected=owner.post(f"/api/teacher/learning-path-proposals/{proposal['id']}/reject")
        assert rejected.status_code==200
        assert owner.get("/api/teacher/assignments").json()["assignments"]==[]



def test_learning_analytics_is_student_private_and_teacher_class_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "analytics.sqlite3")
    with TestClient(main.app) as teacher, TestClient(main.app) as student, TestClient(main.app) as other_teacher:
        assert teacher.post("/api/auth/register-teacher", json={
            "email": "analytics-teacher@example.test", "password": "StrongPass123!", "display_name": "Teacher"
        }).status_code == 201
        classroom = teacher.post("/api/classes", json={"name": "Analytics Class"})
        class_id = classroom.json()["id"]
        joined = student.post("/api/classes/join", json={
            "join_code": classroom.json()["join_code"], "display_name": "Learner",
            "email": "analytics-student@example.test", "password": "StudentPass123!"
        })
        assert joined.status_code == 201
        student_id = joined.json()["student"]["id"] if "student" in joined.json() else joined.json()["user"]["id"]

        with main.db() as con:
            con.execute(
                "INSERT INTO student_quizzes(id,student_id,lesson_id,questions_json,submitted_at,result_json) VALUES(?,?,?,?,CURRENT_TIMESTAMP,?)",
                ("quiz-analytics-1", student_id, "fractions", "[]", json.dumps({
                    "score": 1, "total": 2, "percentage": 50,
                    "details": [
                        {"question_id": "q1", "concept_id": "numerator_denominator", "correct": True},
                        {"question_id": "q2", "concept_id": "unit_fraction", "correct": False},
                    ],
                })),
            )
            con.execute(
                "INSERT INTO student_quizzes(id,student_id,lesson_id,questions_json,submitted_at,result_json) VALUES(?,?,?,?,?,?)",
                ("quiz-analytics-2", student_id, "fractions", "[]", "2026-11-20 10:00:00", json.dumps({
                    "score": 2, "total": 2, "percentage": 100,
                    "details": [
                        {"question_id": "q1", "concept_id": "numerator_denominator", "correct": True},
                        {"question_id": "q2", "concept_id": "unit_fraction", "correct": True},
                    ],
                })),
            )

        assert student.get("/api/student/learning-analytics").status_code == 200
        own = student.get("/api/student/learning-analytics").json()
        assert own["attempt_count"] == 2
        assert own["question_count"] == 4
        assert teacher.get(f"/api/teacher/classes/{class_id}/learning-analytics").status_code == 200
        class_report = teacher.get(f"/api/teacher/classes/{class_id}/learning-analytics").json()
        assert class_report["student_count"] == 1
        assert class_report["students"][0]["analytics"]["attempt_count"] == 2
        assert teacher.get(f"/api/teacher/students/{student_id}/learning-analytics?class_id={class_id}").status_code == 200

        assert other_teacher.post("/api/auth/register-teacher", json={
            "email": "other-analytics@example.test", "password": "StrongPass123!", "display_name": "Other"
        }).status_code == 201
        assert other_teacher.get(f"/api/teacher/classes/{class_id}/learning-analytics").status_code == 404
        assert other_teacher.get(f"/api/teacher/students/{student_id}/learning-analytics?class_id={class_id}").status_code == 404
