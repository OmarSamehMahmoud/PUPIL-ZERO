"""Adaptive dialogue state controller for PUPIL ZERO.

This is a transparent dialogue scaffold, not a validated mastery classifier.
"""
from __future__ import annotations
from typing import Any
from app.assessment import normalize
from app.adaptive import choose_start_scenario

STAGES = {
    "elicit": "اطلب من الطالب شرح فكرته بكلماته. لا تكشف الإجابة.",
    "clarify": "اطلب توضيح خطوة واحدة أو مثالًا صغيرًا دون إعطاء الحل.",
    "transfer": "اطلب تطبيق الفكرة في موقف جديد.",
    "reflect": "اطلب تلخيص الفكرة وما الذي أصبح أوضح.",
}


def initial_state(
    lesson: dict[str, Any], review_targets: list[str] | None = None
) -> dict[str, Any]:
    index, priority_target = choose_start_scenario(lesson, review_targets)
    return {
        "stage": "elicit",
        "scenario_index": index,
        "attempts_on_scenario": 0,
        "evidence_terms": [],
        "review_targets": [],
        "turns": 0,
        "adaptation_target": priority_target,
    }


def advance_state(state: dict[str, Any], student_text: str, lesson: dict[str, Any]) -> dict[str, Any]:
    current = dict(state or initial_state(lesson))
    scenarios = lesson.get("scenarios", [])
    if not scenarios:
        current["stage"] = "reflect"
        return current
    if current.get("stage") == "reflect":
        current["turns"] = int(current.get("turns", 0)) + 1
        return current
    index = min(int(current.get("scenario_index", 0)), len(scenarios)-1)
    scenario = scenarios[index]
    normalized = normalize(student_text)
    hits = [term for term in scenario.get("expected", []) if normalize(term) and normalize(term) in normalized]
    current["turns"] = int(current.get("turns",0))+1
    current["attempts_on_scenario"] = int(current.get("attempts_on_scenario",0))+1
    current["evidence_terms"] = list(dict.fromkeys(current.get("evidence_terms",[])+hits))
    if len(current["evidence_terms"]) >= 2:
        current["scenario_index"] = index+1
        current["attempts_on_scenario"] = 0
        current["evidence_terms"] = []
        current["stage"] = "transfer" if index+1 < len(scenarios) else "reflect"
    elif current["attempts_on_scenario"] >= 2:
        target = scenario.get("target")
        if target and target not in current["review_targets"]:
            current["review_targets"].append(target)
        current["scenario_index"] = index+1
        current["attempts_on_scenario"] = 0
        current["evidence_terms"] = []
        current["stage"] = "clarify" if index+1 < len(scenarios) else "reflect"
    else:
        current["stage"] = "clarify"
    return current


def state_context(state: dict[str, Any], lesson: dict[str, Any]) -> str:
    scenarios = lesson.get("scenarios", [])
    index = int(state.get("scenario_index",0))
    if index >= len(scenarios) or state.get("stage") == "reflect":
        return "مرحلة التأمل الختامي: اطلب تلخيص الفكرة أو ذكر شيء أصبح أوضح. لا تمنح درجة ولا تدّعِ الإتقان."
    scenario = scenarios[index]
    target = scenario.get("target","")
    concept = next((item for item in lesson.get("concepts",[]) if item.get("id")==target),{})
    stage = state.get("stage","elicit")
    adaptation = ""
    if state.get("adaptation_target"):
        adaptation = "هذا السيناريو اختير للتركيز على هدف مراجعة سابق؛ تعامل معه بلطف ولا تفترض وجود خطأ.\n"
    return (f"مرحلة الحوار: {stage}. {STAGES.get(stage,STAGES['elicit'])}\n"
            f"{adaptation}"
            f"المفهوم: {concept.get('label_ar',target)}. التصور البديل للاستكشاف: {concept.get('misconception','غير محدد')}.\n"
            "اسأل سؤالًا واحدًا فقط. لا تقل للطالب إن النظام اكتشف خطأه. مطابقة الكلمات ليست دليل إتقان.")
