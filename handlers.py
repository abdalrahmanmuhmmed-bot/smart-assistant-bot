import os
import io
import asyncio
import logging
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes
from google import genai
from google.genai import types

import database
from ai_agent import UserAIAgent

logger = logging.getLogger(__name__)


async def _keep_typing(chat):
    """إبقاء علامة يكتب الآن ظاهرة طوال فترة تفكير ومعالجة الذكاء الاصطناعي"""
    while True:
        try:
            await chat.send_action(ChatAction.TYPING)
        except Exception:
            pass
        await asyncio.sleep(3.5)


# ── /start ─────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_msg = (
        "أهلاً بيك يا فندم! 👋 أنا مساعدك وسكرتيرك الشخصي.\n\n"
        "أنا هنا عشان أنظملك حياتك ومهامك ومواعيدك، وأفتكر كل التفاصيل المهمة.\n\n"
        "تقدر تكلمني بصوتك أو كتابة بأي طريقة تحبها:\n"
        "• 'فكرني بكرة الساعة 5 أذاكر فيزيا'\n"
        "• 'ضيف مهمة تسليم التقرير يوم الخميس لأولويات الكلية'\n"
        "• 'صرفت 120 جنيه غدا النهاردة'\n"
        "• 'فكرة: نعمل مشروع ذكاء اصطناعي لكذا'\n"
        "• 'أنا بفضل أذاكر الفجر (هحفظها في ذاكرتك الدائمة)'\n\n"
        "الأوامر السريعة:\n"
        "/briefing – ملخصك اليومي وأولوياتك\n"
        "/tasks – قائمة المهام النشطة\n"
        "/reminders – التنبيهات المجدولة\n"
        "/expenses – ملخص المصاريف\n"
        "/memory – الحاجات اللي فاكرها عنك\n"
        "/help – دليل الاستخدام"
    )
    await update.message.reply_text(welcome_msg)


# ── /briefing ──────────────────────────────────────────────────────────────
async def briefing_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    typing_task = asyncio.create_task(_keep_typing(update.effective_chat))
    try:
        agent = UserAIAgent(user_id)
        reply = await agent.process_message("جهزلي الملخص اليومي (Daily Briefing) للنهاردة بأهم الأولويات والتنبيهات والمهام القادمة")
        await update.message.reply_text(reply)
    finally:
        typing_task.cancel()


# ── /tasks ─────────────────────────────────────────────────────────────────
async def list_tasks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tasks = database.list_tasks(user_id)
    if not tasks:
        await update.message.reply_text("معندكش أي مهام متأخرة أو معلقة حالياً، عاش! 🎉")
        return

    lines = ["📋 *قائمة مهامك الحالية:*", ""]
    priority_emojis = {"Critical": "🔥", "High": "⚡", "Medium": "📌", "Low": "☕"}

    for t in tasks:
        emoji = priority_emojis.get(t["priority"], "📌")
        deadline_str = f" ⏳ _{t['deadline']}_" if t["deadline"] else ""
        lines.append(f"{emoji} *#{t['id']}* {t['title']} ({t['project']}){deadline_str}")

    lines.append("\n_تقدر تقولي 'خلصت مهمة رقم كذا' أو 'احذف مهمة كذا'_")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /reminders ─────────────────────────────────────────────────────────────
async def list_reminders_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rems = database.list_pending_reminders(user_id)
    if not rems:
        await update.message.reply_text("مفيش أي تنبيهات مجدولة في الوقت الحالي 😌")
        return

    lines = ["⏰ *التنبيهات المجدولة القادمة:*", ""]
    for r in rems:
        dt_str = r["remind_at"].replace("T", " ")[:16]
        recur_str = " (تكرار يومي)" if r["recurring"] == "daily" else ""
        lines.append(f"• *#{r['id']}* {r['reminder_text']}\n  📅 {dt_str}{recur_str}")

    lines.append("\n_تقدر تقولي 'الغي التنبيه رقم كذا'_")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /expenses ──────────────────────────────────────────────────────────────
async def expenses_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    s = database.get_expenses_summary(user_id)
    total = s["total"]
    count = s["count"]
    recent = s["recent"]

    lines = [f"💰 *ملخص المصاريف:*", f"إجمالي ما تم تسجيله: *{total:.1f} EGP* ({count} عملية)", ""]
    if recent:
        lines.append("*آخر عمليات:*")
        for e in recent:
            lines.append(f"• {e['amount']} {e['currency']} — {e['description']} ({e['category']})")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /memory ────────────────────────────────────────────────────────────────
async def memory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    mems = database.list_memories(user_id)
    if not mems:
        await update.message.reply_text("لسه مسجلتش أي تفضيلات أو معلومات ثابتة في ذاكرتي. قولي مثلاً 'أنا بفضل كذا' وهسجلها.")
        return

    lines = ["🧠 *المعلومات والتفضيلات المحفوظة في ذاكرتي الدائمة:*", ""]
    for m in mems:
        lines.append(f"• [{m['category']}] {m['content']}")

    await update.message.reply_text("\n".join(lines))


# ── معالجة الرسايل النصية ──────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if text.startswith("/"):
        return

    typing_task = asyncio.create_task(_keep_typing(update.effective_chat))
    try:
        agent = UserAIAgent(user_id)
        reply = await agent.process_message(text)
        await update.message.reply_text(reply)
    except Exception as e:
        logger.error(f"[HANDLE_MESSAGE ERROR] {e}")
        await update.message.reply_text("عذراً، حصلت مشكلة صغيرة أثناء معالجة الرسالة.")
    finally:
        typing_task.cancel()


# ── معالجة الرسايل الصوتية (Voice Notes) ────────────────────────────────────
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    typing_task = asyncio.create_task(_keep_typing(update.effective_chat))

    try:
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)
        voice_bytes = await file.download_as_bytearray()

        # استخراج النص من الصوت باستخدام Gemini Multimodal
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        audio_part = types.Part.from_bytes(
            data=bytes(voice_bytes),
            mime_type="audio/ogg"
        )

        transcription_resp = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=[
                audio_part,
                "Transcribe this voice note accurately into Arabic. Return only the exact transcribed text, nothing else."
            ]
        )
        transcribed_text = transcription_resp.text.strip()
        logger.info(f"[VOICE] Transcribed user {user_id}: {transcribed_text}")

        # معالجة النص المنطوق كرسالة عادية
        agent = UserAIAgent(user_id)
        reply = await agent.process_message(transcribed_text)

        full_reply = f"🎙️ *سمعتك بتقول:*\n\"{transcribed_text}\"\n\n{reply}"
        await update.message.reply_text(full_reply, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"[VOICE ERROR] {e}")
        await update.message.reply_text(f"عذراً، مقدرتش أسمع التسجيل الصوتي بوضوح: {e}")
    finally:
        typing_task.cancel()
