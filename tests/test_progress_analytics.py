import json

from app.progress_analytics import build_quiz_learning_analytics


def row(lesson, submitted, details, score=None):
    return {
        "lesson_id": lesson,
        "submitted_at": submitted,
        "result_json": json.dumps({
            "details": details,
            "score": score if score is not None else sum(x["correct"] for x in details),
            "total": len(details),
        }),
    }


def test_builds_chronological_attempt_and_concept_history():
    rows = [
        row("fractions", "2026-03-02 10:00:00", [
            {"concept_id": "equivalence", "correct": True},
            {"concept_id": "unit_fraction", "correct": False},
        ]),
        row("fractions", "2026-03-05 10:00:00", [
            {"concept_id": "equivalence", "correct": True},
            {"concept_id": "unit_fraction", "correct": True},
        ]),
    ]
    result = build_quiz_learning_analytics(rows)
    assert result["attempt_count"] == 2
    assert result["question_count"] == 4
    assert result["overall_accuracy_percentage"] == 75
    lesson = result["lessons"][0]
    assert [item["attempt"] for item in lesson["timeline"]] == [1, 2]
    concepts = {item["concept_id"]: item for item in lesson["concepts"]}
    assert concepts["unit_fraction"]["change_between_first_and_latest"] == "correct_after_incorrect"
    assert concepts["equivalence"]["accuracy_percentage"] == 100


def test_ignores_malformed_or_unusable_attempts():
    rows = [
        {"lesson_id": "fractions", "submitted_at": "2026-03-01", "result_json": "not-json"},
        {"lesson_id": "fractions", "submitted_at": "2026-03-02", "result_json": json.dumps({"details": []})},
        {"lesson_id": "", "submitted_at": "2026-03-03", "result_json": "{}"},
    ]
    result = build_quiz_learning_analytics(rows)
    assert result["attempt_count"] == 0
    assert result["question_count"] == 0
    assert result["overall_accuracy_percentage"] is None
    assert result["lessons"] == []


def test_separates_lessons_and_does_not_infer_mastery():
    rows = [
        row("decimals", "2026-04-01", [{"concept_id": "place_value", "correct": True}]),
        row("fractions", "2026-04-02", [{"concept_id": "numerator", "correct": False}]),
    ]
    result = build_quiz_learning_analytics(rows)
    assert {item["lesson_id"] for item in result["lessons"]} == {"decimals", "fractions"}
    assert "mastery" not in result
    assert "diagnosis" not in result
