"""Evidence-grounded, deterministic teacher copilot suggestions.

This module aggregates formative quiz evidence without student identifiers and
connects reviewed concepts to explicitly authored curriculum prerequisites.
It never diagnoses a learner or estimates mastery.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.intervention_planner import build_intervention_plan


def build_teacher_copilot(lesson: dict[str, Any], quiz_rows: list[dict[str, Any]],
                          minimum_incorrect: int = 2) -> dict[str, Any]:
    concepts = {item["id"]: item for item in lesson.get("concepts", [])}
    counts: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"attempts": 0, "incorrect": 0, "correct": 0, "evidence": []}
    )
    for row in quiz_rows:
        if row.get("lesson_id") != lesson.get("id"):
            continue
        result = row.get("result")
        if not isinstance(result, dict) or not isinstance(result.get("details"), list):
            continue
        for detail in result["details"]:
            if not isinstance(detail, dict):
                continue
            concept_id = detail.get("concept_id")
            if concept_id not in concepts or not isinstance(detail.get("correct"), bool):
                continue
            bucket = counts[concept_id]
            bucket["attempts"] += 1
            bucket["correct"] += int(detail["correct"])
            bucket["incorrect"] += int(not detail["correct"])
            if not detail["correct"] and len(bucket["evidence"]) < 8:
                bucket["evidence"].append({
                    "question_id": str(detail.get("question_id") or "unknown"),
                    "submitted_at": row.get("submitted_at"),
                    "selected_option": detail.get("selected_option"),
                    "correct_option": detail.get("correct_option"),
                    "evidence_type": "recorded_incorrect_quiz_response",
                })

    suggestions = []
    for concept_id, stats in counts.items():
        if stats["incorrect"] < minimum_incorrect:
            continue
        concept = concepts[concept_id]
        prerequisites = [
            {"concept_id": prerequisite, "concept": concepts[prerequisite]["label_ar"],
             "source": "curriculum_author"}
            for prerequisite in concept.get("prerequisites", [])
            if prerequisite in concepts
        ]
        plan = build_intervention_plan(lesson, concept_id)
        suggestions.append({
            "lesson_id": lesson["id"],
            "lesson": lesson["title_ar"],
            "concept_id": concept_id,
            "concept": concept["label_ar"],
            "evidence": {
                "incorrect_answers": stats["incorrect"],
                "correct_answers": stats["correct"],
                "recorded_answers": stats["attempts"],
                "minimum_threshold": minimum_incorrect,
                "sample_note": "إشارات مجمّعة من إجابات الاختبارات المسجلة؛ ليست تشخيصًا فرديًا.",
                "examples": stats["evidence"],
            },
            "authored_prerequisites": prerequisites,
            "suggested_review_focus": concept.get("correction", ""),
            "suggested_activity": plan,
            "proposal_title": "مراجعة: " + concept["label_ar"],
            "proposal_description": (
                "اقتراح مراجعة مبني على " + str(stats["incorrect"]) +
                " إجابة غير صحيحة مسجلة من " + str(stats["attempts"]) +
                " إجابة على المفهوم. المتطلبات السابقة المعروضة مأخوذة من خريطة المنهج المؤلفة. "
                "راجع الأدلة والنشاط وعدّله قبل الاعتماد."
            ),
            "requires_teacher_approval": True,
        })
    suggestions.sort(key=lambda item: (-item["evidence"]["incorrect_answers"], item["concept"]))
    return {
        "lesson_id": lesson["id"],
        "lesson": lesson["title_ar"],
        "suggestions": suggestions,
        "threshold": minimum_incorrect,
        "source": "recorded_formative_quiz_answers+authored_curriculum_prerequisites",
        "notice": (
            "مساعد مراجعة قائم على قواعد واضحة: يعرض عدد الإجابات غير الصحيحة المسجلة "
            "ويربط المفهوم بمتطلباته السابقة المؤلفة. لا يحدد سبب الخطأ، ولا يشخّص طالبًا، "
            "ولا يقيس الإتقان. راجع نصوص الأسئلة وإجاباتها قبل أي قرار."
        ),
    }
