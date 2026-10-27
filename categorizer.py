import re

# كلمات دلالية للتصنيف التلقائي
TASK_KEYWORDS = [
    "لازم", "خلص", "أعمل", "هعمل", "بعمل", "اعمل", "ابعت", "ارد على",
    "أتصل", "اتصل", "اشتري", "أشتري", "روح", "task", "todo", "remind",
    "deadline", "موعد", "ميعاد", "قبل", "النهارده", "بكره", "الأسبوع"
]

IDEA_KEYWORDS = [
    "فكرة", "ممكن", "لو", "أفكر", "ليه مش", "idea", "ماذا لو", "يمكن",
    "اقتراح", "تخيل", "لو عملنا", "concept", "فكر"
]

EXPENSE_KEYWORDS = [
    "صرفت", "دفعت", "اشتريت", "جنيه", "جم", "ج", "دولار", "$", "£",
    "€", "ريال", "درهم", "expense", "spent", "paid", "فلوس", "كلفني",
    "بكام", "بـ"
]

GOAL_KEYWORDS = [
    "هدف", "عايز أوصل", "أوصل", "أحقق", "goal", "plan", "خطة",
    "بحلم", "مستقبل", "سنة", "شهر", "long term", "target", "أكون"
]


def detect_amount(text: str) -> float | None:
    """استخلص المبلغ من النص لو موجود."""
    # بحث عن أرقام قبل أو بعد كلمات العملة
    pattern = r'(\d+(?:\.\d+)?)\s*(?:جنيه|جم|ج\.?|دولار|\$|£|€|ريال|درهم)?'
    match = re.search(pattern, text)
    if match:
        return float(match.group(1))
    return None


def categorize(text: str) -> tuple[str, float | None]:
    """
    صنّف النص تلقائياً.
    رجّع (category, amount) — الـ amount بس مع المصاريف.
    """
    text_lower = text.lower()

    # لو المستخدم بدأ بـ emoji أو كلمة تصنيف صريحة
    if text.startswith(("✅", "☑️", "📌", "#مهمة", "#task")):
        return "task", None
    if text.startswith(("💡", "🧠", "#فكرة", "#idea")):
        return "idea", None
    if text.startswith(("💰", "💸", "🧾", "#مصروف", "#expense")):
        amount = detect_amount(text)
        return "expense", amount
    if text.startswith(("🎯", "🏆", "#هدف", "#goal")):
        return "goal", None

    # تصنيف تلقائي بالكلمات الدلالية
    scores = {"task": 0, "idea": 0, "expense": 0, "goal": 0}

    for kw in TASK_KEYWORDS:
        if kw in text_lower:
            scores["task"] += 1

    for kw in IDEA_KEYWORDS:
        if kw in text_lower:
            scores["idea"] += 1

    for kw in EXPENSE_KEYWORDS:
        if kw in text_lower:
            scores["expense"] += 2  # وزن أعلى لأن المصاريف واضحة

    for kw in GOAL_KEYWORDS:
        if kw in text_lower:
            scores["goal"] += 1

    best = max(scores, key=scores.get)

    if scores[best] == 0:
        return "idea", None  # لو مش واضح → فكرة (الأمان)

    amount = detect_amount(text) if best == "expense" else None
    return best, amount


# ترجمة الكاتيجوري لعربي للعرض
CATEGORY_LABELS = {
    "task":    "✅ مهمة",
    "idea":    "💡 فكرة",
    "expense": "💰 مصروف",
    "goal":    "🎯 هدف",
}

CATEGORY_EMOJIS = {
    "task":    "✅",
    "idea":    "💡",
    "expense": "💰",
    "goal":    "🎯",
}
