from app.assessment import assess_explanation
from app.curriculum import get_lesson
from app.llm import build_system_prompt


def test_empty_explanation_is_conservative():
    report = assess_explanation([], get_lesson("fractions"))
    assert report["coverage_signal"] == 0
    assert report["label"] == "More explanation needed"


def test_explanation_evidence_signal():
    messages = [{"role": "student", "text": "النصف أكبر من الربع لأن تقسيم نفس الحجم إلى أربعة أجزاء يجعل كل جزء أصغر"}]
    report = assess_explanation(messages, get_lesson("fractions"))
    assert report["coverage_signal"] > 0
    assert report["concepts"][1]["status"] == "evidence_found"


def test_system_prompt_uses_safe_student_persona_and_lesson_context():
    prompt = build_system_prompt(get_lesson("fractions"), "milo")
    assert "لا تطلب اسم الطالب" in prompt
    assert "فهم الكسور" in prompt
    assert "MILO" in prompt
