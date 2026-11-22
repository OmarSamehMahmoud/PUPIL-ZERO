"""Private, account-scoped student companion helpers."""
from __future__ import annotations

import re
from typing import Any

LEARNING_STYLES = {
    "step_by_step": "اشرح على خطوات صغيرة، فكرة واحدة في كل رسالة، وتأكد من فهم الطالب قبل الانتقال.",
    "example_first": "ابدأ بمثال بسيط من الحياة اليومية، ثم اربطه بالفكرة الرياضية.",
    "quiz_me": "استخدم سؤالًا قصيرًا واحدًا في كل مرة، ولا تكشف الإجابة قبل محاولة الطالب.",
}


def companion_guidance(style: str) -> str:
    return (
        "أنت زميل تعلم داعم. لا تعطِ محاضرة طويلة؛ اجعل ردك قصيرًا ومشجعًا، "
        "واسأل سؤالًا واحدًا في كل مرة. لا تطلب أي بيانات شخصية، ولا تصدر أحكامًا "
        "على ذكاء الطالب أو مستواه. إذا ظهر خطر أو طلب غير مناسب، وجّه الطالب للمعلم أو ولي الأمر.\n"
        + LEARNING_STYLES.get(style, LEARNING_STYLES["step_by_step"])
    )


def redact_for_model(messages: list[dict[str, str]], private_values: list[str] | None = None) -> list[dict[str, str]]:
    """Keep original transcript locally; remove common identifiers before model calls."""
    private_values = [value.strip() for value in (private_values or []) if value and value.strip()]
    output = []
    for item in messages[-14:]:
        content = str(item.get("text", ""))
        content = re.sub(r"(?i)[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", "[بيانات شخصية محذوفة]", content)
        content = re.sub(r"(?<!\w)(?:\+?\d[\d\s().-]{8,}\d)(?!\w)", "[بيانات شخصية محذوفة]", content)
        for value in private_values:
            content = re.sub(re.escape(value), "[بيانات شخصية محذوفة]", content, flags=re.IGNORECASE)
        output.append({"role": item.get("role", "student"), "text": content})
    return output


def fallback_companion_reply(text: str, lesson_title: str, style: str) -> str:
    if len(text.strip()) < 8:
        return "ممكن تحكيلي أكتر؟ اكتب اللي فهمته حتى لو مش متأكد، ونفكر فيه سوا."
    if style == "example_first":
        return f"تعالى نبدأ بمثال من حياتنا مرتبط بـ{lesson_title}. إيه المثال اللي يخطر في بالك؟"
    if style == "quiz_me":
        return "جاهز لسؤال صغير؟ اشرحلي الفكرة بطريقتك الأول، وبعدها أقولك سؤال نجرّب بيه فهمنا."
    return "حلو إنك بتحاول! خلينا نقسم الفكرة لخطوات صغيرة. إيه أول خطوة شايف إنها مهمة؟"
