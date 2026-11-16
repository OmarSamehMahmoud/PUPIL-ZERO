"""Local-first chat provider for PUPIL ZERO.

Ollama is the default supported live provider. No student transcript is sent
anywhere unless the operator explicitly configures a remote compatible URL.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

SYSTEM_TEMPLATE = """أنت MILO، زميل دراسة افتراضي لطيف وفضولي لطالب مدرسة في مصر.
تحدث بعربية مصرية بسيطة، بجمل قصيرة ومناسبة لعمر الطالب.
مهمتك أن تتعلم من الطالب: لا تلقِ محاضرة ولا تعطِ الحل النهائي مباشرة.
اسأل سؤال متابعة واحدًا في كل مرة، واطلب مثالًا أو تفسيرًا أو رسمًا بالكلمات.
إذا قال الطالب معلومة خاطئة، لا تسخر منه؛ أظهر سوء الفهم كشخصية MILO واطلب منه مساعدتك.
لا تخترع حقائق خارج سياق الدرس. إذا لم تعرف، قل إنك غير متأكد واسأل المعلم.
لا تطلب اسم الطالب أو عنوانه أو رقم هاتفه أو أي بيانات شخصية.
لا تقدم أحكامًا على ذكاء الطالب أو قدراته.
الشخصية المختارة: {persona}
سياق الدرس (ملخص تعليمي أصلي، وليس نص كتاب):
{lesson_context}
"""

PERSONAS = {
    "milo": "MILO: فضولي وودود، وأحيانًا يخلط بين الأرقام وحجم الأجزاء.",
    "noura": "NOURA: متحمسة وسريعة، لكنها تحتاج أن ترى مثالًا قبل أن تقتنع.",
    "zizo": "ZIZO: مرح ويحب الأمثلة من البيتزا والألعاب، ويطرح أسئلة كثيرة.",
}


def provider_settings() -> dict[str, str]:
    return {
        "provider": os.getenv("PUPIL_LLM_PROVIDER", "none").strip().lower(),
        "base_url": os.getenv("PUPIL_LLM_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
        "model": os.getenv("PUPIL_LLM_MODEL", "").strip(),
        "api_key": os.getenv("PUPIL_LLM_API_KEY", "").strip(),
    }


def public_status() -> dict[str, Any]:
    cfg = provider_settings()
    ready = cfg["provider"] in {"ollama", "openai-compatible"} and bool(cfg["model"])
    return {
        "provider": cfg["provider"],
        "model": cfg["model"] if ready else None,
        "configured": ready,
        "mode": "live_ai" if ready else "demo_fallback",
    }


def build_system_prompt(lesson: dict[str, Any], persona: str) -> str:
    concepts = "\\n".join(
        f"- {item['label_ar']}: {item['misconception']}"
        for item in lesson.get("concepts", [])
    )
    context = (
        f"عنوان الدرس: {lesson['title_ar']}\\n"
        f"الأهداف: {'؛ '.join(lesson.get('learning_objectives', []))}\\n"
        f"نقاط قد يختلط فهمها: \\n{concepts}"
    )
    return SYSTEM_TEMPLATE.format(
        persona=PERSONAS.get(persona, PERSONAS["milo"]),
        lesson_context=context,
    )


async def generate_reply(
    messages: list[dict[str, str]], lesson: dict[str, Any], persona: str
) -> str:
    cfg = provider_settings()
    provider = cfg["provider"]
    if provider == "none":
        raise RuntimeError("LLM provider is not configured")
    if provider not in {"ollama", "openai-compatible"}:
        raise RuntimeError("Unsupported PUPIL_LLM_PROVIDER")
    if not cfg["model"]:
        raise RuntimeError("Set PUPIL_LLM_MODEL before starting a live AI session")

    chat_messages = [{"role": "system", "content": build_system_prompt(lesson, persona)}]
    for item in messages[-14:]:
        role = "assistant" if item["role"] == "ai" else "user"
        chat_messages.append({"role": role, "content": item["text"]})

    timeout = httpx.Timeout(45.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        if provider == "ollama":
            url = f"{cfg['base_url']}/api/chat"
            response = await client.post(url, json={
                "model": cfg["model"],
                "messages": chat_messages,
                "stream": False,
                "options": {"temperature": 0.65},
            })
            response.raise_for_status()
            data = response.json()
            answer = data.get("message", {}).get("content", "")
        else:
            url = f"{cfg['base_url']}/v1/chat/completions"
            headers = {"Authorization": f"Bearer {cfg['api_key']}"} if cfg["api_key"] else {}
            response = await client.post(url, headers=headers, json={
                "model": cfg["model"],
                "messages": chat_messages,
                "temperature": 0.65,
            })
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices", [])
            answer = choices[0].get("message", {}).get("content", "") if choices else ""

    answer = str(answer).strip()
    if not answer:
        raise RuntimeError("The configured model returned an empty reply")
    return answer[:3000]
