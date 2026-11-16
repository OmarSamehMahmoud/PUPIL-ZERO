from app.curriculum import get_lesson
from app.intervention_planner import build_intervention_plan

def test_plan_uses_authored_scenarios_and_teacher_review():
    lesson = get_lesson("fractions")
    plan = build_intervention_plan(lesson, "unit_fraction")
    assert plan is not None
    assert plan["concept"] == "الكسور الوحدة"
    assert plan["steps"][0]["activity"] == lesson["scenarios"][0]["prompt_ar"]
    assert plan["steps"][1]["activity"] == lesson["concepts"][1]["correction"]
    assert plan["teacher_decision_required"] is True
    assert len(plan["steps"]) == 4
    assert plan["total_minutes"] == 15

def test_unknown_concept_has_no_plan():
    assert build_intervention_plan(get_lesson("ratio"), "unknown") is None