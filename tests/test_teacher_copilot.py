from app.curriculum import get_lesson
from app.teacher_copilot import build_teacher_copilot


def quiz_row(lesson_id, submitted_at, details):
    return {"lesson_id": lesson_id, "submitted_at": submitted_at, "result": {"details": details}}


def test_copilot_links_repeated_recorded_errors_to_authored_prerequisites():
    lesson = get_lesson("fractions")
    rows = [
        quiz_row("fractions", "2026-11-01", [
            {"question_id": "q1", "concept_id": "unit_fraction", "correct": False,
             "selected_option": "a", "correct_option": "b"},
        ]),
        quiz_row("fractions", "2026-11-02", [
            {"question_id": "q2", "concept_id": "unit_fraction", "correct": False,
             "selected_option": "a", "correct_option": "b"},
        ]),
    ]
    result = build_teacher_copilot(lesson, rows)
    assert len(result["suggestions"]) == 1
    suggestion = result["suggestions"][0]
    assert suggestion["concept_id"] == "unit_fraction"
    assert suggestion["evidence"]["incorrect_answers"] == 2
    assert suggestion["authored_prerequisites"] == [{
        "concept_id": "numerator_denominator", "concept": "البسط والمقام",
        "source": "curriculum_author",
    }]
    assert suggestion["requires_teacher_approval"] is True
    assert suggestion["suggested_activity"]["teacher_decision_required"] is True


def test_copilot_ignores_below_threshold_other_lessons_and_unknown_concepts():
    lesson = get_lesson("fractions")
    rows = [
        quiz_row("fractions", "2026-11-01", [
            {"concept_id": "unit_fraction", "correct": False},
            {"concept_id": "made_up", "correct": False},
        ]),
        quiz_row("decimals", "2026-11-02", [
            {"concept_id": "unit_fraction", "correct": False},
            {"concept_id": "unit_fraction", "correct": False},
        ]),
    ]
    result = build_teacher_copilot(lesson, rows)
    assert result["suggestions"] == []
    assert result["threshold"] == 2
    assert "لا يشخّص" in result["notice"]
