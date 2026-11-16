from app.assessment import assess_explanation
from app.curriculum import get_lesson

def test_empty_explanation_is_conservative():
    report = assess_explanation([], get_lesson("fractions"))
    assert report["coverage_signal"] == 0
    assert report["label"] == "More explanation needed"

def test_explanation_evidence_signal():
    messages = [{"role": "student", "text": "النصف أكبر من الربع لأن تقسيم نفس الحجم إلى أربعة أجزاء يجعل كل جزء أصغر"}]
    report = assess_explanation(messages, get_lesson("fractions"))
    assert report["coverage_signal"] > 0
