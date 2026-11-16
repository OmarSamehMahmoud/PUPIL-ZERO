"""Teacher-reviewed intervention planning from authored lesson content."""
from __future__ import annotations
from typing import Any

def build_intervention_plan(lesson: dict[str, Any], concept_id: str) -> dict[str, Any] | None:
    concept = next((item for item in lesson.get("concepts", []) if item.get("id") == concept_id), None)
    if not concept:
        return None
    scenarios = [item for item in lesson.get("scenarios", []) if item.get("target") == concept_id]
    diagnostic = scenarios[0]["prompt_ar"] if scenarios else f"اسأل الطالب: ماذا تعرف عن {concept['label_ar']}؟ اشرح فكرتك بمثال."
    practice = scenarios[1]["prompt_ar"] if len(scenarios) > 1 else f"اطلب من الطالب ابتكار مثال جديد يوضح {concept['label_ar']} وشرح خطواته."
    return {
        "lesson_id": lesson["id"], "lesson": lesson["title_ar"],
        "concept_id": concept_id, "concept": concept["label_ar"],
        "learning_focus": concept.get("correction", ""),
        "observed_idea_to_explore": concept.get("misconception", ""),
        "steps": [
            {"stage": "استكشاف الفهم", "duration_minutes": 3, "activity": diagnostic, "teacher_action": "استمع لتفسير الطالب أولًا، واطلب منه توضيح السبب دون تصحيح فوري."},
            {"stage": "إعادة الشرح", "duration_minutes": 5, "activity": concept.get("correction", ""), "teacher_action": "استخدم رسمًا أو مثالًا محسوسًا، ثم اطلب من الطالب إعادة الشرح بكلماته."},
            {"stage": "تدريب وتطبيق", "duration_minutes": 5, "activity": practice, "teacher_action": "دع الطالب يحل أو يشرح بنفسه، ثم ناقش طريقة التفكير لا مجرد الإجابة."},
            {"stage": "تحقق ختامي", "duration_minutes": 2, "activity": f"اطلب من الطالب إنشاء مثال مختلف على {concept['label_ar']} وشرح لماذا يدعم فكرته.", "teacher_action": "سجّل ملاحظتك البشرية وحدد إن كان يلزم نشاط آخر؛ لا تعتمد على مطابقة الكلمات وحدها."},
        ],
        "total_minutes": 15, "teacher_decision_required": True,
        "notice": "خطة مقترحة مبنية على محتوى الدرس التجريبي وإشارات أولية. راجع ملاءمتها للطالب وعدّلها قبل الاستخدام؛ ليست تشخيصًا أو قرارًا آليًا.",
    }