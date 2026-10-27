import os
import asyncio
from dotenv import load_dotenv
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from database import init_db
from handlers import (
    start,
    handle_message,
    handle_callback,
    list_all,
    list_tasks,
    list_ideas,
    list_expenses,
    list_goals,
    summary,
    done_cmd,
    delete_cmd,
)

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
PORT  = int(os.getenv("PORT", 8080))


# ── Simple Built-in Health check server for Render (Zero external dependencies) ──
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
        print(f"[WEB] Built-in health server running on port {PORT}")
        return server
    except OSError as e:
        print(f"[WEB WARNING] Could not bind port {PORT}: {e}. Continuing bot execution...")
        return None


async def main():
    if not TOKEN or TOKEN == "ضع_التوكن_هنا":
        print("[ERROR] No token found! Set BOT_TOKEN environment variable.")
        return

    init_db()
    print("[OK] Database ready.")

    # تشغيل سيرفر الـ health check
    await run_web_server()

    # تشغيل البوت
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start",    start))
    app.add_handler(CommandHandler("list",     list_all))
    app.add_handler(CommandHandler("tasks",    list_tasks))
    app.add_handler(CommandHandler("ideas",    list_ideas))
    app.add_handler(CommandHandler("expenses", list_expenses))
    app.add_handler(CommandHandler("goals",    list_goals))
    app.add_handler(CommandHandler("summary",  summary))
    app.add_handler(CommandHandler("done",     done_cmd))
    app.add_handler(CommandHandler("delete",   delete_cmd))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))

    print("[BOT] Polling started...")
    async with app:
        await app.start()
        await app.updater.start_polling()
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())


