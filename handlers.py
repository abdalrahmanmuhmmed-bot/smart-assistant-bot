import os
import io
import re
import asyncio
import logging
from contextlib import asynccontextmanager
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes
from google import genai
from google.genai import types

import firebase_db as database
from ai_agent import UserAIAgent

logger = logging.getLogger(__name__)


def format_for_telegram(text: str) -> str:
    """
    Converts standard Markdown into valid, beautiful Telegram HTML.
    Prevents formatting breakage and ensures bold, italic, code render natively.
    """
    # 1. Protect and escape HTML entities
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # 2. Multi-line code blocks: ```code``` -> <pre>code</pre>
    text = re.sub(r"```(?:[a-zA-Z0-9_-]+)?\n?(.*?)```", r"<pre>\1</pre>", text, flags=re.DOTALL)
    # 3. Inline code: `code` -> <code>code</code>
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    # 4. Bold: **text** or __text__ -> <b>text</b>
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__([^_]+)__", r"<b>\1</b>", text)
    # 5. Italic: *text* or _text_ -> <i>text</i> (when not part of a word or snake_case)
    text = re.sub(r"(?<![a-zA-Z0-9_*])\*([^*]+)\*(?![a-zA-Z0-9_*])", r"<i>\1</i>", text)
    text = re.sub(r"(?<![a-zA-Z0-9_])_([^_]+)_(?![a-zA-Z0-9_])", r"<i>\1</i>", text)
    # 6. Headers: # Header -> <b>Header</b>
    text = re.sub(r"^#{1,6}\s*(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)
    return text


async def send_formatted_reply(message, text: str):
    """
    Sends message using Telegram HTML parser.
    If Telegram raises any parsing error, falls back safely to plain text.
    """
    formatted_html = format_for_telegram(text)
    try:
        await message.reply_text(formatted_html, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"[FORMATTING] HTML parse failed: {e}. Falling back to plain text.")
        await message.reply_text(text)


@asynccontextmanager
async def typing_indicator(chat, interval: float = 4.0):
    """
    Context manager that immediately sends ChatAction.TYPING,
    then keeps sending it periodically approximately every `interval` seconds
    until the block exits, is cancelled, or raises an error.
    Guarantees clean task cancellation and cleanup.
    """
    if chat is None:
        yield None
        return

    # 1. Immediate dispatch before long-running processing
    try:
        await chat.send_action(ChatAction.TYPING)
    except Exception as e:
        logger.debug(f"[TYPING] Immediate send_action failed: {e}")

    # 2. Background recurring loop
    async def _loop():
        try:
            while True:
                await asyncio.sleep(interval)
                try:
                    await chat.send_action(ChatAction.TYPING)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.debug(f"[TYPING] Periodic send_action failed: {e}")
        except asyncio.CancelledError:
            pass

    task = asyncio.create_task(_loop())
    try:
        yield task
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


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
    async with typing_indicator(update.effective_chat, interval=4.0):
        try:
            agent = UserAIAgent(user_id)
            reply = await agent.process_message("جهزلي الملخص اليومي (Daily Briefing) للنهاردة بأهم الأولويات والتنبيهات والمهام القادمة")
            await send_formatted_reply(update.message, reply)
        except Exception as e:
            logger.error(f"[BRIEFING ERROR] {e}")
            await update.message.reply_text("عذراً، حصلت مشكلة أثناء تجهيز الملخص اليومي.")


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

    async with typing_indicator(update.effective_chat, interval=4.0):
        try:
            agent = UserAIAgent(user_id)
            reply = await agent.process_message(text)
            await send_formatted_reply(update.message, reply)
        except Exception as e:
            logger.error(f"[HANDLE_MESSAGE ERROR] {e}")
            await update.message.reply_text("عذراً، حصلت مشكلة صغيرة أثناء معالجة الرسالة.")


async def transcribe_voice(voice_bytes: bytes) -> str:
    """تحويل الرسالة الصوتية إلى نص عربي أو إنجليزي بدقة مع دعم نماذج بديلة عند الضغط"""
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    audio_part = types.Part.from_bytes(
        data=voice_bytes,
        mime_type="audio/ogg"
    )

    models_to_try = [
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-flash-latest"
    ]

    last_err = None
    for model_name in models_to_try:
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=[
                    audio_part,
                    "Transcribe this voice note accurately in the spoken language (Arabic or English). Return only the exact transcribed text, nothing else."
                ]
            )
            text = resp.text.strip()
            if text:
                return text
        except Exception as e:
            logger.warning(f"[VOICE] Transcription failed on {model_name}: {e}. Trying fallback...")
            last_err = e
            continue

    raise last_err or Exception("Could not transcribe voice note.")


# ── معالجة الرسايل الصوتية (Voice Notes) ────────────────────────────────────
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    async with typing_indicator(update.effective_chat, interval=4.0):
        try:
            voice = update.message.voice
            file = await context.bot.get_file(voice.file_id)
            voice_bytes = await file.download_as_bytearray()

            # تفريغ الصوت بنموذج الذكاء الاصطناعي (عربي / إنجليزي)
            transcribed_text = await transcribe_voice(bytes(voice_bytes))
            logger.info(f"[VOICE] Transcribed user {user_id}: {transcribed_text}")

            # معالجة النص المنطوق كرسالة عادية وتنفيذ المطلوب
            agent = UserAIAgent(user_id)
            reply = await agent.process_message(transcribed_text)

            full_reply = f"🎙️ <b>سمعتك بتقول / Heard:</b>\n<i>\"{transcribed_text}\"</i>\n\n{reply}"
            await send_formatted_reply(update.message, full_reply)

        except Exception as e:
            logger.error(f"[VOICE ERROR] {e}")
            await update.message.reply_text("عذراً، مقدرتش أسمع التسجيل الصوتي بوضوح أو كان في ضغط مؤقت في شبكة الذكاء الاصطناعي. جرب تسجل تاني أو تبعت كتابة.")
