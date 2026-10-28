import os
import asyncio
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)

from database import init_db
from scheduler import reminder_worker
from handlers import (
    start,
    briefing_cmd,
    list_tasks_cmd,
    list_reminders_cmd,
    expenses_cmd,
    memory_cmd,
    handle_message,
    handle_voice,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
PORT  = int(os.getenv("PORT", 8080))


# ── Built-in Robust Health check server for Render & UptimeRobot ──────────────
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()

    def log_message(self, format, *args):
        # منع إزعاج الـ terminal بطلبات الـ ping المستمرة
        pass


def start_health_server():
    try:
        server = HTTPServer(("0.0.0.0", PORT), HealthCheckHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info(f"[WEB] Robust health check server listening on port {PORT}")
        return server
    except OSError as e:
        logger.warning(f"[WEB WARNING] Could not bind port {PORT}: {e}. Continuing bot execution...")
        return None


async def main():
    if not TOKEN or TOKEN == "ضع_التوكن_هنا":
        logger.error("[ERROR] No BOT_TOKEN found! Check your .env file.")
        return

    init_db()
    logger.info("[DB] Database and tables verified.")

    # تشغيل خادم المراقبة للبورت (يدعم GET و HEAD لـ UptimeRobot)
    start_health_server()

    # بناء تطبيق التيليجرام
    app = ApplicationBuilder().token(TOKEN).build()

    # تسجيل الأوامر
    app.add_handler(CommandHandler("start",     start))
    app.add_handler(CommandHandler("help",      start))
    app.add_handler(CommandHandler("briefing",  briefing_cmd))
    app.add_handler(CommandHandler("tasks",     list_tasks_cmd))
    app.add_handler(CommandHandler("reminders", list_reminders_cmd))
    app.add_handler(CommandHandler("expenses",  expenses_cmd))
    app.add_handler(CommandHandler("memory",    memory_cmd))

    # تسجيل الرسايل النصية والصوتية
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    logger.info("[BOT] Starting Telegram polling & background reminder worker...")
    async with app:
        await app.start()
        await app.updater.start_polling()

        # تشغيل محرك التنبيهات في الخلفية
        reminder_task = asyncio.create_task(reminder_worker(app))

        try:
            await asyncio.Event().wait()
        finally:
            reminder_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
