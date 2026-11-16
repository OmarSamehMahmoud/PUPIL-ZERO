"""Evidence-grounded teacher review priorities for the local prototype."""
from __future__ import annotations

from typing import Any


def build_review_priorities(insights: dict[str, Any], minimum_sample: int = 5) -> dict[str, Any]:
    """Rank concepts for human review; never infer mastery or diagnose a misconception."""
    priorities: list[dict[str, Any]] = []
    for lesson in insights.get("lessons", []):
        session_count = int(lesson.get("session_count", 0))
        for concept in lesson.get("concepts", []):
            flagged = int(concept.get("sessions_flagged_for_review", 0))
            evidence = int(concept.get("sessions_with_keyword_evidence", 0))
            if flagged == 0:
                continue
            ratio = flagged / max(session_count, 1)
            if session_count < minimum_sample:
                level = "insufficient_sample"
                label = "عينة غير كافية"
            elif ratio >= 0.5:
                level = "high_review_signal"
                label = "أولوية مراجعة مرتفعة"
            else:
                level = "review_signal"
                label = "يُستحسن المراجعة"
            priorities.append({
                "lesson_id": lesson["lesson_id"],
                "lesson": lesson["lesson"],
                "concept_id": concept["concept_id"],
                "concept": concept["concept"],
                "sessions": session_count,
                "sessions_flagged_for_review": flagged,
                "sessions_with_keyword_evidence": evidence,
                "review_ratio": round(ratio, 3),
                "level": level,
                "label": label,
                "reason": f"ظهر كهدف للمراجعة في {flagged} من {session_count} جلسة.",
            })
    priorities.sort(
        key=lambda item: (
            item["level"] == "insufficient_sample",
            item["review_ratio"],
            item["sessions_flagged_for_review"],
        ),
        reverse=True,
    )
    return {
        "minimum_sample": minimum_sample,
        "priorities": priorities,
        "notice": (
            "هذه أولويات لمراجعة المعلم مبنية على علامات حوارية أولية، وليست تشخيصًا "
            "للتصورات الخاطئة أو قياسًا للإتقان. العينات الصغيرة لا تسمح باستنتاجات عامة."
        ),
    }
