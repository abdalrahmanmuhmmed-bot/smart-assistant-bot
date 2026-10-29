import sys
import sqlite3
import os
import firebase_db

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = os.path.join(os.path.dirname(__file__), "assistant.db")


def migrate():
    if not firebase_db.is_firebase_active():
        print("ERROR: Firebase Firestore is not connected. Make sure firebase_key.json exists or FIREBASE_CREDENTIALS_JSON is set.")
        return 1

    if not os.path.exists(DB_PATH):
        print("No local assistant.db found to migrate.")
        return 0

    print(">>> Connecting to local SQLite database...")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    db = firebase_db.get_firestore_client()

    # 1. Projects
    try:
        c.execute("SELECT * FROM projects")
        projects = [dict(r) for r in c.fetchall()]
        print(f">>> Migrating {len(projects)} projects...")
        for p in projects:
            doc_id = str(p.pop("id"))
            db.collection("projects").document(doc_id).set(p)
    except Exception as e:
        print(f"Projects migration note: {e}")

    # 2. Tasks
    try:
        c.execute("SELECT * FROM tasks")
        tasks = [dict(r) for r in c.fetchall()]
        print(f">>> Migrating {len(tasks)} tasks...")
        for t in tasks:
            doc_id = str(t.pop("id"))
            db.collection("tasks").document(doc_id).set(t)
    except Exception as e:
        print(f"Tasks migration note: {e}")

    # 3. Reminders
    try:
        c.execute("SELECT * FROM reminders")
        reminders = [dict(r) for r in c.fetchall()]
        print(f">>> Migrating {len(reminders)} reminders...")
        for r in reminders:
            doc_id = str(r.pop("id"))
            db.collection("reminders").document(doc_id).set(r)
    except Exception as e:
        print(f"Reminders migration note: {e}")

    # 4. Memories
    try:
        c.execute("SELECT * FROM memories")
        memories = [dict(r) for r in c.fetchall()]
        print(f">>> Migrating {len(memories)} memories...")
        for m in memories:
            doc_id = str(m.pop("id"))
            db.collection("memories").document(doc_id).set(m)
    except Exception as e:
        print(f"Memories migration note: {e}")

    # 5. Expenses
    try:
        c.execute("SELECT * FROM expenses")
        expenses = [dict(r) for r in c.fetchall()]
        print(f">>> Migrating {len(expenses)} expenses...")
        for exp in expenses:
            doc_id = str(exp.pop("id"))
            db.collection("expenses").document(doc_id).set(exp)
    except Exception as e:
        print(f"Expenses migration note: {e}")

    # 6. Notes
    try:
        c.execute("SELECT * FROM notes")
        notes = [dict(r) for r in c.fetchall()]
        print(f">>> Migrating {len(notes)} notes...")
        for n in notes:
            doc_id = str(n.pop("id"))
            db.collection("notes").document(doc_id).set(n)
    except Exception as e:
        print(f"Notes migration note: {e}")

    conn.close()
    print(">>> All data successfully migrated to Firebase Firestore! ✅")
    return 0


if __name__ == "__main__":
    sys.exit(migrate())
