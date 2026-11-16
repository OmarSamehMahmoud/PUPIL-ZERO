"""Transparent, curriculum-authored study paths and low-stakes quizzes.

No model-generated grades or mastery claims: recommendations use explainable
keyword evidence and questions are reviewed, static items authored for this demo.
"""
from __future__ import annotations

from typing import Any

QUIZ_BANK: dict[str, list[dict[str, Any]]] = {
    "fractions": [
        {"id":"fraction_q1","concept_id":"numerator_denominator","prompt":"في الكسر ٣/٥، المقام بيوضح إيه؟",
         "options":[{"id":"a","text":"عدد الأجزاء المتساوية في الكل"},{"id":"b","text":"عدد الأجزاء التي أخذناها"},{"id":"c","text":"حجم الكل دائمًا"}],
         "correct_option":"a","explanation":"المقام يوضح عدد الأجزاء المتساوية التي قُسم إليها الكل."},
        {"id":"fraction_q2","concept_id":"unit_fraction","prompt":"لو نفس البيتزا اتقسمت ٤ أجزاء متساوية بدل جزئين، القطعة الواحدة هتكون إزاي؟",
         "options":[{"id":"a","text":"أكبر"},{"id":"b","text":"أصغر"},{"id":"c","text":"نفس الحجم"}],
         "correct_option":"b","explanation":"عند تقسيم نفس الكل إلى أجزاء أكثر ومتساوية، يصبح الجزء الواحد أصغر."},
        {"id":"fraction_q3","concept_id":"equivalence","prompt":"أي كسر يساوي ١/٢؟",
         "options":[{"id":"a","text":"١/٣"},{"id":"b","text":"٢/٤"},{"id":"c","text":"٣/٤"}],
         "correct_option":"b","explanation":"نضرب البسط والمقام في ٢ فنحصل على ٢/٤."},
    ],
    "decimals": [
        {"id":"decimal_q1","concept_id":"decimal_place_value","prompt":"في العدد ٠٫٤، الرقم ٤ بيمثل إيه؟",
         "options":[{"id":"a","text":"أربعة أعشار"},{"id":"b","text":"أربعة آحاد"},{"id":"c","text":"أربعة أجزاء من ألف"}],
         "correct_option":"a","explanation":"أول منزلة يمين العلامة العشرية هي منزلة الأعشار."},
        {"id":"decimal_q2","concept_id":"decimal_comparison","prompt":"أنهي عدد أكبر؟",
         "options":[{"id":"a","text":"٠٫٧٥"},{"id":"b","text":"٠٫٨٠"},{"id":"c","text":"متساويان"}],
         "correct_option":"b","explanation":"٠٫٨٠ أكبر من ٠٫٧٥ عند المقارنة حتى منزلة الجزء من مئة."},
        {"id":"decimal_q3","concept_id":"decimal_place_value","prompt":"هل ٠٫٥٠ و٠٫٥ لهما نفس القيمة؟",
         "options":[{"id":"a","text":"نعم"},{"id":"b","text":"لا، ٠٫٥٠ أكبر"},{"id":"c","text":"لا، ٠٫٥ أصغر"}],
         "correct_option":"a","explanation":"الصفر في نهاية الجزء العشري لا يغيّر القيمة."},
    ],
    "ratio": [
        {"id":"ratio_q1","concept_id":"ratio_order","prompt":"نسبة التفاح للبرتقال ٢ إلى ٣. هل ٣ إلى ٢ نفس النسبة؟",
         "options":[{"id":"a","text":"نعم دائمًا"},{"id":"b","text":"لا، ترتيب الكميتين اتغيّر"},{"id":"c","text":"النسب لا تقارن"}],
         "correct_option":"b","explanation":"ترتيب الكميتين مهم ويغيّر معنى المقارنة."},
        {"id":"ratio_q2","concept_id":"equivalent_ratio","prompt":"لو النسبة ٢ إلى ٣ وضربنا الطرفين في ٢، تبقى كام؟",
         "options":[{"id":"a","text":"٤ إلى ٦"},{"id":"b","text":"٤ إلى ٣"},{"id":"c","text":"٢ إلى ٦"}],
         "correct_option":"a","explanation":"للحفاظ على النسبة نضرب الطرفين في نفس العدد."},
        {"id":"ratio_q3","concept_id":"equivalent_ratio","prompt":"إيه العملية اللي تحافظ على تكافؤ النسبة؟",
         "options":[{"id":"a","text":"نضرب طرف واحد فقط"},{"id":"b","text":"نضيف ١ لطرف واحد"},{"id":"c","text":"نضرب الطرفين في نفس العدد غير الصفري"}],
         "correct_option":"c","explanation":"ضرب طرفي النسبة في نفس العامل غير الصفري يحافظ على التكافؤ."},
    ],
}


def get_quiz_questions(lesson_id: str) -> list[dict[str, Any]]:
    return [dict(q, options=[dict(o) for o in q["options"]]) for q in QUIZ_BANK.get(lesson_id, [])]


def grade_quiz(questions: list[dict[str, Any]], answers: dict[str, str]) -> dict[str, Any]:
    details = []
    correct = 0
    for question in questions:
        selected = answers.get(question["id"], "")
        is_correct = selected == question["correct_option"]
        correct += int(is_correct)
        details.append({
            "question_id": question["id"], "concept_id": question["concept_id"],
            "correct": is_correct, "selected_option": selected or None,
            "correct_option": question["correct_option"],
            "explanation": question["explanation"],
        })
    total = len(questions)
    return {
        "score": correct, "total": total,
        "percentage": round(correct * 100 / total) if total else 0,
        "details": details,
        "notice": "نتيجة تدريبية فورية للمراجعة الذاتية؛ ليست درجة مدرسية أو دليلًا معتمدًا على الإتقان.",
    }


def build_study_plan(lesson: dict[str, Any], reports: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {item["id"]: 0 for item in lesson.get("concepts", [])}
    for record in reports:
        report = record.get("report") or {}
        for item in report.get("concepts", []):
            if item.get("status") == "evidence_found" and item.get("concept_id") in counts:
                counts[item["concept_id"]] += 1
    steps = []
    for concept in lesson.get("concepts", []):
        observed = counts.get(concept["id"], 0)
        steps.append({
            "concept_id": concept["id"], "concept": concept["label_ar"],
            "priority": "practice" if observed == 0 else "review" if observed == 1 else "stretch",
            "evidence_sessions": observed,
            "activity": (
                "ابدأ بمثال بسيط واشرح الفكرة بكلماتك." if observed == 0 else
                "راجع الفكرة ثم اشرح مثالًا مختلفًا عن السابق." if observed == 1 else
                "جرّب تطبيق الفكرة في موقف جديد واشرح لماذا تنجح."
            ),
        })
    steps.sort(key=lambda item: ({"practice":0,"review":1,"stretch":2}[item["priority"]], item["concept"]))
    return {
        "lesson_id": lesson["id"], "lesson": lesson["title_ar"],
        "steps": steps, "sessions_reviewed": len(reports),
        "basis": "ترتيب مقترح مبني على إشارات كلمات في تقارير الشرح السابقة، وليس تشخيصًا أو قياسًا للإتقان.",
        "limitations": ["قد لا تلتقط مطابقة الكلمات المعنى المقصود أو اختلاف اللهجة والإملاء.",
                        "راجع الشرح والسياق مع المعلم قبل اتخاذ قرار تعليمي."],
    }
