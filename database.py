import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "assistant.db")


def init_db():
    """إنشاء قاعدة البيانات والجداول لو مش موجودة."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   INTEGER NOT NULL,
            category  TEXT NOT NULL,       -- task / idea / expense / goal
            content   TEXT NOT NULL,
            amount    REAL,                -- للمصاريف بس
            done      INTEGER DEFAULT 0,   -- 0 = لسه، 1 = خلص
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def add_item(user_id: int, category: str, content: str, amount: float = None) -> int:
    """أضف عنصر جديد وارجع الـ ID بتاعه."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO items (user_id, category, content, amount, created_at) VALUES (?,?,?,?,?)",
        (user_id, category, content, amount, datetime.now().isoformat())
    )
    item_id = c.lastrowid
    conn.commit()
    conn.close()
    return item_id


def get_items(user_id: int, category: str = None, done: int = 0) -> list:
    """اجلب العناصر حسب الكاتيجوري والحالة."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if category:
        c.execute(
            "SELECT id, category, content, amount, created_at FROM items WHERE user_id=? AND category=? AND done=? ORDER BY id DESC",
            (user_id, category, done)
        )
    else:
        c.execute(
            "SELECT id, category, content, amount, created_at FROM items WHERE user_id=? AND done=? ORDER BY id DESC",
            (user_id, done)
        )
    rows = c.fetchall()
    conn.close()
    return rows


def mark_done(user_id: int, item_id: int) -> bool:
    """علم على عنصر إنه خلص."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "UPDATE items SET done=1 WHERE id=? AND user_id=?",
        (item_id, user_id)
    )
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def delete_item(user_id: int, item_id: int) -> bool:
    """امسح عنصر."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM items WHERE id=? AND user_id=?", (item_id, user_id))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def get_weekly_summary(user_id: int) -> dict:
    """ملخص أسبوعي لكل الكاتيجوريز."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    summary = {}
    for cat in ["task", "idea", "expense", "goal"]:
        c.execute(
            "SELECT COUNT(*) FROM items WHERE user_id=? AND category=? AND done=0",
            (user_id, cat)
        )
        summary[cat] = c.fetchone()[0]

    # مجموع المصاريف
    c.execute(
        "SELECT SUM(amount) FROM items WHERE user_id=? AND category='expense' AND done=0",
        (user_id,)
    )
    total = c.fetchone()[0]
    summary["total_expenses"] = total or 0.0

    conn.close()
    return summary
