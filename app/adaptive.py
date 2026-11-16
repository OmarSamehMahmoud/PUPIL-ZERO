"""Deterministic scenario adaptation using prior teacher-review signals.

This is transparent routing logic, not a validated learner model.
"""
from __future__ import annotations

from typing import Any


def choose_start_scenario(
    lesson: dict[str, Any], review_targets: list[str] | None = None
) -> tuple[int, str | None]:
    """Prefer an authored scenario for a previously flagged concept."""
    scenarios = lesson.get("scenarios", [])
    if not scenarios:
        return 0, None
    targets = list(dict.fromkeys(review_targets or []))
    for target in targets:
        for index, scenario in enumerate(scenarios):
            if scenario.get("target") == target:
                return index, target
    return 0, None


def adaptation_summary(target: str | None, lesson: dict[str, Any]) -> dict[str, str]:
    if not target:
        return {
            "mode": "standard",
            "reason": "نبدأ بالسيناريو التمهيدي الموجود في الدرس.",
        }
    concept = next(
        (item for item in lesson.get("concepts", []) if item.get("id") == target),
        None,
    )
    label = concept.get("label_ar", target) if concept else target
    return {
        "mode": "review_focus",
        "reason": f"بدأنا بسيناريو إضافي عن «{label}» لأنه ظهر كهدف للمراجعة في حصة سابقة.",
    }
