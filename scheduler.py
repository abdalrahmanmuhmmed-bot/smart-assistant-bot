import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from firebase_db import get_due_reminders, mark_reminder_sent, get_current_time_cairo

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
                    f"⏰ *تنبيه موعد مهم:*\n\n"
                    f"{text}\n\n"
                    f"_{now_cairo.strftime('%I:%M %p — %d/%m/%Y')}_"
                )

                try:
                    await application.bot.send_message(
                        chat_id=user_id,
                        text=alert_text,
                        parse_mode="Markdown"
                    )
                    logger.info(f"[SCHEDULER] Sent reminder #{rem_id} to user {user_id}")
                except Exception as send_err:
                    logger.error(f"[SCHEDULER] Failed to send reminder #{rem_id}: {send_err}")

                # Handle recurrence or mark sent
                if recurring == "daily":
                    # Reschedule 24h ahead
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
