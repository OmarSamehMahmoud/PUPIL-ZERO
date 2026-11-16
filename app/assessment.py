"""Transparent, explainable formative assessment for the MVP."""
from __future__ import annotations

import re
from typing import Any


def normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[ًٌٍَُِّْـ]", "", text)
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي")
    return re.sub(r"[^\w\s]", " ", text)


def assess_explanation(messages: list[dict[str, str]], lesson: dict[str, Any]) -> dict[str, Any]:
    student_text = " ".join(m.get("text", "") for m in messages if m.get("role") == "student")
    normalized = normalize(student_text)
    concepts = []
    for concept in lesson["concepts"]:
        evidence = [
            term for term in concept.get("evidence_terms", [])
            if normalize(term) in normalized
        ]
        concepts.append({
            "concept_id": concept["id"],
            "concept": concept["label_ar"],
            "status": "evidence_found" if evidence else "not_enough_evidence",
            "evidence_terms": evidence,
            "note": "Keyword evidence is only a signal; teacher review is required.",
        })

    covered_scenarios = []
    for index, scenario in enumerate(lesson["scenarios"], start=1):
        evidence = [term for term in scenario["expected"] if normalize(term) in normalized]
        if evidence:
            covered_scenarios.append({"scenario": index, "evidence_terms": evidence})

    coverage = round(100 * len(covered_scenarios) / max(1, len(lesson["scenarios"])))
    return {
        "coverage_signal": coverage,
        "label": "Promising evidence" if coverage >= 67 else "More explanation needed",
        "concepts": concepts,
        "scenario_evidence": covered_scenarios,
        "limitations": [
            "This is a prototype keyword signal, not a validated measure of learning.",
            "Arabic dialect, spelling, and speech transcription can affect keyword matching.",
            "A teacher should review the transcript and evidence before interpreting results.",
        ],
        "next_step": "Ask the learner to explain the idea using a new real-life example.",
    }
