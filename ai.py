import os
import json
import asyncio
from dotenv import load_dotenv
from google import genai
from google.genai import types
from database import get_weekly_summary

load_dotenv()

SYSTEM_PROMPT = """
أنت مساعد شخصي ذكي وودود اسمك "مساعدي".
بتساعد المستخدم يتنظم في حياته اليومية.

مهمتك لما المستخدم يبعتلك رسالة:
١. تفهم إيه اللي قاله بدقة وذكاء
٢. تصنفه في واحدة من 4 فئات:
   - task: مهمة أو حاجة محتاج يعملها
   - idea: فكرة أو ملاحظة يحفظها
   - expense: مصروف أو فلوس دفعها
   - goal: هدف بعيد المدى
٣. ترد عليه بطريقة طبيعية ومباشرة وذكية كشخص فاهم وواعي بسياق المستخدم
٤. لو فيه اقتراح عملي وسريع يقدر يساعده، اقترحه باختصار وبدون ضغط إطلاقاً

قواعد الرد:
- الرد يجب أن يكون بصيغة JSON حصراً بهذا الشكل:
{
  "category": "task|idea|expense|goal",
  "content": "النص المنظف والمختصر اللي هيتخزن",
  "amount": null,
  "reply": "ردك الطبيعي والذكي للمستخدم",
  "suggestion": null
}

لو مصروف وفيه مبلغ واضح: حط amount كرقم (مثال: 150)، وإلا null.
لو في اقتراح عملي قصير جداً: حط suggestion كنص، وإلا null.
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
