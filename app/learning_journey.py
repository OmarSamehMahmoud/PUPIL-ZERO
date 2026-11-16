"""Longitudinal, explainable learning evidence for an anonymous learner key."""
from __future__ import annotations

from typing import Any


def build_learning_journey(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare per-session keyword signals; never label a learner as mastered."""
    ordered = sorted(records, key=lambda item: (item.get("created_at") or "", item.get("session_id") or ""))
    concepts: dict[str, dict[str, Any]] = {}
    timeline = []
    for record in ordered:
        report = record.get("report") or {}
        found = []
        for item in report.get("concepts", []):
            key = item.get("concept_id", "")
            if not key:
                continue
            entry = concepts.setdefault(key, {
                "concept_id": key, "concept": item.get("concept", key),
                "sessions_observed": 0, "sessions_with_evidence": 0,
                "first_evidence_at": None, "latest_evidence_at": None,
            })
            entry["sessions_observed"] += 1
            if item.get("status") == "evidence_found":
                entry["sessions_with_evidence"] += 1
                found.append(key)
                stamp = record.get("created_at")
                if entry["first_evidence_at"] is None:
                    entry["first_evidence_at"] = stamp
                entry["latest_evidence_at"] = stamp
        timeline.append({
            "session_id": record.get("session_id"),
            "created_at": record.get("created_at"),
            "lesson_id": record.get("lesson_id"),
            "lesson": record.get("lesson"),
            "evidence_concepts": found,
        })
    summary = []
    for entry in concepts.values():
        count = entry["sessions_with_evidence"]
        entry["signal"] = "recurring_evidence" if count >= 2 else (
            "single_observation" if count == 1 else "not_yet_observed"
        )
        summary.append(entry)
    summary.sort(key=lambda item: item["concept"])
    return {
        "session_count": len(ordered),
        "concepts": summary,
        "timeline": timeline,
        "notice": (
            "هذا سجل زمني لإشارات مطابقة كلمات في الشرح، وليس قياسًا مُعتمدًا للتعلم أو الإتقان. "
            "ظهور الدليل في جلسات متعددة لا يثبت الاحتفاظ طويل المدى؛ راجع إجابات الطالب وسياقها."
        ),
    }
