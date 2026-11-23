"""Structured, lesson-grounded AI classroom debates and student judging."""
from __future__ import annotations

import json
from typing import Any

SPEAKERS = ("milo", "noura", "zizo")


def debate_guidance(lesson: dict[str, Any]) -> str:
    """Build a constrained prompt from repository-authored lesson material only."""
    lesson_data = {
        "title": lesson.get("title_ar", ""),
        "objectives": lesson.get("learning_objectives", []),
        "concepts": [
            {"id": item.get("id"), "name": item.get("label_ar"),
             "explanation": item.get("correction", "")}
            for item in lesson.get("concepts", [])
        ],
        "scenario": (lesson.get("scenarios") or [{}])[0].get("prompt_ar", ""),
    }
    return (
        "أنت منسق مناظرة تعليمية قصيرة بين ثلاثة زملاء. أخرج JSON فقط بالشكل "
        '{"arguments":[{"speaker":"milo","text":"..."},'
        '{"speaker":"noura","text":"..."},{"speaker":"zizo","text":"..."}],'
        '"judge_question":"..."} '
        "MILO يعرض حجة أولى واضحة مرتبطة بمفهوم من الدرس. "
        "NOURA تختبر الحجة بمثال يومي أو مثال من السيناريو المرفق دون إضافة حقائق جديدة. "
        "ZIZO يقدم اعتراضًا محترمًا أو حالة مضادة تساعد على فحص حدود الحجة، لا مجرد تكرارها. "
        "اكتب بعربية مصرية بسيطة ومناسبة للطلاب. كل مساهمة قصيرة من 1 إلى 3 جمل. "
        "لا تسخر ولا تصدر حكمًا على الطالب ولا تطلب بيانات شخصية. "
        "لا تخترع معلومات؛ محتوى الدرس أدناه هو مصدر الحقائق الوحيد. "
        "اختم بسؤال يطلب من الطالب اختيار الحجة الأكثر إقناعًا أو اختيار «لسه مش متأكد»، "
        "ثم شرح السبب بكلماته. لا تذكر إجابة صحيحة أو فائزًا. سياق الدرس: "
        + json.dumps(lesson_data, ensure_ascii=False)
    )


def validate_debate(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw.strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("Debate model did not return valid JSON") from exc
    rows = parsed.get("arguments") if isinstance(parsed, dict) else None
    if not isinstance(rows, list) or len(rows) != 3:
        raise ValueError("Debate must contain exactly three arguments")
    clean = []
    for index, speaker in enumerate(SPEAKERS):
        row = rows[index]
        if not isinstance(row, dict) or row.get("speaker") != speaker:
            raise ValueError("Debate speakers are missing or out of order")
        value = row.get("text")
        if not isinstance(value, str) or not 5 <= len(value.strip()) <= 700:
            raise ValueError("Debate argument failed validation")
        clean.append({"speaker": speaker, "text": value.strip()})
    question = parsed.get("judge_question")
    if not isinstance(question, str) or not 8 <= len(question.strip()) <= 400:
        raise ValueError("Debate judge question failed validation")
    return {"arguments": clean, "judge_question": question.strip()}


def authored_debate(lesson: dict[str, Any]) -> dict[str, Any]:
    """Transparent offline fallback based only on authored lesson text."""
    concepts = lesson.get("concepts", [])
    first = concepts[0] if concepts else {}
    second = concepts[1] if len(concepts) > 1 else first
    scenario = (lesson.get("scenarios") or [{}])[0].get("prompt_ar", "")
    explanation = first.get("correction") or lesson.get("title_ar", "فكرة الدرس")
    example = scenario or ("راجع مثالًا مرتبطًا بموضوع " + lesson.get("title_ar", "الدرس"))
    contrast = second.get("label_ar") or first.get("label_ar") or lesson.get("title_ar", "الفكرة")
    return {
        "arguments": [
            {"speaker": "milo", "text": "حجتي: " + explanation},
            {"speaker": "noura", "text": "خلينا نختبر الكلام بمثال من الدرس: " + example},
            {"speaker": "zizo", "text": "اعتراضي كسؤال للتفكير: هل تفضل نفس النتيجة لو فحصنا مفهوم «" + contrast + "» أو غيّرنا تفاصيل المثال؟"},
        ],
        "judge_question": "مين حجته أقنعتك أكتر: MILO أو NOURA أو ZIZO؟ وممكن تختار «لسه مش متأكد». اشرح السبب بكلماتك.",
    }


def build_judgment(winner: str, reason: str) -> dict[str, str]:
    if winner not in (*SPEAKERS, "undecided"):
        raise ValueError("Choose a valid debate position")
    clean_reason = reason.strip()
    if not 5 <= len(clean_reason) <= 1200:
        raise ValueError("Explain your choice in at least five characters")
    return {
        "winner": winner,
        "reason": clean_reason,
        "reflection": (
            "شكرًا إنك وضحت طريقة تفكيرك. قارن السبب اللي كتبته بتفاصيل الدرس، "
            "وفكّر هل في دليل أو مثال ممكن يغيّر رأيك. اختيارك مش درجة ولا تقييم لقدراتك."
        ),
    }
