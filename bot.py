import os
import asyncio
import logging
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


# ── Built-in Health check server for Render ──────────────────────────────────
async def handle_http(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    try:
        while True:
            line = await reader.readline()
            if not line or line == b"\r\n" or line == b"\n":
                break
        response = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"Content-Length: 2\r\n"
            b"Connection: close\r\n\r\n"
            b"OK"
        )
        writer.write(response)
        await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def run_web_server():
    try:
        server = await asyncio.start_server(handle_http, "0.0.0.0", PORT)
        logger.info(f"[WEB] Built-in health check server listening on port {PORT}")
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

    # تشغيل خادم المراقبة للبورت
    await run_web_server()

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
