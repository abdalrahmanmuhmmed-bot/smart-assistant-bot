import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from database import add_item, get_items, mark_done, delete_item, get_weekly_summary
from categorizer import CATEGORY_LABELS, CATEGORY_EMOJIS
from ai import process_with_ai


async def _keep_typing(chat):
    """إبقاء علامة يكتب الآن ظاهرة طوال فترة تفكير الذكاء الاصطناعي"""
    while True:
        try:
            await chat.send_action(ChatAction.TYPING)
        except Exception:
            pass
        await asyncio.sleep(3.5)


# ── /start ─────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أهلاً! 👋 أنا مساعدك الشخصي.\n\n"
        "بعتلي أي حاجة وأنا هصنفها لوحدي:\n"
        "✅ مهام  💡 أفكار  💰 مصاريف  🎯 أهداف\n\n"
        "أو ابدأ بـ emoji عشان تحدد التصنيف بنفسك:\n"
        "  ✅ لازم أراجع الملف\n"
        "  💡 فكرة عن مشروع جديد\n"
        "  💰 صرفت 150 على أكل\n"
        "  🎯 أوصل لـ 10k متابع\n\n"
        "الأوامر:\n"
        "/list – اعرض كل حاجة\n"
        "/tasks – المهام بس\n"
        "/ideas – الأفكار\n"
        "/expenses – المصاريف\n"
        "/goals – الأهداف\n"
        "/summary – ملخص سريع\n"
        "/done [رقم] – خلص مهمة\n"
        "/delete [رقم] – امسح عنصر"
    )


# ── رسايل عادية → Gemini بيفهم ويصنف ─────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if text.startswith("/"):
        return

    # تشغيل علامة 'يكتب الآن...' في الخلفية باستمرار
    typing_task = asyncio.create_task(_keep_typing(update.effective_chat))
    try:
        result = await process_with_ai(text, user_id)
    finally:
        typing_task.cancel()

    category = result["category"]
    content  = result["content"]
    amount   = result["amount"]
    reply    = result["reply"]
    suggestion = result["suggestion"]

    item_id = add_item(user_id, category, content, amount)
    label   = CATEGORY_LABELS[category]

    # أزرار تصحيح التصنيف
    keyboard = [
        [
            InlineKeyboardButton("✅ مهمة", callback_data=f"recat:{item_id}:task"),
            InlineKeyboardButton("💡 فكرة", callback_data=f"recat:{item_id}:idea"),
        ],
        [
            InlineKeyboardButton("💰 مصروف", callback_data=f"recat:{item_id}:expense"),
            InlineKeyboardButton("🎯 هدف",   callback_data=f"recat:{item_id}:goal"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # بناء الرسالة
    full_reply = f"{reply}\n\n_{label}  •  #{item_id}_"
    if suggestion:
        full_reply += f"\n\n💬 {suggestion}"

    await update.message.reply_text(full_reply, reply_markup=reply_markup, parse_mode="Markdown")


# ── Callback: إعادة تصنيف ─────────────────────────────────────────────────
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("recat:"):
        _, item_id, new_cat = data.split(":")
        item_id = int(item_id)
        user_id = update.effective_user.id

        # جلب النص الأصلي وتحديث الكاتيجوري
        from database import DB_PATH
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT content FROM items WHERE id=? AND user_id=?", (item_id, user_id))
        row = c.fetchone()
        if row:
            from categorizer import detect_amount
            amount = detect_amount(row[0]) if new_cat == "expense" else None
            c.execute(
                "UPDATE items SET category=?, amount=? WHERE id=? AND user_id=?",
                (new_cat, amount, item_id, user_id)
            )
            conn.commit()
            label = CATEGORY_LABELS[new_cat]
            await query.edit_message_text(f"تم تغيير التصنيف إلى {label} ✔️\n#{item_id}")
        else:
            await query.edit_message_text("مش لاقي العنصر ده.")
        conn.close()

    elif data.startswith("done:"):
        item_id = int(data.split(":")[1])
        user_id = update.effective_user.id
        if mark_done(user_id, item_id):
            await query.edit_message_text(f"✅ تم! #{item_id} اتخلص")
        else:
            await query.edit_message_text("مش لاقي العنصر ده.")


# ── عرض القوائم ───────────────────────────────────────────────────────────
def _format_list(rows: list, title: str) -> str:
    if not rows:
        return f"{title}\n\nمفيش حاجة هنا لحد دلوقتي 😌"
    lines = [title, ""]
    for row in rows:
        item_id, cat, content, amount, created_at = row
        emoji = CATEGORY_EMOJIS.get(cat, "•")
        date = created_at[:10]
        line = f"{emoji} #{item_id}  {content}"
        if amount:
            line += f"  ({amount:.0f})"
        line += f"  _[{date}]_"
        lines.append(line)
    return "\n".join(lines)


async def list_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rows = get_items(user_id)
    await update.message.reply_text(_format_list(rows, "📋 كل حاجة عندك:"), parse_mode="Markdown")


async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rows = get_items(user_id, "task")
    await update.message.reply_text(_format_list(rows, "✅ المهام:"), parse_mode="Markdown")


async def list_ideas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rows = get_items(user_id, "idea")
    await update.message.reply_text(_format_list(rows, "💡 الأفكار:"), parse_mode="Markdown")


async def list_expenses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rows = get_items(user_id, "expense")
    await update.message.reply_text(_format_list(rows, "💰 المصاريف:"), parse_mode="Markdown")


async def list_goals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rows = get_items(user_id, "goal")
    await update.message.reply_text(_format_list(rows, "🎯 الأهداف:"), parse_mode="Markdown")


# ── ملخص ─────────────────────────────────────────────────────────────────
async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    s = get_weekly_summary(user_id)
    text = (
        "📊 ملخصك الآن:\n\n"
        f"✅ مهام متراكمة: {s['task']}\n"
        f"💡 أفكار محفوظة: {s['idea']}\n"
        f"🎯 أهداف شغالة: {s['goal']}\n"
        f"💰 مصاريف مسجلة: {s['expense']}  (مجموع: {s['total_expenses']:.0f})\n"
    )
    await update.message.reply_text(text)


# ── /done و /delete ────────────────────────────────────────────────────────
async def done_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("استخدم: /done [رقم]\nمثال: /done 5")
        return
    if mark_done(user_id, int(args[0])):
        await update.message.reply_text(f"✅ #{args[0]} اتخلص!")
    else:
        await update.message.reply_text("مش لاقي العنصر ده.")


async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("استخدم: /delete [رقم]\nمثال: /delete 5")
        return
    if delete_item(user_id, int(args[0])):
        await update.message.reply_text(f"🗑️ #{args[0]} اتمسح.")
    else:
        await update.message.reply_text("مش لاقي العنصر ده.")
