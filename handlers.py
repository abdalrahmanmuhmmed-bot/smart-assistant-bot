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


async def send_formatted_to_chat(bot, chat_id: int, text: str):
    """
    Sends message to a specific chat using Telegram HTML parser.
    Safely falls back to plain text if parsing fails.
    """
    formatted_html = format_for_telegram(text)
    try:
        await bot.send_message(chat_id=chat_id, text=formatted_html, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"[FORMATTING] HTML parse failed for chat {chat_id}: {e}. Falling back to plain text.")
        await bot.send_message(chat_id=chat_id, text=text)


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
    user = update.effective_user
    if user:
        database.upsert_user(user.id, first_name=user.first_name or "", username=user.username or "")

    welcome_msg = (
        "أهلاً بيك يا فندم! 👋 أنا مساعدك وسكرتيرك الشخصي.\n\n"
        "أنا هنا عشان أنظملك حياتك ومهامك ومواعيدك، وأفتكر كل التفاصيل المهمة.\n\n"
        "تقدر تكلمني بصوتك أو كتابة بأي طريقة تحبها:\n"
        "• 'فكرني بكرة الساعة 5 أذاكر فيزيا'\n"
        "• 'ضيف مهمة تسليم التقرير يوم الخميس لأولويات الكلية'\n"
        "• 'صرفت 120 جنيه غدا النهاردة'\n"
        "• 'فكرة: نعمل مشروع ذكاء اصطناعي لكذا'\n"
        "• 'أنا بفضل أذاكر الفجر (هحفظها في ذاكرتك الدائمة)'\n"
        "• 'عايز الإيجاز الصباحي يجيلي 9 الصبح'\n\n"
        "الأوامر السريعة:\n"
        "/briefing – ملخصك اليومي وأولوياتك\n"
        "/briefing_time – موعد الإيجاز الصباحي التلقائي\n"
        "/calendar – تقويم جوجل والمواعيد\n"
        "/tasks – قائمة المهام النشطة\n"
        "/reminders – التنبيهات المجدولة\n"
        "/expenses – ملخص المصاريف\n"
        "/memory – الحاجات اللي فاكرها عنك\n"
        "/status – حالة النظام وقاعدة البيانات\n"
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


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض حالة السيرفر وقاعدة البيانات السحابية الحالية"""
    user_id = update.effective_user.id
    user = update.effective_user
    if user:
        database.upsert_user(user.id, first_name=user.first_name or "", username=user.username or "")

    import firebase_db
    is_cloud = firebase_db.is_firebase_active()
    db_name = "Cloud Firestore ☁️" if is_cloud else "SQLite (Local) 📁"
    tasks_count = len(database.list_tasks(user_id))
    rems_count = len(database.list_pending_reminders(user_id))
    settings = database.get_user_settings(user_id)
    b_status = f"مفعّل يومياً في {settings.get('briefing_time', '08:30')} 🌅" if settings.get("briefing_enabled") else "معطّل 🔴"
    now_str = database.get_current_time_cairo().strftime("%I:%M %p - %Y-%m-%d")

    msg = (
        f"🟢 <b>حالة المساعد الذكي</b>\n\n"
        f"• <b>قاعدة البيانات:</b> {db_name}\n"
        f"• <b>الإيجاز الصباحي:</b> {b_status}\n"
        f"• <b>المهام النشطة:</b> {tasks_count} مهمة\n"
        f"• <b>التذكيرات القادمة:</b> {rems_count} تذكير\n"
        f"• <b>التوقيت الحالي (القاهرة):</b> {now_str}\n"
        f"• <b>الإصدار:</b> v2.3 (Proactive Briefing)"
    )
    await send_formatted_reply(update.message, msg)


async def briefing_time_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض أو تغيير موعد الإيجاز الصباحي التلقائي"""
    user_id = update.effective_user.id
    user = update.effective_user
    if user:
        database.upsert_user(user.id, first_name=user.first_name or "", username=user.username or "")

    args = context.args
    settings = database.get_user_settings(user_id)

    if not args:
        status_txt = "مفعّل 🟢" if settings.get("briefing_enabled") else "معطّل 🔴"
        current_time = settings.get("briefing_time", "08:30")
        msg = (
            f"🌅 <b>إعدادات الإيجاز الصباحي التلقائي</b>\n\n"
            f"• <b>الحالة:</b> {status_txt}\n"
            f"• <b>الموعد الحالي:</b> {current_time} بتوقيت القاهرة\n\n"
            f"لتغيير الموعد، أرسل:\n"
            f"<code>/briefing_time 09:00</code> (بصيغة 24 ساعة)\n"
            f"أو للتعطيل:\n"
            f"<code>/briefing_time off</code>\n"
            f"أو للتفعيل:\n"
            f"<code>/briefing_time on</code>\n\n"
            f"<i>(يمكنك أيضاً طلب ذلك في أي وقت بالحديث الطبيعي أو الفويس نوت)</i>"
        )
        await send_formatted_reply(update.message, msg)
        return

    sub = args[0].lower().strip()
    if sub in ("off", "disable", "تعطيل", "إيقاف"):
        database.update_user_settings(user_id, briefing_enabled=False)
        await send_formatted_reply(update.message, "✅ تم تعطيل الإيجاز الصباحي التلقائي.")
    elif sub in ("on", "enable", "تفعيل", "تشغيل"):
        database.update_user_settings(user_id, briefing_enabled=True)
        await send_formatted_reply(update.message, f"✅ تم تفعيل الإيجاز الصباحي التلقائي في موعده ({settings.get('briefing_time', '08:30')} بتوقيت القاهرة).")
    else:
        if len(sub) == 5 and sub[2] == ":" and sub[:2].isdigit() and sub[3:].isdigit():
            h, m = int(sub[:2]), int(sub[3:])
            if 0 <= h < 24 and 0 <= m < 60:
                database.update_user_settings(user_id, briefing_time=sub, briefing_enabled=True)
                await send_formatted_reply(update.message, f"✅ تم ضبط موعد الإيجاز الصباحي التلقائي يومياً على الساعة <b>{sub}</b> بتوقيت القاهرة 🌅")
                return
        await send_formatted_reply(update.message, "⚠️ صيغة غير صحيحة. يرجى كتابة الوقت مثل: <code>/briefing_time 08:30</code>")


async def calendar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض جدول Google Calendar القادم أو إرشادات الربط"""
    user_id = update.effective_user.id
    import calendar_service
    settings = database.get_user_settings(user_id)
    cal_id = settings.get("google_calendar_id")

    if not cal_id:
        msg = (
            "📅 <b>ربط تقويم جوجل (Google Calendar):</b>\n\n"
            "لم تقم بربط بريدك على تقويم جوجل بعد.\n\n"
            "<b>طريقة الربط في دقيقة:</b>\n"
            "1. افتح تقويم جوجل في المتصفح أو التطبيق: <code>calendar.google.com</code>\n"
            "2. ادخل على إعدادات تقويمك، وفي خانة (مشاركة مع أشخاص محددين) أضف إيميل السيرفر:\n"
            "<code>firebase-adminsdk-fbsvc@smartassistant-52554.iam.gserviceaccount.com</code>\n"
            "واختر صلاحية: <b>إجراء تغييرات على الأحداث</b>.\n\n"
            "3. ثم أرسل هنا إيميلك:\n"
            "<code>/set_calendar your_email@gmail.com</code>\n"
            "وسيتم ربط ومزامنة جدولك فوراً! 🚀"
        )
        await send_formatted_reply(update.message, msg)
        return

    events = calendar_service.list_events(calendar_id=cal_id, max_results=10)
    if not events:
        msg = (
            f"📅 <b>تقويم جوجل المرتبط:</b> <code>{cal_id}</code>\n\n"
            "لا توجد أحداث أو مواعيد قادمة مسجلة في التقويم حالياً.\n"
            "تقدر تقولي: <i>'ضيف ميعاد تسليمة كذا على الكاليندر يوم الخميس الساعة 5'</i> وهضيفهالك فوراً!"
        )
        await send_formatted_reply(update.message, msg)
        return

    lines = [f"📅 <b>أحداث ومواعيد تقويم جوجل القادمة ({cal_id}):</b>\n"]
    for ev in events:
        start_str = ev.get("start", "")
        try:
            dt = datetime.fromisoformat(start_str.replace("Z", ""))
            formatted_date = dt.strftime("%d/%m/%Y %I:%M %p")
        except Exception:
            formatted_date = start_str
        lines.append(f"• <b>{ev.get('summary')}</b>\n  ⏰ {formatted_date}")

    await send_formatted_reply(update.message, "\n".join(lines))


async def set_calendar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ربط إيميل تقويم جوجل"""
    user_id = update.effective_user.id
    args = context.args
    if not args or "@" not in args[0]:
        await send_formatted_reply(update.message, "يرجى كتابة بريدك الإلكتروني هكذا:\n<code>/set_calendar your_email@gmail.com</code>")
        return

    email = args[0].strip().lower()
    database.update_user_settings(user_id, google_calendar_id=email)
    msg = (
        f"✅ <b>تم حفظ بريد التقويم:</b> <code>{email}</code>\n\n"
        "تأكد فقط من عمل مشاركة لتقويمك في <code>calendar.google.com</code> مع إيميل الخدمة:\n"
        "<code>firebase-adminsdk-fbsvc@smartassistant-52554.iam.gserviceaccount.com</code>\n"
        "بصلاحية (إجراء تغييرات على الأحداث) لتبدأ المزامنة الكاملة! 🎯"
    )
    await send_formatted_reply(update.message, msg)


# ── معالجة الرسايل النصية ──────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        database.upsert_user(user.id, first_name=user.first_name or "", username=user.username or "")

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
    user = update.effective_user
    if user:
        database.upsert_user(user.id, first_name=user.first_name or "", username=user.username or "")

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


# ── معالجة الصور والمستندات المرئية (Vision & OCR) ──────────────────────────
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        database.upsert_user(user.id, first_name=user.first_name or "", username=user.username or "")

    user_id = update.effective_user.id
    async with typing_indicator(update.effective_chat, interval=4.0):
        try:
            if update.message.photo:
                photo_obj = update.message.photo[-1]
                file_id = photo_obj.file_id
            elif update.message.document:
                file_id = update.message.document.file_id
            else:
                return

            file = await context.bot.get_file(file_id)
            img_bytes = await file.download_as_bytearray()

            caption = (update.message.caption or "").strip()
            prompt = (
                f"أرسل المستخدم هذه الصورة مع التعليق التالي: '{caption}'.\n"
                "حلل الصورة بدقة متناهية:\n"
                "1. إذا كانت فاتورة أو إيصال: استخرج المبلغ والتصنيف واقترح تسجيله في المصاريف.\n"
                "2. إذا كانت شريحة أو إعلان أو جدول: استخرج مواعيد التسليمات (Deadlines) أو التكليفات ونظمها كمهام.\n"
                "3. إذا كانت مسألة أو سؤال أو رسم بياني: اشرحه وأجب عنه بدقة.\n"
                "4. إذا كانت لقطة شاشة لإعدادات (مثل جوجل كاليندر أو فايربيز): اشرح له بالضبط أين يضغط والخطوة التالية."
            ) if not caption else f"{caption}\n(حلل الصورة المرفقة وأجب بدقة أو نفذ المطلوب برمجياً)"

            agent = UserAIAgent(user_id)
            reply = await agent.process_message(prompt, image_bytes=bytes(img_bytes), mime_type="image/jpeg")
            await send_formatted_reply(update.message, reply)

        except Exception as e:
            logger.error(f"[PHOTO ERROR] {e}")
            await update.message.reply_text("عذراً، حدثت مشكلة أثناء معالجة الصورة. يرجى التأكد من وضوح الصورة والمحاولة مرة أخرى.")
