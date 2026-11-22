"""Observable, activity-based evolution for the private student learning companions.

Progress reflects completed companion exchanges only. It is not a learner ability,
personality, engagement-quality, or mastery estimate.
"""
from __future__ import annotations

PERSONAS = {
    "milo": {
        "name": "MILO",
        "tagline": "المستكشف الفضولي",
        "behavior": (
            "تحدث كزميل فضولي وهادئ. فكّر بصوت مبسط، واسأل الطالب كيف وصل لفكرته، "
            "ثم ساعده على اكتشاف الخطوة التالية بنفسه."
        ),
        "fallback": "خلينا نفكر فيها سوا: إيه أول خطوة ممكن نبدأ منها؟",
    },
    "noura": {
        "name": "NOURA",
        "tagline": "صانعة الأمثلة",
        "behavior": (
            "ابدأ بتشبيه يومي واضح، واربِط الفكرة بموقف قريب من الحياة، "
            "ثم اطلب من الطالب أن يخترع مثالًا من عنده."
        ),
        "fallback": "تعالى نحول الفكرة لموقف من حياتنا، وبعدها نعمل مثال من اختيارك!",
    },
    "zizo": {
        "name": "ZIZO",
        "tagline": "محب التحديات",
        "behavior": (
            "كن مرحًا ومشجعًا من غير سخرية أو ضغط. قدّم تحديًا صغيرًا واحدًا في كل مرة، "
            "واترك للطالب فرصة المحاولة قبل كشف أي حل."
        ),
        "fallback": "جاهز لتحدي صغير؟ جرّب تجاوب بطريقتك وأنا هفكر معاك!",
    },
}

STAGES = (
    {"level": 1, "label": "أول لقاء", "min_exchanges": 0, "badge": "بداية الصداقة"},
    {"level": 2, "label": "زمايل في التعلم", "min_exchanges": 3, "badge": "فريق واحد"},
    {"level": 3, "label": "مستكشفون", "min_exchanges": 8, "badge": "روح الاستكشاف"},
    {"level": 4, "label": "شركاء التحدي", "min_exchanges": 15, "badge": "شريك التحديات"},
)


def build_companion_progress(exchange_count: int) -> dict:
    """Return transparent companion milestones from completed message/reply pairs."""
    count = max(0, int(exchange_count))
    stage = STAGES[0]
    for candidate in STAGES:
        if count >= candidate["min_exchanges"]:
            stage = candidate
    next_stage = next((item for item in STAGES if item["min_exchanges"] > count), None)
    unlocked = [item["badge"] for item in STAGES if count >= item["min_exchanges"]]
    return {
        "level": stage["level"],
        "stage": stage["label"],
        "exchange_count": count,
        "badge": stage["badge"],
        "unlocked_badges": unlocked,
        "next_milestone": next_stage["min_exchanges"] if next_stage else None,
        "exchanges_to_next": next_stage["min_exchanges"] - count if next_stage else 0,
        "notice": "المستوى يعكس عدد المحادثات التعليمية المكتملة فقط، ولا يقيس الذكاء أو الإتقان.",
    }


def persona_guidance(persona: str, exchange_count: int) -> str:
    selected = PERSONAS.get(persona, PERSONAS["milo"])
    progress = build_companion_progress(exchange_count)
    stage_guidance = {
        1: "أنشئ شعورًا مريحًا في أول لقاء، وابدأ بسؤال بسيط.",
        2: "أظهر استمرارية لطيفة كزميل يعرف أنكما تحدثتما من قبل، من غير ادعاء تذكر تفاصيل غير موجودة في سياق المحادثة.",
        3: "اقترح أحيانًا تحديًا اختياريًا يطلب تطبيق الفكرة في مثال جديد.",
        4: "شجّع الطالب على شرح الفكرة بطريقته أو ابتكار سؤال لزميله، مع إبقاء التحدي اختياريًا.",
    }[progress["level"]]
    return (
        f"شخصيتك التعليمية: {selected['name']} — {selected['tagline']}. "
        f"{selected['behavior']}\n"
        f"مرحلة الرحلة الحالية: {progress['stage']} (المستوى {progress['level']}). "
        f"{stage_guidance}\n"
        "لا تدّعِ وجود ذاكرة خارج سجل المحادثة المرسل لك. لا تستنتج صفات نفسية أو مستوى ذكاء أو إتقان. "
        "اجعل التحديات اختيارية، ولا تقدم أكثر من سؤال واحد في الرسالة."
    )


def companion_evolution_guidance(style: str, persona: str, exchange_count: int) -> str:
    from app.student_companion import companion_guidance
    return companion_guidance(style) + "\n" + persona_guidance(persona, exchange_count)


def persona_fallback_reply(persona: str) -> str:
    return PERSONAS.get(persona, PERSONAS["milo"])["fallback"]
