"""Local-first chat provider for PUPIL ZERO."""
from __future__ import annotations

import os
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

SYSTEM_TEMPLATE = """أنت {persona_name}، زميل دراسة افتراضي لطيف وفضولي لطالب مدرسة في مصر.
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

حالة الحوار التكيفية:
{state_context}
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


def build_system_prompt(lesson: dict[str, Any], persona: str = "milo", state_context: str = "ابدأ بسؤال استكشافي واحد.") -> str:
    concepts = "\n".join(
        f"- {item['label_ar']}: {item['misconception']}"
        for item in lesson.get("concepts", [])
    )
    context = (
        f"عنوان الدرس: {lesson['title_ar']}\n"
        f"الأهداف: {'؛ '.join(lesson.get('learning_objectives', []))}\n"
        f"نقاط قد يختلط فهمها: \n{concepts}"
    )
    names = {"milo": "MILO", "noura": "NOURA", "zizo": "ZIZO"}
    return SYSTEM_TEMPLATE.format(
        persona_name=names.get(persona, "MILO"),
        persona=PERSONAS.get(persona, PERSONAS["milo"]),
        lesson_context=context,
        state_context=state_context,
    )


def _history_messages(transcript: list[dict[str, str]], system_prompt: str) -> list[dict[str, str]]:
    history = [{"role": "system", "content": system_prompt}]
    for item in transcript[-14:]:
        role = "assistant" if item.get("role") == "ai" else "user"
        history.append({"role": role, "content": item.get("text", "")})
    return history


async def generate_reply(
    messages: list[dict[str, str]], lesson: dict[str, Any], persona: str,
    dialogue_state: str = "ابدأ بسؤال استكشافي واحد."
) -> str:
    cfg = provider_settings()
    provider = cfg["provider"]
    if provider == "none":
        raise RuntimeError("LLM provider is not configured")
    if provider not in {"ollama", "openai-compatible"}:
        raise RuntimeError("Unsupported PUPIL_LLM_PROVIDER")
    if not cfg["model"]:
        raise RuntimeError("Set PUPIL_LLM_MODEL before starting a live AI session")

    chat_messages = _history_messages(messages, build_system_prompt(lesson, persona, dialogue_state))

    timeout = httpx.Timeout(60.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        if provider == "ollama":
            response = await client.post(
                f"{cfg['base_url']}/api/chat",
                json={
                    "model": cfg["model"],
                    "messages": chat_messages,
                    "stream": False,
                    "options": {"temperature": 0.65},
                },
            )
            response.raise_for_status()
            answer = response.json().get("message", {}).get("content", "")
        else:
            headers = {"Authorization": f"Bearer {cfg['api_key']}"} if cfg["api_key"] else {}
            response = await client.post(
                f"{cfg['base_url']}/v1/chat/completions",
                headers=headers,
                json={"model": cfg["model"], "messages": chat_messages, "temperature": 0.65},
            )
            response.raise_for_status()
            choices = response.json().get("choices", [])
            answer = choices[0].get("message", {}).get("content", "") if choices else ""

    answer = str(answer).strip()
    if not answer:
        raise RuntimeError("The configured model returned an empty reply")
    return answer[:3000]


async def generate_structured_reply(messages: list[dict[str, str]], system_prompt: str) -> str:
    """Generate strict JSON-oriented output without the single-persona chat template."""
    cfg = provider_settings()
    provider = cfg["provider"]
    if provider not in {"ollama", "openai-compatible"}:
        raise RuntimeError("A configured Ollama or OpenAI-compatible provider is required")
    if not cfg["model"]:
        raise RuntimeError("Set PUPIL_LLM_MODEL before starting a structured AI interaction")

    chat_messages = [{"role": "system", "content": system_prompt}]
    chat_messages.extend(
        {"role": item.get("role", "user"), "content": item.get("text", "")}
        for item in messages[-8:]
    )
    timeout = httpx.Timeout(60.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        if provider == "ollama":
            response = await client.post(
                f"{cfg['base_url']}/api/chat",
                json={
                    "model": cfg["model"], "messages": chat_messages,
                    "stream": False, "format": "json",
                    "options": {"temperature": 0.35},
                },
            )
            response.raise_for_status()
            answer = response.json().get("message", {}).get("content", "")
        else:
            headers = {"Authorization": f"Bearer {cfg['api_key']}"} if cfg["api_key"] else {}
            response = await client.post(
                f"{cfg['base_url']}/v1/chat/completions",
                headers=headers,
                json={
                    "model": cfg["model"], "messages": chat_messages,
                    "temperature": 0.35, "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            choices = response.json().get("choices", [])
            answer = choices[0].get("message", {}).get("content", "") if choices else ""
    answer = str(answer).strip()
    if not answer:
        raise RuntimeError("The configured model returned an empty structured response")
    return answer[:5000]


async def generate_formative_quiz(lesson: dict[str, Any], count: int = 3) -> list[dict[str, Any]]:
    """Generate validated candidate MCQs using the configured local/self-hosted model."""
    import json
    cfg = provider_settings()
    provider = cfg["provider"]
    if provider not in {"ollama", "openai-compatible"} or not cfg["model"]:
        raise RuntimeError("A configured AI provider and model are required")
    concepts = [
        {"id": item["id"], "label": item["label_ar"], "explanation": item.get("correction", ""),
         "common_confusion": item.get("misconception", "")}
        for item in lesson.get("concepts", [])
    ]
    prompt = (
        "Create exactly " + str(count) + " age-appropriate formative multiple-choice questions "
        "in clear Egyptian Arabic, based only on this original lesson data. "
        "Cover different concepts where possible. Avoid trick questions, personal data, "
        "and claims about student ability. Return ONLY a JSON object with key questions. "
        "Each question must have concept_id, prompt, options (exactly 3 objects with id and text), "
        "correct_option (one option id), and explanation. Use option ids a,b,c. "
        "Do not include markdown fences.\nLESSON DATA:\n" +
        json.dumps({"title": lesson.get("title_ar"), "objectives": lesson.get("learning_objectives", []),
                    "concepts": concepts}, ensure_ascii=False)
    )
    messages = [
        {"role": "system", "content": "You write careful educational practice questions. Output valid JSON only."},
        {"role": "user", "content": prompt},
    ]
    timeout = httpx.Timeout(90.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        if provider == "ollama":
            response = await client.post(
                f"{cfg['base_url']}/api/chat",
                json={"model": cfg["model"], "messages": messages, "stream": False,
                      "format": "json", "options": {"temperature": 0.2}},
            )
            response.raise_for_status()
            raw = response.json().get("message", {}).get("content", "")
        else:
            headers = {"Authorization": f"Bearer {cfg['api_key']}"} if cfg["api_key"] else {}
            response = await client.post(
                f"{cfg['base_url']}/v1/chat/completions", headers=headers,
                json={"model": cfg["model"], "messages": messages, "temperature": 0.2,
                      "response_format": {"type": "json_object"}},
            )
            response.raise_for_status()
            choices = response.json().get("choices", [])
            raw = choices[0].get("message", {}).get("content", "") if choices else ""
    try:
        parsed = json.loads(str(raw).strip())
    except (TypeError, ValueError) as exc:
        raise RuntimeError("The configured model did not return valid JSON") from exc
    questions = parsed.get("questions") if isinstance(parsed, dict) else None
    if not isinstance(questions, list) or len(questions) != count:
        raise RuntimeError("The configured model returned an invalid question count")
    allowed_concepts = {item["id"] for item in concepts}
    validated = []
    for index, item in enumerate(questions):
        if not isinstance(item, dict) or item.get("concept_id") not in allowed_concepts:
            raise RuntimeError("Generated question references an unknown lesson concept")
        prompt_text = item.get("prompt")
        options = item.get("options")
        correct = item.get("correct_option")
        explanation = item.get("explanation")
        if not isinstance(prompt_text, str) or not 8 <= len(prompt_text.strip()) <= 500:
            raise RuntimeError("Generated question prompt failed validation")
        if not isinstance(explanation, str) or not 5 <= len(explanation.strip()) <= 700:
            raise RuntimeError("Generated explanation failed validation")
        if not isinstance(options, list) or len(options) != 3:
            raise RuntimeError("Generated question must have exactly three options")
        normalized = []
        option_ids = set()
        for option in options:
            if not isinstance(option, dict) or not isinstance(option.get("id"), str) or not isinstance(option.get("text"), str):
                raise RuntimeError("Generated option failed validation")
            oid, text_value = option["id"].strip(), option["text"].strip()
            if oid not in {"a", "b", "c"} or oid in option_ids or not 1 <= len(text_value) <= 240:
                raise RuntimeError("Generated option failed validation")
            option_ids.add(oid)
            normalized.append({"id": oid, "text": text_value})
        if option_ids != {"a", "b", "c"} or correct not in option_ids:
            raise RuntimeError("Generated correct answer failed validation")
        validated.append({
            "id": f"ai_{lesson['id']}_{index + 1}_{uuid_token()}",
            "concept_id": item["concept_id"], "prompt": prompt_text.strip(),
            "options": normalized, "correct_option": correct,
            "explanation": explanation.strip(),
        })
    return validated


def uuid_token() -> str:
    import secrets
    return secrets.token_hex(4)


async def generate_learning_feedback(lesson: dict[str, Any], incorrect_items: list[dict[str, str]]) -> list[dict[str, str]]:
    """Create private, low-stakes alternative explanations without student identifiers."""
    import json
    cfg = provider_settings()
    if cfg["provider"] not in {"ollama", "openai-compatible"} or not cfg["model"]:
        raise RuntimeError("A configured local AI provider and model are required")
    safe_items = [{
        "question_id": item["question_id"], "concept_id": item["concept_id"],
        "question": item["question"], "selected_answer": item["selected_answer"],
        "correct_answer": item["correct_answer"], "authored_explanation": item["authored_explanation"],
        "concept_explanation": item["concept_explanation"],
    } for item in incorrect_items]
    prompt = (
        "For each incorrect practice answer, write supportive Egyptian Arabic feedback. "
        "Do not shame, label, diagnose, infer ability, or say the learner has a misconception. "
        "Acknowledge the selected answer neutrally, explain the idea in a different simple way, "
        "and give one short practice prompt without its answer. Use only the supplied lesson facts. "
        "Return JSON only: {\"feedback\":[{\"question_id\":str,\"feedback\":str,"
        "\"alternative_explanation\":str,\"practice_prompt\":str}]}. Include every question_id exactly once. "
        "Each text must be concise.\nDATA:\n" +
        json.dumps({"lesson": lesson.get("title_ar"), "items": safe_items}, ensure_ascii=False)
    )
    messages = [{"role":"system","content":"You are a careful learning-support writer. Return valid JSON only."},
                {"role":"user","content":prompt}]
    timeout = httpx.Timeout(90.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        if cfg["provider"] == "ollama":
            response = await client.post(f"{cfg['base_url']}/api/chat",
                json={"model":cfg["model"],"messages":messages,"stream":False,"format":"json",
                      "options":{"temperature":0.25}})
            response.raise_for_status()
            raw = response.json().get("message",{}).get("content","")
        else:
            headers = {"Authorization":f"Bearer {cfg['api_key']}"} if cfg["api_key"] else {}
            response = await client.post(f"{cfg['base_url']}/v1/chat/completions",headers=headers,
                json={"model":cfg["model"],"messages":messages,"temperature":0.25,
                      "response_format":{"type":"json_object"}})
            response.raise_for_status()
            choices=response.json().get("choices",[])
            raw=choices[0].get("message",{}).get("content","") if choices else ""
    try:
        parsed=json.loads(str(raw).strip())
        feedback=parsed.get("feedback") if isinstance(parsed,dict) else None
    except (TypeError,ValueError) as exc:
        raise RuntimeError("Local AI returned invalid feedback JSON") from exc
    expected={item["question_id"] for item in safe_items}
    if not isinstance(feedback,list) or {x.get("question_id") for x in feedback if isinstance(x,dict)} != expected:
        raise RuntimeError("Local AI feedback did not match the submitted questions")
    clean=[]
    for item in feedback:
        row={"question_id":item["question_id"]}
        for key in ("feedback","alternative_explanation","practice_prompt"):
            value=item.get(key)
            if not isinstance(value,str) or not 5 <= len(value.strip()) <= 500:
                raise RuntimeError("Local AI feedback failed validation")
            row[key]=value.strip()
        clean.append(row)
    return clean


async def generate_teacher_review_suggestions(lesson: dict[str, Any], patterns: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Generate class-level review ideas from anonymous aggregated answer counts."""
    import json
    cfg=provider_settings()
    if cfg["provider"] not in {"ollama","openai-compatible"} or not cfg["model"]:
        raise RuntimeError("A configured local AI provider and model are required")
    prompt=("Create one practical teacher-led review activity per supplied concept, in Egyptian Arabic. "
        "Use only supplied lesson facts. Do not diagnose students or claim mastery. "
        "Return JSON only: {\"suggestions\":[{\"concept_id\":str,\"activity\":str,"
        "\"teacher_question\":str}]}. Preserve every concept_id exactly once.\nDATA:\n"+
        json.dumps({"lesson":lesson.get("title_ar"),"patterns":patterns},ensure_ascii=False))
    messages=[{"role":"system","content":"You are a cautious teaching assistant. Return valid JSON only."},
              {"role":"user","content":prompt}]
    timeout=httpx.Timeout(90.0,connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        if cfg["provider"]=="ollama":
            response=await client.post(f"{cfg['base_url']}/api/chat",
                json={"model":cfg["model"],"messages":messages,"stream":False,"format":"json",
                      "options":{"temperature":0.2}})
            response.raise_for_status()
            raw=response.json().get("message",{}).get("content","")
        else:
            headers={"Authorization":f"Bearer {cfg['api_key']}"} if cfg["api_key"] else {}
            response=await client.post(f"{cfg['base_url']}/v1/chat/completions",headers=headers,
                json={"model":cfg["model"],"messages":messages,"temperature":0.2,
                      "response_format":{"type":"json_object"}})
            response.raise_for_status()
            choices=response.json().get("choices",[])
            raw=choices[0].get("message",{}).get("content","") if choices else ""
    try:
        parsed=json.loads(str(raw).strip())
        rows=parsed.get("suggestions") if isinstance(parsed,dict) else None
    except (TypeError,ValueError) as exc:
        raise RuntimeError("Local AI returned invalid teacher suggestions JSON") from exc
    expected={item["concept_id"] for item in patterns}
    if not isinstance(rows,list) or {x.get("concept_id") for x in rows if isinstance(x,dict)} != expected:
        raise RuntimeError("Local AI teacher suggestions did not match the requested concepts")
    result=[]
    for row in rows:
        item={"concept_id":row["concept_id"]}
        for key in ("activity","teacher_question"):
            value=row.get(key)
            if not isinstance(value,str) or not 8 <= len(value.strip()) <= 600:
                raise RuntimeError("Local AI teacher suggestion failed validation")
            item[key]=value.strip()
        result.append(item)
    return result


async def generate_open_response_analysis(lesson: dict[str, Any], answer: str) -> list[dict[str, str]]:
    """Link an open response to authored concepts using quoted, verifiable evidence only."""
    import json
    cfg = provider_settings()
    concepts = [{"concept_id": c["id"], "concept": c["label_ar"],
                 "learning_note": c.get("correction", ""), "evidence_terms": c.get("evidence_terms", [])}
                for c in lesson.get("concepts", [])]
    if cfg["provider"] not in {"ollama", "openai-compatible"} or not cfg["model"]:
        raise RuntimeError("A configured local AI provider and model are required")
    prompt = ("Review this student's explanation for formative support. Do not diagnose, grade, infer ability, "
        "or claim mastery. For every supplied concept return one row. Any positive signal MUST quote an exact "
        "substring from student_answer in evidence_quote. Otherwise use empty quote and status needs_clarification. "
        "Never invent evidence. Return JSON only: {concept_signals:[{concept_id,status,evidence_quote,"
        "interpretation,follow_up_question}]}. status is evidence_found or needs_clarification. "
        "Use concise Egyptian Arabic for interpretation and follow_up_question.\nDATA:\n" +
        json.dumps({"lesson": lesson.get("title_ar"), "concepts": concepts, "student_answer": answer}, ensure_ascii=False))
    messages = [{"role":"system","content":"You are a cautious formative-learning assistant. Output valid JSON only."},
                {"role":"user","content":prompt}]
    timeout = httpx.Timeout(90.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        if cfg["provider"] == "ollama":
            response = await client.post(f"{cfg['base_url']}/api/chat",
                json={"model":cfg["model"],"messages":messages,"stream":False,"format":"json",
                      "options":{"temperature":0.1}})
            response.raise_for_status()
            raw = response.json().get("message",{}).get("content","")
        else:
            headers = {"Authorization":f"Bearer {cfg['api_key']}"} if cfg["api_key"] else {}
            response = await client.post(f"{cfg['base_url']}/v1/chat/completions",headers=headers,
                json={"model":cfg["model"],"messages":messages,"temperature":0.1,
                      "response_format":{"type":"json_object"}})
            response.raise_for_status()
            choices=response.json().get("choices",[])
            raw=choices[0].get("message",{}).get("content","") if choices else ""
    try:
        parsed=json.loads(str(raw).strip())
        rows=parsed.get("concept_signals") if isinstance(parsed,dict) else None
    except (TypeError,ValueError) as exc:
        raise RuntimeError("Local AI returned invalid open-response JSON") from exc
    expected={c["concept_id"] for c in concepts}
    if not isinstance(rows,list) or {x.get("concept_id") for x in rows if isinstance(x,dict)} != expected:
        raise RuntimeError("Local AI concept links did not match this lesson")
    clean=[]
    for row in rows:
        if not isinstance(row,dict) or row.get("status") not in {"evidence_found","needs_clarification"}:
            raise RuntimeError("Local AI returned an invalid evidence status")
        quote=row.get("evidence_quote","")
        if not isinstance(quote,str) or len(quote)>240 or (quote and quote not in answer):
            raise RuntimeError("Local AI evidence quote was not found verbatim in the answer")
        if (row["status"]=="evidence_found") != bool(quote):
            raise RuntimeError("Local AI evidence status and quote disagree")
        item={"concept_id":row["concept_id"],"status":row["status"],"evidence_quote":quote}
        for key in ("interpretation","follow_up_question"):
            value=row.get(key)
            if not isinstance(value,str) or not 5<=len(value.strip())<=400:
                raise RuntimeError("Local AI open-response text failed validation")
            item[key]=value.strip()
        clean.append(item)
    return clean
