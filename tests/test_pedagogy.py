from app.curriculum import get_lesson
from app.pedagogy import advance_state, initial_state, state_context


def test_dialogue_starts_by_eliciting_student_explanation():
    state = initial_state(get_lesson("fractions"))
    assert state["stage"] == "elicit"
    assert state["scenario_index"] == 0


def test_two_distinct_evidence_phrases_move_to_transfer():
    lesson = get_lesson("fractions")
    state = initial_state(lesson)
    state = advance_state(state, "نفس الحجم", lesson)
    assert state["stage"] == "clarify"
    state = advance_state(state, "القطعة أصغر", lesson)
    assert state["stage"] == "transfer"
    assert state["scenario_index"] == 1


def test_two_low_evidence_attempts_record_review_target():
    lesson = get_lesson("fractions")
    state = initial_state(lesson)
    state = advance_state(state, "مش عارف", lesson)
    state = advance_state(state, "مش فاهم السؤال", lesson)
    assert "unit_fraction" in state["review_targets"]
    assert state["scenario_index"] == 1


def test_reflection_context_does_not_claim_mastery():
    lesson = get_lesson("fractions")
    state = initial_state(lesson)
    state["stage"] = "reflect"
    prompt = state_context(state, lesson)
    assert "لا تمنحه درجة" in prompt
    assert "الإتقان" in prompt
