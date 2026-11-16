from app.curriculum import get_lesson
from app.llm import _history_messages, build_system_prompt


def test_system_prompt_keeps_student_as_teacher():
    prompt = build_system_prompt(get_lesson("fractions"), "milo")
    assert "تحدث بعربية مصرية بسيطة" in prompt
    assert "لا تسخر منه" in prompt
    assert "فهم الكسور" in prompt


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


def test_history_is_limited_to_recent_turns():
    transcript = [{"role": "student", "text": str(i)} for i in range(20)]
    messages = _history_messages(transcript, "system")
    assert len(messages) == 15
    assert messages[1]["content"] == "6"
