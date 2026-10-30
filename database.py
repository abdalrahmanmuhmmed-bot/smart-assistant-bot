import sqlite3
import os
from datetime import datetime
from zoneinfo import ZoneInfo

DB_PATH = os.path.join(os.path.dirname(__file__), "assistant.db")
CAIRO_TZ = ZoneInfo("Africa/Cairo")


def get_current_time_cairo() -> datetime:
    return datetime.now(CAIRO_TZ)


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    c = conn.cursor()

    # 1. Projects
    c.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'active',
            created_at TEXT NOT NULL
        )
    """)

    # 2. Tasks
    c.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            project TEXT DEFAULT 'عام',
            priority TEXT DEFAULT 'Medium', -- Critical, High, Medium, Low
            status TEXT DEFAULT 'pending',   -- pending, in_progress, completed, cancelled, blocked
            deadline TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # 3. Reminders
    c.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            task_id INTEGER,
            reminder_text TEXT NOT NULL,
            remind_at TEXT NOT NULL,        -- ISO 8601 string in Cairo time
            recurring TEXT DEFAULT 'none',  -- none, daily, weekly
            status TEXT DEFAULT 'pending',   -- pending, sent, cancelled
            created_at TEXT NOT NULL
        )
    """)

    # 4. Personal Memory
    c.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,         -- preference, goal, fact, decision, routine
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # 5. Expenses
    c.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            currency TEXT DEFAULT 'EGP',
            category TEXT DEFAULT 'عام',
            description TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # 6. Notes & Ideas
    c.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            project TEXT,
            tags TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # 7. User Profiles & Settings
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            briefing_enabled INTEGER DEFAULT 1,
            briefing_time TEXT DEFAULT '08:30',
            last_briefing_date TEXT DEFAULT '',
            google_calendar_id TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)

    # Ensure google_calendar_id column exists if table was created previously
    try:
        c.execute("ALTER TABLE users ADD COLUMN google_calendar_id TEXT DEFAULT ''")
    except Exception:
        pass

    
    # 8. Multi-Turn Chat Conversation History
    c.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')

    conn.commit()
    conn.close()


# ─── Tasks Operations ────────────────────────────────────────────────────────

def create_task(user_id: int, title: str, description: str = "", project: str = "عام",
                priority: str = "Medium", deadline: str = "") -> dict:
    now_iso = get_current_time_cairo().isoformat()
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO tasks (user_id, title, description, project, priority, status, deadline, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?)
    """, (user_id, title, description, project or "عام", priority or "Medium", deadline or None, now_iso, now_iso))
    task_id = c.lastrowid
    conn.commit()
    conn.close()
    return {"id": task_id, "title": title, "priority": priority, "deadline": deadline, "status": "pending"}


def update_task_status(user_id: int, task_id: int, status: str) -> bool:
    now_iso = get_current_time_cairo().isoformat()
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE id = ? AND user_id = ?",
              (status, now_iso, task_id, user_id))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def list_tasks(user_id: int, status: str = None, project: str = None, limit: int = 15) -> list:
    conn = get_connection()
    c = conn.cursor()
    query = "SELECT * FROM tasks WHERE user_id = ?"
    params = [user_id]
    if status:
        query += " AND status = ?"
        params.append(status)
    else:
        query += " AND status != 'completed' AND status != 'cancelled'"
    if project:
        query += " AND project = ?"
        params.append(project)
    query += " ORDER BY CASE priority WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END, id DESC LIMIT ?"
    params.append(limit)
    c.execute(query, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def delete_task(user_id: int, task_id: int) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0


# ─── Reminders Operations ────────────────────────────────────────────────────

def create_reminder(user_id: int, reminder_text: str, remind_at_iso: str,
                    task_id: int = None, recurring: str = "none") -> dict:
    now_iso = get_current_time_cairo().isoformat()
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO reminders (user_id, task_id, reminder_text, remind_at, recurring, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'pending', ?)
    """, (user_id, task_id, reminder_text, remind_at_iso, recurring, now_iso))
    rem_id = c.lastrowid
    conn.commit()
    conn.close()
    return {"id": rem_id, "text": reminder_text, "remind_at": remind_at_iso, "recurring": recurring}


def list_pending_reminders(user_id: int) -> list:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM reminders WHERE user_id = ? AND status = 'pending' ORDER BY remind_at ASC
    """, (user_id,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def cancel_reminder(user_id: int, reminder_id: int) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE reminders SET status = 'cancelled' WHERE id = ? AND user_id = ?",
              (reminder_id, user_id))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def get_due_reminders(current_time_iso: str) -> list:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM reminders WHERE status = 'pending' AND remind_at <= ?
    """, (current_time_iso,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def mark_reminder_sent(reminder_id: int, reschedule_iso: str = None) -> None:
    conn = get_connection()
    c = conn.cursor()
    if reschedule_iso:
        c.execute("UPDATE reminders SET remind_at = ? WHERE id = ?", (reschedule_iso, reminder_id))
    else:
        c.execute("UPDATE reminders SET status = 'sent' WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()


# ─── Memory Operations ───────────────────────────────────────────────────────

def save_memory(user_id: int, category: str, content: str) -> dict:
    now_iso = get_current_time_cairo().isoformat()
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO memories (user_id, category, content, created_at)
        VALUES (?, ?, ?, ?)
    """, (user_id, category or "fact", content, now_iso))
    mem_id = c.lastrowid
    conn.commit()
    conn.close()
    return {"id": mem_id, "category": category, "content": content}


def list_memories(user_id: int, category: str = None, limit: int = 20) -> list:
    conn = get_connection()
    c = conn.cursor()
    if category:
        c.execute("SELECT * FROM memories WHERE user_id = ? AND category = ? ORDER BY id DESC LIMIT ?",
                  (user_id, category, limit))
    else:
        c.execute("SELECT * FROM memories WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                  (user_id, limit))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def delete_memory(user_id: int, memory_id: int) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM memories WHERE id = ? AND user_id = ?", (memory_id, user_id))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0


# ─── Expenses Operations ─────────────────────────────────────────────────────

def add_expense(user_id: int, amount: float, description: str, category: str = "عام", currency: str = "EGP") -> dict:
    now_iso = get_current_time_cairo().isoformat()
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO expenses (user_id, amount, currency, category, description, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, amount, currency, category, description, now_iso))
    exp_id = c.lastrowid
    conn.commit()
    conn.close()
    return {"id": exp_id, "amount": amount, "currency": currency, "category": category, "description": description}


def get_expenses_summary(user_id: int) -> dict:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT SUM(amount), COUNT(*) FROM expenses WHERE user_id = ?", (user_id,))
    total, count = c.fetchone()
    c.execute("SELECT * FROM expenses WHERE user_id = ? ORDER BY id DESC LIMIT 5", (user_id,))
    recent = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"total": total or 0.0, "count": count or 0, "recent": recent}


# ─── Notes Operations ────────────────────────────────────────────────────────

def save_note(user_id: int, title: str, content: str, project: str = "", tags: str = "") -> dict:
    now_iso = get_current_time_cairo().isoformat()
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO notes (user_id, title, content, project, tags, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, title, content, project, tags, now_iso))
    note_id = c.lastrowid
    conn.commit()
    conn.close()
    return {"id": note_id, "title": title, "content": content, "project": project}


def search_notes(user_id: int, query: str = "", limit: int = 10) -> list:
    conn = get_connection()
    c = conn.cursor()
    if query:
        pattern = f"%{query}%"
        c.execute("""
            SELECT * FROM notes WHERE user_id = ? AND (title LIKE ? OR content LIKE ? OR tags LIKE ?)
            ORDER BY id DESC LIMIT ?
        """, (user_id, pattern, pattern, pattern, limit))
    else:
        c.execute("SELECT * FROM notes WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# ─── Projects Operations ─────────────────────────────────────────────────────

def create_project(user_id: int, name: str, description: str = "") -> dict:
    now_iso = get_current_time_cairo().isoformat()
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO projects (user_id, name, description, status, created_at)
        VALUES (?, ?, ?, 'active', ?)
    """, (user_id, name, description, now_iso))
    proj_id = c.lastrowid
    conn.commit()
    conn.close()
    return {"id": proj_id, "name": name, "description": description}


def list_projects(user_id: int) -> list:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM projects WHERE user_id = ? ORDER BY id DESC", (user_id,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# ─── Daily Briefing Data ─────────────────────────────────────────────────────

def get_briefing_data(user_id: int) -> dict:
    conn = get_connection()
    c = conn.cursor()
    
    # Active tasks (prioritized)
    c.execute("""
        SELECT * FROM tasks WHERE user_id = ? AND status != 'completed' AND status != 'cancelled'
        ORDER BY CASE priority WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END, deadline ASC
        LIMIT 7
    """, (user_id,))
    active_tasks = [dict(r) for r in c.fetchall()]

    # Pending reminders for today
    today_prefix = get_current_time_cairo().strftime("%Y-%m-%d")
    c.execute("""
        SELECT * FROM reminders WHERE user_id = ? AND status = 'pending' AND remind_at LIKE ?
        ORDER BY remind_at ASC
    """, (user_id, f"{today_prefix}%"))
    today_reminders = [dict(r) for r in c.fetchall()]

    # Key memories
    c.execute("""
        SELECT category, content FROM memories WHERE user_id = ? ORDER BY id DESC LIMIT 5
    """, (user_id,))
    memories = [dict(r) for r in c.fetchall()]

    conn.close()
    return {
        "current_time_cairo": get_current_time_cairo().strftime("%Y-%m-%d %I:%M %p (%A)"),
        "active_tasks": active_tasks,
        "today_reminders": today_reminders,
        "key_memories": memories
    }


# ─── User Settings & Morning Briefing Operations ─────────────────────────────

def upsert_user(user_id: int, first_name: str = "", username: str = "") -> dict:
    now_iso = get_current_time_cairo().isoformat()
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO users (user_id, first_name, username, briefing_enabled, briefing_time, last_briefing_date, created_at)
        VALUES (?, ?, ?, 1, '08:30', '', ?)
        ON CONFLICT(user_id) DO UPDATE SET
            first_name = CASE WHEN ? != '' THEN ? ELSE first_name END,
            username = CASE WHEN ? != '' THEN ? ELSE username END
    """, (user_id, first_name, username, now_iso, first_name, first_name, username, username))
    conn.commit()
    conn.close()
    return get_user_settings(user_id)


def get_user_settings(user_id: int) -> dict:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {
        "user_id": user_id,
        "briefing_enabled": 1,
        "briefing_time": "08:30",
        "last_briefing_date": ""
    }


def update_user_settings(user_id: int, briefing_enabled: int = None,
                         briefing_time: str = None, last_briefing_date: str = None,
                         google_calendar_id: str = None) -> bool:
    conn = get_connection()
    c = conn.cursor()
    updates = []
    params = []
    if briefing_enabled is not None:
        updates.append("briefing_enabled = ?")
        params.append(1 if briefing_enabled else 0)
    if briefing_time is not None:
        updates.append("briefing_time = ?")
        params.append(briefing_time)
    if last_briefing_date is not None:
        updates.append("last_briefing_date = ?")
        params.append(last_briefing_date)
    if google_calendar_id is not None:
        updates.append("google_calendar_id = ?")
        params.append(google_calendar_id)

    if not updates:
        conn.close()
        return True

    params.append(user_id)
    c.execute(f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?", params)
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def get_users_for_morning_briefing(current_hhmm: str, today_date: str) -> list:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM users
        WHERE briefing_enabled = 1
          AND briefing_time = ?
          AND (last_briefing_date IS NULL OR last_briefing_date != ?)
    """, (current_hhmm, today_date))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# ─── Chat Conversation History Operations ───────────────────────────────────

def add_chat_message(user_id: int, role: str, content: str) -> None:
    now_iso = get_current_time_cairo().isoformat()
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO chat_history (user_id, role, content, created_at)
        VALUES (?, ?, ?, ?)
    ''', (user_id, role, content, now_iso))
    conn.commit()
    conn.close()


def get_recent_chat_history(user_id: int, limit: int = 10) -> list:
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT role, content FROM chat_history
        WHERE user_id = ?
        ORDER BY id DESC LIMIT ?
    ''', (user_id, limit))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    rows.reverse()
    return rows


def clear_chat_history(user_id: int) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM chat_history WHERE user_id = ?', (user_id,))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0

