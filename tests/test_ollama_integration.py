"""Opt-in end-to-end test against a real local Ollama model.

Run after starting Ollama and pulling the configured model:
PUPIL_LIVE_OLLAMA_TEST=1 python -m pytest tests/test_ollama_integration.py -q
"""
import asyncio
import os

import pytest

from app.curriculum import get_lesson
from app.llm import generate_open_response_analysis, provider_settings


@pytest.mark.skipif(os.getenv("PUPIL_LIVE_OLLAMA_TEST") != "1",
                    reason="Set PUPIL_LIVE_OLLAMA_TEST=1 to call a real local Ollama server")
def test_real_ollama_open_response_returns_lesson_scoped_verifiable_evidence():
    cfg = provider_settings()
    if cfg["provider"] != "ollama" or not cfg["model"]:
        pytest.skip("Configure PUPIL_LLM_PROVIDER=ollama and PUPIL_LLM_MODEL")
    lesson = get_lesson("fractions")
    answer = "البسط هو عدد الأجزاء اللي بناخدها والمقام عدد الأجزاء المتساوية في الكل."
    result = asyncio.run(generate_open_response_analysis(lesson, answer))
    expected = {concept["id"] for concept in lesson["concepts"]}
    assert {item["concept_id"] for item in result} == expected
    assert all(not item["evidence_quote"] or item["evidence_quote"] in answer for item in result)
