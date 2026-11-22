"""Grounded multi-classmate classroom simulation orchestration."""
from __future__ import annotations

import json
from typing import Any

CLASSMATES = {
    "milo": {
        "name": "MILO",
        "role": "المستكشف الفضولي",
        "instruction": "اطرح سؤالًا استكشافيًا يساعدنا نفهم الفكرة من الأساس.",
    },
    "noura": {
        "name": "NOURA",
        "role": "صانعة الأمثلة",
        "instruction": "قدّم مثالًا حياتيًا بسيطًا مرتبطًا فقط بمعلومات الدرس.",
    },
    "zizo": {
        "name": "ZIZO",
        "role": "محب التحديات",
        "instruction": "اقترح تحديًا صغيرًا اختياريًا، من غير كشف إجابته.",
    },
}


def classroom_guidance(lesson: dict[str, Any]) -> str:
    """Ask one local-model call for a structured, lesson-grounded roundtable."""
    lesson_data = {
        "title": lesson.get("title_ar", ""),
        "objectives": lesson.get("learning_objectives", []),
        "concepts": [
            {"id": item.get("id"), "name": item.get("label_ar"),
             "explanation": item.get("correction", "")}
            for item in lesson.get("concepts", [])
        ],
    }
    return (
        "أنت منسق فصل افتراضي يضم ثلاثة زملاء تعلم: MILO وNOURA وZIZO. "
        "حوّل آخر رسالة من الطالب إلى نقاش قصير بينهم. أخرج JSON فقط بالشكل "
        '{"contributions":[{"speaker":"milo","text":"..."},'
        '{"speaker":"noura","text":"..."},{"speaker":"zizo","text":"..."}],'
        '"teacher_question":"..."} '
        "يجب أن تظهر الشخصيات الثلاث مرة واحدة بالترتيب المحدد. "
        "MILO: " + CLASSMATES["milo"]["instruction"] + " "
        "NOURA: " + CLASSMATES["noura"]["instruction"] + " "
        "ZIZO: " + CLASSMATES["zizo"]["instruction"] + " "
        "اكتب بعربية مصرية بسيطة ومناسبة للطلاب. لا تسخر ولا تصدر أحكامًا عن قدرات الطالب. "
        "لا تطلب بيانات شخصية. استخدم معلومات الدرس فقط ولا تخترع حقائق أو إجابات. "
        "السؤال الختامي سؤال واحد يوجهه الفصل للطالب. اجعل كل مساهمة قصيرة. "
        "إذا كانت رسالة الطالب خارج الدرس، اطلب منه بلطف العودة لموضوع الدرس. "
        "سياق الدرس الأصلي (مصدر الحقائق الوحيد): " +
        json.dumps(lesson_data, ensure_ascii=False)
    )


def validate_roundtable(raw: str) -> dict[str, Any]:
    """Reject malformed model output instead of showing untrusted structure."""
    try:
        parsed = json.loads(raw.strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("Classroom model did not return valid JSON") from exc
    rows = parsed.get("contributions") if isinstance(parsed, dict) else None
    if not isinstance(rows, list) or len(rows) != 3:
        raise ValueError("Classroom response must contain three contributions")
    expected = ["milo", "noura", "zizo"]
    clean = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or row.get("speaker") != expected[index]:
            raise ValueError("Classroom response has an invalid speaker order")
        value = row.get("text")
        if not isinstance(value, str) or not 5 <= len(value.strip()) <= 500:
            raise ValueError("Classroom contribution failed validation")
        clean.append({"speaker": expected[index], "text": value.strip()})
    question = parsed.get("teacher_question")
    if not isinstance(question, str) or not 5 <= len(question.strip()) <= 300:
        raise ValueError("Classroom follow-up question failed validation")
    return {"contributions": clean, "teacher_question": question.strip()}


def authored_roundtable(student_text: str, lesson: dict[str, Any]) -> dict[str, Any]:
    """Transparent deterministic fallback; does not pretend to be generated AI."""
    title = lesson.get("title_ar", "الدرس")
    concepts = lesson.get("concepts", [])
    first = concepts[0].get("label_ar", title) if concepts else title
    second = concepts[1].get("label_ar", first) if len(concepts) > 1 else first
    return {
        "contributions": [
            {"speaker": "milo", "text": f"خلينا نفكر في سؤالك عن {title}. إيه الفكرة الأساسية اللي محتاجين نفهمها الأول؟"},
            {"speaker": "noura", "text": f"ممكن نبدأ بمثال بسيط ونربطه بفكرة {first}. إيه مثال من حياتنا يساعدنا؟"},
            {"speaker": "zizo", "text": f"عندي تحدي اختياري: جرّب تشرح الفرق بين {first} و{second} بكلماتك."},
        ],
        "teacher_question": "الفصل كله بيسألك: تحب تبدأ بشرح فكرتك، ولا نحل مثال مع بعض؟",
    }


def format_roundtable(roundtable: dict[str, Any]) -> str:
    lines = [
        f"{CLASSMATES[item['speaker']]['name']}: {item['text']}"
        for item in roundtable["contributions"]
    ]
    lines.append("سؤال الفصل: " + roundtable["teacher_question"])
    return "\n\n".join(lines)
