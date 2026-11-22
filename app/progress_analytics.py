"""Transparent longitudinal summaries of submitted formative quiz attempts.

Percentages describe recorded quiz attempts only. They are not grades, diagnoses,
mastery estimates, or evidence of causal learning improvement.
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any


def build_quiz_learning_analytics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    valid_attempts = 0
    for row in rows:
        lesson_id = str(row.get("lesson_id") or "")
        if not lesson_id:
            continue
        try:
            result = json.loads(row.get("result_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        details = result.get("details") if isinstance(result, dict) else None
        if not isinstance(details, list):
            continue
        valid_details = [
            item for item in details
            if isinstance(item, dict) and isinstance(item.get("concept_id"), str)
            and isinstance(item.get("correct"), bool)
        ]
        if not valid_details:
            continue
        grouped[lesson_id].append({
            "submitted_at": row.get("submitted_at"),
            "details": valid_details,
            "score": result.get("score"),
            "total": result.get("total"),
            "percentage": result.get("percentage"),
        })
        valid_attempts += 1

    lessons = []
    overall_correct = 0
    overall_questions = 0
    for lesson_id, attempts in sorted(grouped.items()):
        attempts.sort(key=lambda item: (item["submitted_at"] or ""))
        concept_history: dict[str, list[dict[str, Any]]] = defaultdict(list)
        timeline = []
        for index, attempt in enumerate(attempts, start=1):
            correct = sum(bool(detail["correct"]) for detail in attempt["details"])
            total = len(attempt["details"])
            overall_correct += correct
            overall_questions += total
            timeline.append({
                "attempt": index,
                "submitted_at": attempt["submitted_at"],
                "correct": correct,
                "total": total,
                "percentage": round(correct * 100 / total) if total else 0,
            })
            for detail in attempt["details"]:
                concept_history[detail["concept_id"]].append({
                    "submitted_at": attempt["submitted_at"],
                    "correct": detail["correct"],
                })

        concepts = []
        for concept_id, history in sorted(concept_history.items()):
            correct = sum(item["correct"] for item in history)
            first = history[0]["correct"]
            latest = history[-1]["correct"]
            concepts.append({
                "concept_id": concept_id,
                "attempts": len(history),
                "correct": correct,
                "incorrect": len(history) - correct,
                "accuracy_percentage": round(correct * 100 / len(history)),
                "first_recorded": first,
                "latest_recorded": latest,
                "change_between_first_and_latest": (
                    "same" if first == latest else "correct_after_incorrect" if latest
                    else "incorrect_after_correct"
                ),
                "history": history,
            })
        lessons.append({
            "lesson_id": lesson_id,
            "attempt_count": len(attempts),
            "timeline": timeline,
            "concepts": concepts,
        })

    return {
        "attempt_count": valid_attempts,
        "question_count": overall_questions,
        "overall_accuracy_percentage": (
            round(overall_correct * 100 / overall_questions) if overall_questions else None
        ),
        "lessons": lessons,
        "notice": "هذه ملخصات وصفية لمحاولات الاختبارات التدريبية المسجلة فقط. اختلاف الأسئلة، وعدد المحاولات، والتخمين قد يؤثر في النسب؛ لا تمثل درجات مدرسية أو تشخيصًا أو إثباتًا للإتقان أو التحسن السببي.",
    }
