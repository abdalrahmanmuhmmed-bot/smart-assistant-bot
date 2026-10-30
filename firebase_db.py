import os
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, List, Dict, Any

import firebase_admin
from firebase_admin import credentials, firestore
import database as sqlite_db

logger = logging.getLogger(__name__)
CAIRO_TZ = ZoneInfo("Africa/Cairo")

_firestore_client = None
_init_attempted = False


def get_current_time_cairo() -> datetime:
    return datetime.now(CAIRO_TZ)


def get_firestore_client():
    global _firestore_client, _init_attempted
    if _firestore_client is not None:
        return _firestore_client
    if _init_attempted:
        return None

    _init_attempted = True

    cred = None
    cred_json_str = os.getenv("FIREBASE_CREDENTIALS_JSON")
    key_file_path = os.getenv("FIREBASE_KEY_PATH", os.path.join(os.path.dirname(__file__), "firebase_key.json"))

    try:
        if cred_json_str:
            cred_dict = json.loads(cred_json_str)
            cred = credentials.Certificate(cred_dict)
        elif os.path.exists(key_file_path):
            cred = credentials.Certificate(key_file_path)

        if cred:
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            _firestore_client = firestore.client()
            logger.info("Firebase Firestore connected successfully.")
            return _firestore_client
    except Exception as e:
        logger.error(f"Failed to initialize Firebase Firestore: {e}")

    logger.warning("Firebase credentials not found or invalid. Falling back to SQLite.")
    return None


def is_firebase_active() -> bool:
    return get_firestore_client() is not None


# ─── Tasks Operations ────────────────────────────────────────────────────────

def create_task(user_id: int, title: str, description: str = "", project: str = "عام",
                priority: str = "Medium", deadline: str = "") -> dict:
    db = get_firestore_client()
    if not db:
        return sqlite_db.create_task(user_id, title, description, project, priority, deadline)

    now_iso = get_current_time_cairo().isoformat()
    doc_ref = db.collection("tasks").document()
    task_data = {
        "id": doc_ref.id,
        "user_id": user_id,
        "title": title,
        "description": description or "",
        "project": project or "عام",
        "priority": priority or "Medium",
        "status": "pending",
        "deadline": deadline or "",
        "created_at": now_iso,
        "updated_at": now_iso
    }
    doc_ref.set(task_data)
    return {"id": doc_ref.id, "title": title, "priority": priority, "deadline": deadline, "status": "pending"}


def update_task_status(user_id: int, task_id: Any, status: str) -> bool:
    db = get_firestore_client()
    if not db:
        return sqlite_db.update_task_status(user_id, int(task_id) if str(task_id).isdigit() else task_id, status)

    try:
        doc_ref = db.collection("tasks").document(str(task_id))
        doc = doc_ref.get()
        if not doc.exists or doc.to_dict().get("user_id") != user_id:
            return False
        now_iso = get_current_time_cairo().isoformat()
        doc_ref.update({"status": status, "updated_at": now_iso})
        return True
    except Exception as e:
        logger.error(f"Firestore update_task_status error: {e}")
        return False


def list_tasks(user_id: int, status: str = None, project: str = None, limit: int = 15) -> list:
    db = get_firestore_client()
    if not db:
        return sqlite_db.list_tasks(user_id, status, project, limit)

    query = db.collection("tasks").where(filter=firestore.FieldFilter("user_id", "==", user_id))
    if status:
        query = query.where(filter=firestore.FieldFilter("status", "==", status))

    docs = query.stream()
    tasks = []
    for d in docs:
        item = d.to_dict()
        item["id"] = d.id
        if not status and item.get("status") in ("completed", "cancelled"):
            continue
        if project and item.get("project") != project:
            continue
        tasks.append(item)

    # Sort in memory: Priority (Critical -> High -> Medium -> Low), then created_at DESC
    priority_order = {"Critical": 1, "High": 2, "Medium": 3, "Low": 4}
    tasks.sort(key=lambda x: (priority_order.get(x.get("priority", "Medium"), 5), -(datetime.fromisoformat(x.get("created_at", "1970-01-01T00:00:00+00:00")).timestamp())))
    return tasks[:limit]


def delete_task(user_id: int, task_id: Any) -> bool:
    db = get_firestore_client()
    if not db:
        return sqlite_db.delete_task(user_id, int(task_id) if str(task_id).isdigit() else task_id)

    try:
        doc_ref = db.collection("tasks").document(str(task_id))
        doc = doc_ref.get()
        if not doc.exists or doc.to_dict().get("user_id") != user_id:
            return False
        doc_ref.delete()
        return True
    except Exception as e:
        logger.error(f"Firestore delete_task error: {e}")
        return False


# ─── Reminders Operations ────────────────────────────────────────────────────

def create_reminder(user_id: int, reminder_text: str, remind_at_iso: str,
                    task_id: Any = None, recurring: str = "none") -> dict:
    db = get_firestore_client()
    if not db:
        return sqlite_db.create_reminder(user_id, reminder_text, remind_at_iso, task_id, recurring)

    now_iso = get_current_time_cairo().isoformat()
    doc_ref = db.collection("reminders").document()
    rem_data = {
        "id": doc_ref.id,
        "user_id": user_id,
        "task_id": str(task_id) if task_id else None,
        "reminder_text": reminder_text,
        "remind_at": remind_at_iso,
        "recurring": recurring or "none",
        "status": "pending",
        "created_at": now_iso
    }
    doc_ref.set(rem_data)
    return {"id": doc_ref.id, "text": reminder_text, "remind_at": remind_at_iso, "recurring": recurring}


def list_pending_reminders(user_id: int) -> list:
    db = get_firestore_client()
    if not db:
        return sqlite_db.list_pending_reminders(user_id)

    query = (
        db.collection("reminders")
        .where(filter=firestore.FieldFilter("user_id", "==", user_id))
        .where(filter=firestore.FieldFilter("status", "==", "pending"))
    )
    docs = query.stream()
    reminders = [d.to_dict() | {"id": d.id} for d in docs]
    reminders.sort(key=lambda x: x.get("remind_at", ""))
    return reminders


def cancel_reminder(user_id: int, reminder_id: Any) -> bool:
    db = get_firestore_client()
    if not db:
        return sqlite_db.cancel_reminder(user_id, int(reminder_id) if str(reminder_id).isdigit() else reminder_id)

    try:
        doc_ref = db.collection("reminders").document(str(reminder_id))
        doc = doc_ref.get()
        if not doc.exists or doc.to_dict().get("user_id") != user_id:
            return False
        doc_ref.update({"status": "cancelled"})
        return True
    except Exception as e:
        logger.error(f"Firestore cancel_reminder error: {e}")
        return False


def get_due_reminders(current_time_iso: str) -> list:
    db = get_firestore_client()
    if not db:
        return sqlite_db.get_due_reminders(current_time_iso)

    query = (
        db.collection("reminders")
        .where(filter=firestore.FieldFilter("status", "==", "pending"))
        .where(filter=firestore.FieldFilter("remind_at", "<=", current_time_iso))
    )
    docs = query.stream()
    return [d.to_dict() | {"id": d.id} for d in docs]


def mark_reminder_sent(reminder_id: Any, reschedule_iso: str = None) -> None:
    db = get_firestore_client()
    if not db:
        return sqlite_db.mark_reminder_sent(int(reminder_id) if str(reminder_id).isdigit() else reminder_id, reschedule_iso)

    try:
        doc_ref = db.collection("reminders").document(str(reminder_id))
        if reschedule_iso:
            doc_ref.update({"remind_at": reschedule_iso})
        else:
            doc_ref.update({"status": "sent"})
    except Exception as e:
        logger.error(f"Firestore mark_reminder_sent error: {e}")


# ─── Memory Operations ───────────────────────────────────────────────────────

def save_memory(user_id: int, category: str, content: str) -> dict:
    db = get_firestore_client()
    if not db:
        return sqlite_db.save_memory(user_id, category, content)

    now_iso = get_current_time_cairo().isoformat()
    doc_ref = db.collection("memories").document()
    mem_data = {
        "id": doc_ref.id,
        "user_id": user_id,
        "category": category or "fact",
        "content": content,
        "created_at": now_iso
    }
    doc_ref.set(mem_data)
    return {"id": doc_ref.id, "category": category, "content": content}


def list_memories(user_id: int, category: str = None, limit: int = 20) -> list:
    db = get_firestore_client()
    if not db:
        return sqlite_db.list_memories(user_id, category, limit)

    query = db.collection("memories").where(filter=firestore.FieldFilter("user_id", "==", user_id))
    if category:
        query = query.where(filter=firestore.FieldFilter("category", "==", category))
    docs = query.stream()
    memories = [d.to_dict() | {"id": d.id} for d in docs]
    memories.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return memories[:limit]


def delete_memory(user_id: int, memory_id: Any) -> bool:
    db = get_firestore_client()
    if not db:
        return sqlite_db.delete_memory(user_id, int(memory_id) if str(memory_id).isdigit() else memory_id)

    try:
        doc_ref = db.collection("memories").document(str(memory_id))
        doc = doc_ref.get()
        if not doc.exists or doc.to_dict().get("user_id") != user_id:
            return False
        doc_ref.delete()
        return True
    except Exception as e:
        logger.error(f"Firestore delete_memory error: {e}")
        return False


# ─── Expenses Operations ─────────────────────────────────────────────────────

def add_expense(user_id: int, amount: float, description: str, category: str = "عام", currency: str = "EGP") -> dict:
    db = get_firestore_client()
    if not db:
        return sqlite_db.add_expense(user_id, amount, description, category, currency)

    now_iso = get_current_time_cairo().isoformat()
    doc_ref = db.collection("expenses").document()
    exp_data = {
        "id": doc_ref.id,
        "user_id": user_id,
        "amount": float(amount),
        "currency": currency or "EGP",
        "category": category or "عام",
        "description": description,
        "created_at": now_iso
    }
    doc_ref.set(exp_data)
    return {"id": doc_ref.id, "amount": amount, "currency": currency, "category": category, "description": description}


def get_expenses_summary(user_id: int) -> dict:
    db = get_firestore_client()
    if not db:
        return sqlite_db.get_expenses_summary(user_id)

    query = db.collection("expenses").where(filter=firestore.FieldFilter("user_id", "==", user_id))
    docs = query.stream()
    expenses = [d.to_dict() | {"id": d.id} for d in docs]
    total = sum(float(e.get("amount", 0)) for e in expenses)
    expenses.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"total": total, "count": len(expenses), "recent": expenses[:5]}


# ─── Notes Operations ────────────────────────────────────────────────────────

def save_note(user_id: int, title: str, content: str, project: str = "", tags: str = "") -> dict:
    db = get_firestore_client()
    if not db:
        return sqlite_db.save_note(user_id, title, content, project, tags)

    now_iso = get_current_time_cairo().isoformat()
    doc_ref = db.collection("notes").document()
    note_data = {
        "id": doc_ref.id,
        "user_id": user_id,
        "title": title,
        "content": content,
        "project": project or "",
        "tags": tags or "",
        "created_at": now_iso
    }
    doc_ref.set(note_data)
    return {"id": doc_ref.id, "title": title, "content": content, "project": project}


def search_notes(user_id: int, query: str = "", limit: int = 10) -> list:
    db = get_firestore_client()
    if not db:
        return sqlite_db.search_notes(user_id, query, limit)

    query_ref = db.collection("notes").where(filter=firestore.FieldFilter("user_id", "==", user_id))
    docs = query_ref.stream()
    notes = [d.to_dict() | {"id": d.id} for d in docs]

    if query:
        q_lower = query.lower()
        notes = [
            n for n in notes
            if q_lower in n.get("title", "").lower()
            or q_lower in n.get("content", "").lower()
            or q_lower in n.get("tags", "").lower()
        ]

    notes.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return notes[:limit]


# ─── Projects Operations ─────────────────────────────────────────────────────

def create_project(user_id: int, name: str, description: str = "") -> dict:
    db = get_firestore_client()
    if not db:
        return sqlite_db.create_project(user_id, name, description)

    now_iso = get_current_time_cairo().isoformat()
    doc_ref = db.collection("projects").document()
    proj_data = {
        "id": doc_ref.id,
        "user_id": user_id,
        "name": name,
        "description": description or "",
        "status": "active",
        "created_at": now_iso
    }
    doc_ref.set(proj_data)
    return {"id": doc_ref.id, "name": name, "description": description}


def list_projects(user_id: int) -> list:
    db = get_firestore_client()
    if not db:
        return sqlite_db.list_projects(user_id)

    query = db.collection("projects").where(filter=firestore.FieldFilter("user_id", "==", user_id))
    docs = query.stream()
    projects = [d.to_dict() | {"id": d.id} for d in docs]
    projects.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return projects


# ─── Daily Briefing Data ─────────────────────────────────────────────────────

def get_briefing_data(user_id: int) -> dict:
    db = get_firestore_client()
    if not db:
        return sqlite_db.get_briefing_data(user_id)

    active_tasks = list_tasks(user_id, limit=7)
    pending_reminders = list_pending_reminders(user_id)
    today_prefix = get_current_time_cairo().strftime("%Y-%m-%d")
    today_reminders = [r for r in pending_reminders if r.get("remind_at", "").startswith(today_prefix)]
    memories = list_memories(user_id, limit=5)

    return {
        "current_time_cairo": get_current_time_cairo().strftime("%Y-%m-%d %I:%M %p (%A)"),
        "active_tasks": active_tasks,
        "today_reminders": today_reminders,
        "key_memories": [{"category": m.get("category"), "content": m.get("content")} for m in memories]
    }


# ─── User Settings & Morning Briefing Operations ─────────────────────────────

def upsert_user(user_id: int, first_name: str = "", username: str = "") -> dict:
    db = get_firestore_client()
    if not db:
        return sqlite_db.upsert_user(user_id, first_name, username)

    try:
        doc_ref = db.collection("users").document(str(user_id))
        doc = doc_ref.get()
        now_iso = get_current_time_cairo().isoformat()
        if doc.exists:
            data = doc.to_dict()
            updates = {}
            if first_name and data.get("first_name") != first_name:
                updates["first_name"] = first_name
            if username and data.get("username") != username:
                updates["username"] = username
            if updates:
                doc_ref.update(updates)
                data.update(updates)
            return data
        else:
            new_user = {
                "user_id": user_id,
                "first_name": first_name or "",
                "username": username or "",
                "briefing_enabled": True,
                "briefing_time": "08:30",
                "last_briefing_date": "",
                "created_at": now_iso
            }
            doc_ref.set(new_user)
            return new_user
    except Exception as e:
        logger.error(f"Firestore upsert_user error: {e}")
        return sqlite_db.upsert_user(user_id, first_name, username)


def get_user_settings(user_id: int) -> dict:
    db = get_firestore_client()
    if not db:
        return sqlite_db.get_user_settings(user_id)

    try:
        doc_ref = db.collection("users").document(str(user_id))
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        # Default user if not yet registered
        return {
            "user_id": user_id,
            "briefing_enabled": True,
            "briefing_time": "08:30",
            "last_briefing_date": ""
        }
    except Exception as e:
        logger.error(f"Firestore get_user_settings error: {e}")
        return sqlite_db.get_user_settings(user_id)


def update_user_settings(user_id: int, briefing_enabled: Optional[bool] = None,
                         briefing_time: Optional[str] = None, last_briefing_date: Optional[str] = None,
                         google_calendar_id: Optional[str] = None) -> bool:
    db = get_firestore_client()
    if not db:
        return sqlite_db.update_user_settings(user_id, briefing_enabled, briefing_time, last_briefing_date, google_calendar_id)

    try:
        doc_ref = db.collection("users").document(str(user_id))
        updates = {}
        if briefing_enabled is not None:
            updates["briefing_enabled"] = bool(briefing_enabled)
        if briefing_time is not None:
            updates["briefing_time"] = briefing_time
        if last_briefing_date is not None:
            updates["last_briefing_date"] = last_briefing_date
        if google_calendar_id is not None:
            updates["google_calendar_id"] = google_calendar_id

        if not updates:
            return True

        doc = doc_ref.get()
        if not doc.exists:
            # create doc if missing
            upsert_user(user_id)

        doc_ref.update(updates)
        return True
    except Exception as e:
        logger.error(f"Firestore update_user_settings error: {e}")
        return sqlite_db.update_user_settings(user_id, briefing_enabled, briefing_time, last_briefing_date)


def get_users_for_morning_briefing(current_hhmm: str, today_date: str) -> list:
    db = get_firestore_client()
    if not db:
        return sqlite_db.get_users_for_morning_briefing(current_hhmm, today_date)

    try:
        query = (
            db.collection("users")
            .where(filter=firestore.FieldFilter("briefing_enabled", "==", True))
            .where(filter=firestore.FieldFilter("briefing_time", "==", current_hhmm))
        )
        docs = query.stream()
        results = []
        for d in docs:
            item = d.to_dict()
            # Check that briefing hasn't already been sent today
            if item.get("last_briefing_date") != today_date:
                results.append(item)
        return results
    except Exception as e:
        logger.error(f"Firestore get_users_for_morning_briefing error: {e}")
        return sqlite_db.get_users_for_morning_briefing(current_hhmm, today_date)


# ─── Chat Conversation History Operations ───────────────────────────────────

def add_chat_message(user_id: int, role: str, content: str) -> None:
    db = get_firestore_client()
    if not db:
        return sqlite_db.add_chat_message(user_id, role, content)

    try:
        now_iso = get_current_time_cairo().isoformat()
        db.collection("chat_history").add({
            "user_id": user_id,
            "role": role,
            "content": content,
            "created_at": now_iso
        })
    except Exception as e:
        logger.error(f"Firestore add_chat_message error: {e}")
        sqlite_db.add_chat_message(user_id, role, content)


def get_recent_chat_history(user_id: int, limit: int = 10) -> list:
    db = get_firestore_client()
    if not db:
        return sqlite_db.get_recent_chat_history(user_id, limit)

    try:
        query = (
            db.collection("chat_history")
            .where(filter=firestore.FieldFilter("user_id", "==", user_id))
        )
        docs = query.stream()
        messages = [d.to_dict() for d in docs]
        messages.sort(key=lambda x: x.get("created_at", ""))
        recent = messages[-limit:]
        return [{"role": m.get("role"), "content": m.get("content")} for m in recent]
    except Exception as e:
        logger.error(f"Firestore get_recent_chat_history error: {e}")
        return sqlite_db.get_recent_chat_history(user_id, limit)


def clear_chat_history(user_id: int) -> bool:
    db = get_firestore_client()
    if not db:
        return sqlite_db.clear_chat_history(user_id)

    try:
        query = db.collection("chat_history").where(filter=firestore.FieldFilter("user_id", "==", user_id))
        docs = query.stream()
        for doc in docs:
            doc.reference.delete()
        sqlite_db.clear_chat_history(user_id)
        return True
    except Exception as e:
        logger.error(f"Firestore clear_chat_history error: {e}")
        return sqlite_db.clear_chat_history(user_id)

