"""Original, editable learning units for the PUPIL ZERO demonstrator.

These are authored examples, not copied textbook pages. Grade/term mapping
must be checked against the official current Egyptian Ministry textbook.
"""
from typing import Any

PORTAL = "https://studentbooks.moe.gov.eg/"

CURRICULUM: dict[str, dict[str, Any]] = {
    "fractions": {
        "id": "fractions", "title_ar": "فهم الكسور", "title_en": "Understanding Fractions",
        "grade": "المرحلة الإعدادية — التحديد الدقيق قيد المراجعة", "subject": "Mathematics",
        "term": "Needs official textbook mapping", "academic_year": "2026/2027 — verification pending",
        "source_url": PORTAL,
        "learning_objectives": ["Explain numerator and denominator in context.", "Compare unit fractions using equal-sized wholes.", "Recognize equivalent fractions using visual reasoning."],
        "concepts": [
            {"id":"numerator_denominator","label_ar":"البسط والمقام","misconception":"A larger denominator always means a larger fraction.","correction":"For the same whole, more equal parts means each part is smaller.","evidence_terms":["البسط","المقام","أجزاء متساوية","نفس الحجم"]},
            {"id":"unit_fraction","label_ar":"الكسور الوحدة","misconception":"1/4 is greater than 1/2 because 4 is greater than 2.","correction":"For equal-sized wholes, one half is larger than one quarter.","evidence_terms":["النصف","الربع","أصغر","أكبر","نفس الحجم","نفس الحاجه"]},
            {"id":"equivalence","label_ar":"الكسور المتكافئة","misconception":"Changing only the numerator keeps the fraction's value.","correction":"Multiply or divide numerator and denominator by the same non-zero number.","evidence_terms":["متكافئ","نفس القيمة","نضرب البسط","نقسم البسط","٢/٤","1/2"]},
        ],
        "scenarios":[
            {"prompt_ar":"أنا شايف إن ربع البيتزا أكبر من نصفها، لأن الرقم ٤ أكبر من ٢. كلامي صح؟","target":"unit_fraction","expected":["whole","equal","smaller","أصغر","نفس الحجم","متساوي"]},
            {"prompt_ar":"لو عندنا بيتزتين نفس الحجم، واحدة متقسمة نصفين والتانية أربعة أجزاء متساوية، القطعة في أنهي واحدة أكبر؟ وليه؟","target":"unit_fraction","expected":["نصف","أكبر","أربع","ربع","تقسيم","أجزاء"]},
            {"prompt_ar":"هل ٢/٤ تساوي ١/٢؟ اشرحلي من غير ما تقول آه أو لأ بس.","target":"equivalence","expected":["نقسم","نضرب","نفس","متكافئ","نصف","أربعة"]},
        ],
    },
    "decimals": {
        "id":"decimals", "title_ar":"فهم الأعداد العشرية", "title_en":"Understanding Decimals",
        "grade":"المرحلة الإعدادية — التحديد الدقيق قيد المراجعة", "subject":"Mathematics",
        "term":"Needs official textbook mapping", "academic_year":"2026/2027 — verification pending", "source_url":PORTAL,
        "learning_objectives":["Explain tenths and hundredths using place value.","Compare decimal numbers by place value.","Connect decimal notation to money and measurement."],
        "concepts":[
            {"id":"decimal_place_value","label_ar":"القيمة المكانية","misconception":"Digits after the decimal point are whole numbers on their own.","correction":"Each position to the right represents a smaller place value such as tenths and hundredths.","evidence_terms":["أعشار","أجزاء من مئة","القيمة المكانية","منزلة"]},
            {"id":"decimal_comparison","label_ar":"مقارنة الأعداد العشرية","misconception":"0.8 is smaller than 0.75 because 8 is smaller than 75.","correction":"Compare place values; 0.80 is greater than 0.75.","evidence_terms":["0.80","0.75","أكبر","مقارنة","نفس المنزلة"]},
        ],
        "scenarios":[
            {"prompt_ar":"أنا محتار: هل ٠٫٨ أصغر من ٠٫٧٥ عشان ٨ أصغر من ٧٥؟","target":"decimal_comparison","expected":["0.80","0.75","أكبر","أعشار","مقارنة"]},
            {"prompt_ar":"لو معايا ٠٫٥٠ جنيه و٠٫٥ جنيه، هل القيمة مختلفة؟ اشرحلي.","target":"decimal_place_value","expected":["نفس","القيمة","صفر","خمسين","نصف"]},
        ],
    },
    "ratio": {
        "id":"ratio", "title_ar":"مقدمة في النسبة والتناسب", "title_en":"Introduction to Ratios",
        "grade":"المرحلة الإعدادية — التحديد الدقيق قيد المراجعة", "subject":"Mathematics",
        "term":"Needs official textbook mapping", "academic_year":"2026/2027 — verification pending", "source_url":PORTAL,
        "learning_objectives":["Describe a ratio as a comparison of quantities.","Keep the order of compared quantities clear.","Scale equivalent ratios by the same factor."],
        "concepts":[
            {"id":"ratio_order","label_ar":"ترتيب النسبة","misconception":"A ratio is unchanged when its two quantities are reversed.","correction":"The order matters because it tells which quantity is compared to which.","evidence_terms":["الترتيب","الأول","الثاني","مختلفة","مش نفس"]},
            {"id":"equivalent_ratio","label_ar":"النسب المتكافئة","misconception":"Only one side of a ratio should be scaled.","correction":"Multiply or divide both quantities by the same non-zero factor.","evidence_terms":["نضرب الاتنين","نفس العدد","الطرفين","متكافئة"]},
        ],
        "scenarios":[
            {"prompt_ar":"لو نسبة التفاح للبرتقال ٢ إلى ٣، هل هي نفسها ٣ إلى ٢؟ وليه؟","target":"ratio_order","expected":["الترتيب","مختلفة","مش نفس","التفاح","البرتقال"]},
            {"prompt_ar":"لو ضاعفنا عدد التفاح بس وسبنا البرتقال زي ما هو، هل النسبة تفضل زي ما هي؟","target":"equivalent_ratio","expected":["الاتنين","نفس العدد","الطرفين","النسبة"]},
        ],
    },
}


def get_lesson(lesson_id: str = "fractions") -> dict[str, Any] | None:
    return CURRICULUM.get(lesson_id)


def list_lessons() -> list[dict[str, str]]:
    return [
        {"id": lesson["id"], "title_ar": lesson["title_ar"], "title_en": lesson["title_en"], "grade": lesson["grade"]}
        for lesson in CURRICULUM.values()
    ]
