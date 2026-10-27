import os
import json
import asyncio
from dotenv import load_dotenv
from google import genai
from google.genai import types
from database import get_weekly_summary

load_dotenv()

SYSTEM_PROMPT = """
أنت سكرتير ومساعد شخصي ذكي وواقعي جداً اسمك "مساعدي".
هدفك تفهم كلام المستخدم وتميز بين أنواع المدخلات بدون أي تسرع أو تحويل كل شيء لمهام.

معايير التصنيف الصارمة:
١. "task" (مهمة):
   - فقط وفقط إذا كان الكلام يحتوي على إجراء تنفيذي محدد ومطلوب إنجازه قريباً (Action Item).
   - أمثلة: "محتاج أكلم الدكتور"، "لازم أخلص الشيت قبل بكرة"، "فكرني اشتري لبن".
   - لا تصنف أي فكرة أو خاطرة أو طموح كمهمة!

٢. "idea" (فكرة أو ملاحظة):
   - أي فكرة عابرة، معلومة عايز يحفظها، خاطرة شخصية، اقتراح، رأي، أو كلام عام ليس له التزام تنفيذي فوري.
   - أمثلة: "لو عملنا منصة لتبادل الكتب هتكون فكرة حلوة"، "في موقع اسمه كذا مفيد في التصميم"، "الجو النهاردة كان هادي".

٣. "expense" (مصروفات):
   - أي شيء يخص دفع أموال، شراء، مصاريف، اشتراكات، فواتير.
   - أمثلة: "دفعت 70 مواصلات"، "اشتريت شاحن بـ 450"، "فاتورة النت اتجددت".

٤. "goal" (هدف):
   - طموح مستقبلي، خطة طويلة الأجل، أهداف تطوير الذات أو عادات جديدة.
   - أمثلة: "عايز أخس 5 كيلو قبل الصيف"، "هدفي أوصل لـ B2 في الإنجليزي السنة دي".

قواعد الرد:
- تجنب تماماً تصنيف الكلام كـ task لمجرد أنه يمكن عمله مستقبلاً. إن لم يكن إجراءً مباشراً واضحاً، فهو فكرة (idea) أو هدف (goal).
- ردك يجب أن يكون بصيغة JSON حصراً:
{
  "category": "task|idea|expense|goal",
  "content": "النص المنظف والمختصر المناسب للحفظ",
  "amount": null,
  "reply": "ردك الذكي والودود المناسب للسياق",
  "suggestion": null
}

لو مصروف وفيه مبلغ: ضع amount كرقم (مثال: 70)، وإلا null.
لو عندك تعليق أو اقتراح مفيد بدون أي إلحاح: ضعه في suggestion، وإلا null.
"""


def _call_gemini_sync(text: str, user_id: int) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)

    summary = get_weekly_summary(user_id)
    context = (
        f"بيانات المستخدم الحالية:\n"
        f"- مهام متبقية: {summary['task']}\n"
        f"- أفكار: {summary['idea']}\n"
        f"- أهداف: {summary['goal']}\n"
        f"- مصاريف: {summary['expense']} (إجمالي: {summary['total_expenses']:.0f})\n\n"
        f"رسالة المستخدم: {text}"
    )

    models_to_try = ["gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.5-flash-lite"]
    last_err = None

    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=context,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json"
                )
            )
            raw_text = response.text.strip()
            return json.loads(raw_text)
        except Exception as e:
            last_err = e
            continue

    raise last_err


async def process_with_ai(text: str, user_id: int) -> dict:
    try:
        result = await asyncio.to_thread(_call_gemini_sync, text, user_id)
        return {
            "category": result.get("category", "idea"),
            "content":  result.get("content", text),
            "amount":   result.get("amount"),
            "reply":    result.get("reply", "تم الحفظ بنجاح 👍"),
            "suggestion": result.get("suggestion"),
        }
    except Exception as e:
        print(f"[AI ERROR] {e}")
        from categorizer import categorize
        cat, amt = categorize(text)
        return {
            "category": cat,
            "content": text,
            "amount": amt,
            "reply": "تم الحفظ ✔️",
            "suggestion": None,
        }
