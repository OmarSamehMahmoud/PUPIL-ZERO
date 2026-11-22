from app.student_companion import companion_guidance, fallback_companion_reply, redact_for_model


def test_companion_styles_have_distinct_guidance_and_fallbacks():
    assert "خطوات صغيرة" in companion_guidance("step_by_step")
    assert "مثال بسيط" in companion_guidance("example_first")
    assert "سؤالًا قصيرًا" in companion_guidance("quiz_me")
    assert "مثال" in fallback_companion_reply("عايز أفهم الدرس كويس", "الكسور", "example_first")
    assert "سؤال" in fallback_companion_reply("عايز أفهم الدرس كويس", "الكسور", "quiz_me")


def test_model_context_redacts_account_identifiers_and_common_contact_patterns():
    messages = [
        {"role": "student", "text": "أنا Private Learner وبريدي private@example.test ورقمي 01012345678"},
        {"role": "ai", "text": "أهلاً بيك"},
    ]
    safe = redact_for_model(messages, ["Private Learner"])
    joined = " ".join(item["text"] for item in safe)
    assert "Private Learner" not in joined
    assert "private@example.test" not in joined
    assert "01012345678" not in joined
    assert "[بيانات شخصية محذوفة]" in joined
    assert len(safe) == 2
