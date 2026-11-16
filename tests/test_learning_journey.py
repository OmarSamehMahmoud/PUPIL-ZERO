from app.learning_journey import build_learning_journey


def test_journey_tracks_recurring_evidence_across_sessions():
    records = [
        {"session_id": "a", "created_at": "2026-01-01", "lesson_id": "fractions",
         "lesson": "الكسور", "report": {"concepts": [
             {"concept_id": "unit", "concept": "الكسور الوحدة", "status": "evidence_found"}]}},
        {"session_id": "b", "created_at": "2026-01-02", "lesson_id": "fractions",
         "lesson": "الكسور", "report": {"concepts": [
             {"concept_id": "unit", "concept": "الكسور الوحدة", "status": "evidence_found"}]}},
    ]
    result = build_learning_journey(records)
    assert result["session_count"] == 2
    assert result["concepts"][0]["signal"] == "recurring_evidence"
    assert result["concepts"][0]["sessions_with_evidence"] == 2
    assert [item["session_id"] for item in result["timeline"]] == ["a", "b"]
    assert "ليس قياسًا" in result["notice"]


def test_journey_does_not_claim_evidence_when_absent():
    result = build_learning_journey([{
        "session_id": "a", "created_at": "2026-01-01",
        "report": {"concepts": [
            {"concept_id": "ratio", "concept": "النسبة", "status": "not_enough_evidence"}]},
    }])
    assert result["concepts"][0]["signal"] == "not_yet_observed"
    assert result["concepts"][0]["sessions_with_evidence"] == 0


def test_empty_journey_is_valid():
    result = build_learning_journey([])
    assert result["session_count"] == 0
    assert result["concepts"] == []
    assert result["timeline"] == []
