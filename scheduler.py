import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from firebase_db import (
    get_due_reminders,
    mark_reminder_sent,
    get_current_time_cairo,
    get_users_for_morning_briefing,
    update_user_settings,
)
from handlers import send_formatted_to_chat

logger = logging.getLogger(__name__)
CAIRO_TZ = ZoneInfo("Africa/Cairo")


async def reminder_worker(application):
    """
    Background worker that checks for due reminders every 15 seconds
    and sends direct Telegram alerts to users.
    """
    logger.info("[SCHEDULER] Reminder worker started.")
    while True:
        try:
            now_cairo = get_current_time_cairo()
            now_iso = now_cairo.isoformat()
            due = get_due_reminders(now_iso)

            for rem in due:
                user_id = rem["user_id"]
                text = rem["reminder_text"]
                rem_id = rem["id"]
                recurring = rem.get("recurring", "none")

                alert_text = (
                    f"⏰ <b>تنبيه موعد مهم:</b>\n\n"
                    f"{text}\n\n"
                    f"<i>{now_cairo.strftime('%I:%M %p — %d/%m/%Y')}</i>"
                )

                try:
                    await send_formatted_to_chat(application.bot, user_id, alert_text)
                    logger.info(f"[SCHEDULER] Sent reminder #{rem_id} to user {user_id}")
                except Exception as send_err:
                    logger.error(f"[SCHEDULER] Failed to send reminder #{rem_id}: {send_err}")

                # Handle recurrence or mark sent
                if recurring == "daily":
                    try:
                        rem_dt = datetime.fromisoformat(rem["remind_at"])
                    except Exception:
                        rem_dt = now_cairo
                    next_iso = (rem_dt + timedelta(days=1)).isoformat()
                    mark_reminder_sent(rem_id, reschedule_iso=next_iso)
                elif recurring == "weekly":
                    try:
                        rem_dt = datetime.fromisoformat(rem["remind_at"])
                    except Exception:
                        rem_dt = now_cairo
                    next_iso = (rem_dt + timedelta(days=7)).isoformat()
                    mark_reminder_sent(rem_id, reschedule_iso=next_iso)
                else:
                    mark_reminder_sent(rem_id)

        except Exception as e:
            logger.error(f"[SCHEDULER ERROR] {e}")

        await asyncio.sleep(15)


async def morning_briefing_worker(application):
    """
    Background worker that runs every 30 seconds to check if any user is due
    for their proactive morning briefing.
    """
    from ai_agent import UserAIAgent

    logger.info("[SCHEDULER] Morning briefing worker started.")
    while True:
        try:
            now_cairo = get_current_time_cairo()
            current_hhmm = now_cairo.strftime("%H:%M")
            today_date = now_cairo.strftime("%Y-%m-%d")

            due_users = get_users_for_morning_briefing(current_hhmm, today_date)

            for u in due_users:
                user_id = u["user_id"]
                try:
                    logger.info(f"[SCHEDULER] Triggering proactive morning briefing for user {user_id}...")
                    # Mark briefing as sent today first to avoid double triggers
                    update_user_settings(user_id, last_briefing_date=today_date)

                    agent = UserAIAgent(user_id)
                    prompt = (
                        "أنت ترسل الآن الإيجاز الصباحي التلقائي اليومي (Proactive Morning Briefing) للمستخدم.\n"
                        "1. ابدأ بتحية صباحية مميزة ومشجعة مع ذكر تاريخ اليوم واليوم.\n"
                        "2. لخص أهم الأولويات والمهام النشطة ومواعيد تسليمها المقتربة.\n"
                        "3. اذكر أي مواعيد أو تذكيرات مجدولة لليوم.\n"
                        "4. اختم بكلمة تحفيزية إيجابية ومقتضبة لبدء اليوم بنشاط وطاقة."
                    )
                    reply = await agent.process_message(prompt)
                    header = "🌅 <b>إيجازك الصباحي اليومي:</b>\n\n"
                    await send_formatted_to_chat(application.bot, user_id, header + reply)
                    logger.info(f"[SCHEDULER] Successfully sent morning briefing to user {user_id}")
                except Exception as user_err:
                    logger.error(f"[SCHEDULER] Failed to send morning briefing to {user_id}: {user_err}")

        except Exception as e:
            logger.error(f"[SCHEDULER BRIEFING ERROR] {e}")

        await asyncio.sleep(30)
