from app.llm import _history_messages, build_system_prompt
from app.curriculum import get_lesson


def test_system_prompt_keeps_student_as_teacher():
    prompt = build_system_prompt(get_lesson("fractions"))
    assert "human student is the teacher" in prompt
    assert "natural, friendly Egyptian Arabic" in prompt
    assert "Never shame" in prompt


def test_history_maps_roles_and_limits_context():
    transcript = [
        {"role": "ai", "text": "سؤال افتتاحي"},
        {"role": "student", "text": "النصف أكبر"},
        {"role": "ai", "text": "ليه؟"},
    ]
    messages = _history_messages(transcript, "system")
    assert messages == [
        {"role": "system", "content": "system"},
        {"role": "assistant", "content": "سؤال افتتاحي"},
        {"role": "user", "content": "النصف أكبر"},
        {"role": "assistant", "content": "ليه؟"},
    ]
