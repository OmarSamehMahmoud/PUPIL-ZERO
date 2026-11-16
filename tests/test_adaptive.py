from app.adaptive import adaptation_summary, choose_start_scenario
from app.curriculum import get_lesson
from app.pedagogy import initial_state, state_context


def test_prior_review_target_selects_matching_authored_scenario():
    lesson = get_lesson("fractions")
    index, target = choose_start_scenario(lesson, ["equivalence"])
    assert index == 2
    assert target == "equivalence"
    assert lesson["scenarios"][index]["target"] == target


def test_unknown_or_empty_review_targets_use_introductory_scenario():
    lesson = get_lesson("decimals")
    assert choose_start_scenario(lesson, ["not-a-concept"]) == (0, None)
    assert choose_start_scenario({"scenarios": []}, ["anything"]) == (0, None)


def test_initial_state_carries_adaptation_context():
    lesson = get_lesson("fractions")
    state = initial_state(lesson, ["unit_fraction"])
    assert state["scenario_index"] == 0
    assert state["adaptation_target"] == "unit_fraction"
    assert "هدف مراجعة سابق" in state_context(state, lesson)


def test_adaptation_summary_explains_reason_without_claiming_mastery():
    lesson = get_lesson("fractions")
    result = adaptation_summary("equivalence", lesson)
    assert result["mode"] == "review_focus"
    assert "الكسور المتكافئة" in result["reason"]
    assert adaptation_summary(None, lesson)["mode"] == "standard"
