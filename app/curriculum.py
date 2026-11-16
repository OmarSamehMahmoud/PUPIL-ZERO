"""Original MVP learning content; not copied textbook pages.

Topics are aligned at a high level with Egyptian preparatory mathematics.
Verify the exact 2026/2027 textbook sequence against the Ministry portal before
claiming exact curriculum coverage.
"""
from typing import Any

CURRICULUM: dict[str, dict[str, Any]] = {
    "fractions": {
        "id": "fractions",
        "title_ar": "فهم الكسور",
        "title_en": "Understanding Fractions",
        "grade": "Preparatory 1 (demonstrator)",
        "subject": "Mathematics",
        "term": "To be verified against current textbook",
        "source_url": "https://studentbooks.moe.gov.eg/",
        "learning_objectives": [
            "Explain numerator and denominator in context.",
            "Compare unit fractions using equal-sized wholes.",
            "Recognize equivalent fractions using visual reasoning.",
        ],
        "concepts": [
            {"id": "numerator_denominator", "label_ar": "البسط والمقام", "misconception": "A larger denominator always means a larger fraction.", "correction": "When the whole is the same size, dividing it into more equal parts makes each part smaller."},
            {"id": "unit_fraction", "label_ar": "الكسور الوحدة", "misconception": "1/4 is greater than 1/2 because 4 is greater than 2.", "correction": "Compare equal-sized wholes: one half is larger than one quarter."},
            {"id": "equivalence", "label_ar": "الكسور المتكافئة", "misconception": "Changing the numerator alone keeps the fraction's value.", "correction": "Multiply or divide numerator and denominator by the same non-zero number."},
        ],
        "scenarios": [
            {"prompt_ar": "أنا شايف إن ربع البيتزا أكبر من نصفها، لأن الرقم ٤ أكبر من ٢. كلامي صح؟", "target": "unit_fraction", "expected": ["whole", "equal", "smaller", "أصغر", "نفس الحجم", "متساوي"]},
            {"prompt_ar": "لو عندنا بيتزتين نفس الحجم، واحدة متقسمة نصفين والتانية أربعة أجزاء متساوية، القطعة في أنهي واحدة أكبر؟ وليه؟", "target": "unit_fraction", "expected": ["نصف", "أكبر", "أربع", "ربع", "تقسيم", "أجزاء"]},
            {"prompt_ar": "هل ٢/٤ تساوي ١/٢؟ اشرحلي من غير ما تقول آه أو لأ بس.", "target": "equivalence", "expected": ["نقسم", "نضرب", "نفس", "متكافئ", "نصف", "أربعة"]},
        ],
    }
}


def get_lesson(lesson_id: str = "fractions") -> dict[str, Any] | None:
    return CURRICULUM.get(lesson_id)
