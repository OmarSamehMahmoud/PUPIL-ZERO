from app.teacher_intelligence import build_review_priorities


def test_priority_marks_small_samples_as_insufficient():
    result = build_review_priorities({
        "lessons": [{
            "lesson_id": "fractions", "lesson": "الكسور", "session_count": 2,
            "concepts": [{
                "concept_id": "unit_fraction", "concept": "الكسور الوحدة",
                "sessions_flagged_for_review": 1,
                "sessions_with_keyword_evidence": 1,
            }],
        }]
    })
    item = result["priorities"][0]
    assert item["level"] == "insufficient_sample"
    assert item["review_ratio"] == 0.5
    assert "ليست تشخيصًا" in result["notice"]


def test_priority_ranks_repeated_review_signals():
    result = build_review_priorities({
        "lessons": [{
            "lesson_id": "decimals", "lesson": "الأعداد العشرية", "session_count": 6,
            "concepts": [
                {"concept_id": "place", "concept": "القيمة المكانية",
                 "sessions_flagged_for_review": 4, "sessions_with_keyword_evidence": 2},
                {"concept_id": "compare", "concept": "المقارنة",
                 "sessions_flagged_for_review": 1, "sessions_with_keyword_evidence": 5},
            ],
        }]
    })
    assert result["priorities"][0]["concept_id"] == "place"
    assert result["priorities"][0]["level"] == "high_review_signal"
    assert result["priorities"][1]["level"] == "review_signal"


def test_empty_insights_returns_no_priorities():
    assert build_review_priorities({"lessons": []})["priorities"] == []
