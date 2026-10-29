import os
import json
import logging
from zoneinfo import ZoneInfo
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types

import firebase_db as database

load_dotenv()
logger = logging.getLogger(__name__)

CAIRO_TZ = ZoneInfo("Africa/Cairo")

BASE_SYSTEM_INSTRUCTION = """
# Personal AI Assistant — Master System Prompt

## 1. Identity and Mission
You are my personal AI assistant, life organizer, memory system, and execution partner.
Your mission is to help me organize my life, manage tasks and deadlines, remember important information, coordinate projects, manage my schedule, and automate repetitive activities.
You should not merely tell me what to do. When authorized tools are available, help me execute tasks, verify the results, and keep track of what remains unfinished.

Your priorities are:
- Reliability and accuracy.
- Organization and simplicity.
- Proactive assistance without unnecessary interruptions.
- Secure handling of personal information.
- Efficient execution and clear reporting.
- Maintaining my control over important decisions.

## 2. Communication Style & Languages
- **Full Bilingual Fluency (عربي & English):**
  * Seamlessly understand both Egyptian Arabic and English.
  * Always respond in the language used by the user:
    - If the user writes or speaks in English: respond in clear, natural, direct, and fluent English.
    - If the user writes or speaks in Arabic: respond in natural, warm, practical Egyptian Arabic (لهجة مصرية عملية ومهذبة وواضحة).
    - If the user mixes both languages: respond naturally matching their style.
  * All tools (tasks, reminders, memory, expenses, notes, projects, briefing) work universally whether the user requests them in Arabic or English.
- **Spelling and Grammar Standards:**
  * Maintain strict spelling, grammatical, and typographical accuracy in both languages.
  * In Arabic, use correct Hamzas (أ / إ / آ), proper Taa Marbouta (ة vs ه), and Alif Layyinah (ى vs ي).
- **Telegram Formatting Guidelines:**
  * Keep formatting clean, elegant, and readable on mobile screens.
  * Use bold for key titles/deadlines, code formatting for numbers/IDs, and bullet points for lists.
- Be friendly, direct, practical, and organized.
- Keep routine replies concise.
- Avoid overwhelming me with excessive information.
- Ask clarifying questions only when essential information is missing.
- Never ask me again for information that is already available in authorized memory.

## 3. Core Guidelines & Tools
- Timezone: Africa/Cairo.
- ALWAYS use the actual current date, time, and day provided in the runtime prompt to resolve relative dates (e.g. "بكرة الساعة 5", "الخميس الجاي", "كمان ساعتين").
- Format ISO timestamps for reminders as: YYYY-MM-DDTHH:MM:SS (in Cairo time).
- Never claim an action or reminder was completed without actually calling the corresponding tool and seeing a success result!
- Distinguish between:
  * A task (something that needs to be done, has status and priority).
  * A reminder (a scheduled notification at a specific date/time).
  * An idea/note (valuable information to save without an immediate action).
  * A personal memory (a confirmed fact, user preference, long-term goal, or recurring routine).
  * An expense (money spent or tracked).

## 4. Priority Framework for Tasks
- Critical: Urgent, high-impact tasks with immediate consequences.
- High: Important work with approaching deadlines.
- Medium: Meaningful tasks that can be scheduled.
- Low: Optional tasks with limited immediate impact.

## 5. Daily Briefing Structure
When requested or generating a daily briefing:
1. Today's date and day.
2. The 3 most important priorities (Critical/High).
3. Upcoming deadlines & scheduled reminders for today.
4. Next recommended action.
"""


class UserAIAgent:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    # ─── Tool 1: Tasks ────────────────────────────────────────────────────────
    def task_tool(self, action: str, title: str = "", task_id: int = None,
                  project: str = "عام", priority: str = "Medium",
                  deadline: str = "", status: str = "") -> dict:
        """
        Manage user tasks.
        Args:
            action: 'create', 'update_status', 'list', 'delete'
            title: Task title or description of what needs to be done
            task_id: ID of the task when updating or deleting
            project: Project or category name (e.g., 'الكلية', 'مشروع التخرج', 'شخصي', 'عام')
            priority: 'Critical', 'High', 'Medium', or 'Low'
            deadline: Deadline string or date/time (e.g., '2026-10-30 17:00')
            status: 'pending', 'in_progress', 'completed', 'cancelled', 'blocked'
        """
        try:
            if action == "create":
                if not title:
                    return {"error": "Title is required to create a task."}
                res = database.create_task(self.user_id, title=title, project=project,
                                           priority=priority, deadline=deadline)
                return {"status": "success", "message": f"Task #{res['id']} created", "task": res}

            elif action == "update_status":
                if not task_id or not status:
                    return {"error": "task_id and status are required."}
                ok = database.update_task_status(self.user_id, task_id, status)
                return {"status": "success" if ok else "failed", "task_id": task_id, "new_status": status}

            elif action == "list":
                tasks = database.list_tasks(self.user_id, status=status or None, project=project or None)
                return {"status": "success", "count": len(tasks), "tasks": tasks}

            elif action == "delete":
                if not task_id:
                    return {"error": "task_id is required to delete."}
                ok = database.delete_task(self.user_id, task_id)
                return {"status": "success" if ok else "not_found", "task_id": task_id}

            return {"error": f"Unknown action: {action}"}
        except Exception as e:
            return {"error": str(e)}

    # ─── Tool 2: Reminders ────────────────────────────────────────────────────
    def reminder_tool(self, action: str, reminder_text: str = "",
                      remind_at_iso: str = "", reminder_id: int = None,
                      recurring: str = "none") -> dict:
        """
        Schedule or manage real-time reminders.
        Args:
            action: 'create', 'list', 'cancel'
            reminder_text: What to remind the user about
            remind_at_iso: Exact ISO 8601 datetime for the alert in Cairo time (e.g., '2026-10-29T15:00:00')
            reminder_id: ID of the reminder to cancel
            recurring: 'none', 'daily', or 'weekly'
        """
        try:
            if action == "create":
                if not reminder_text or not remind_at_iso:
                    return {"error": "reminder_text and remind_at_iso are required."}
                res = database.create_reminder(self.user_id, reminder_text, remind_at_iso, recurring=recurring)
                return {"status": "success", "message": f"Reminder #{res['id']} scheduled for {remind_at_iso}", "reminder": res}

            elif action == "list":
                rems = database.list_pending_reminders(self.user_id)
                return {"status": "success", "count": len(rems), "reminders": rems}

            elif action == "cancel":
                if not reminder_id:
                    return {"error": "reminder_id is required."}
                ok = database.cancel_reminder(self.user_id, reminder_id)
                return {"status": "success" if ok else "failed", "reminder_id": reminder_id}

            return {"error": f"Unknown action: {action}"}
        except Exception as e:
            return {"error": str(e)}

    # ─── Tool 3: Personal Memory ─────────────────────────────────────────────
    def memory_tool(self, action: str, category: str = "fact",
                    content: str = "", memory_id: int = None) -> dict:
        """
        Save or recall personal memory, preferences, confirmed facts, and long-term goals.
        Args:
            action: 'save', 'list', 'delete'
            category: 'preference' (e.g. يفضل المذاكرة ليلاً), 'goal' (هدف طويل المدى), 'fact' (حقيقة شخصية), 'routine' (روتين يومي)
            content: The fact or preference to remember permanently
            memory_id: ID to delete
        """
        try:
            if action == "save":
                if not content:
                    return {"error": "content is required."}
                res = database.save_memory(self.user_id, category, content)
                return {"status": "success", "message": "Memory saved permanently.", "memory": res}

            elif action == "list":
                mems = database.list_memories(self.user_id, category=category or None)
                return {"status": "success", "count": len(mems), "memories": mems}

            elif action == "delete":
                if not memory_id:
                    return {"error": "memory_id required."}
                ok = database.delete_memory(self.user_id, memory_id)
                return {"status": "success" if ok else "not_found"}

            return {"error": f"Unknown action: {action}"}
        except Exception as e:
            return {"error": str(e)}

    # ─── Tool 4: Expenses ────────────────────────────────────────────────────
    def expense_tool(self, action: str, amount: float = 0.0, description: str = "",
                     category: str = "عام", currency: str = "EGP") -> dict:
        """
        Record and query personal expenses.
        Args:
            action: 'add', 'summary'
            amount: Numeric cost (e.g., 150.0)
            description: What was purchased
            category: 'طعام', 'مواصلات', 'دراسة', 'فواتير', 'ترفيه', 'عام'
            currency: Default 'EGP'
        """
        try:
            if action == "add":
                if amount <= 0 or not description:
                    return {"error": "amount and description are required."}
                res = database.add_expense(self.user_id, amount, description, category, currency)
                return {"status": "success", "message": f"Expense #{res['id']} recorded: {amount} {currency}", "expense": res}

            elif action == "summary":
                summary = database.get_expenses_summary(self.user_id)
                return {"status": "success", "summary": summary}

            return {"error": f"Unknown action: {action}"}
        except Exception as e:
            return {"error": str(e)}

    # ─── Tool 5: Notes & Knowledge ───────────────────────────────────────────
    def note_tool(self, action: str, title: str = "", content: str = "",
                  project: str = "", search_query: str = "") -> dict:
        """
        Store and retrieve valuable ideas, unstructured notes, meeting minutes, or project thoughts.
        Args:
            action: 'save', 'search', 'list'
            title: Short title of the note
            content: Full text of the idea/note
            project: Optional related project
            search_query: Search keywords
        """
        try:
            if action == "save":
                if not title or not content:
                    return {"error": "title and content are required."}
                res = database.save_note(self.user_id, title, content, project)
                return {"status": "success", "message": f"Note #{res['id']} saved", "note": res}

            elif action in ("search", "list"):
                notes = database.search_notes(self.user_id, query=search_query)
                return {"status": "success", "count": len(notes), "notes": notes}

            return {"error": f"Unknown action: {action}"}
        except Exception as e:
            return {"error": str(e)}

    # ─── Tool 6: Daily Briefing ──────────────────────────────────────────────
    def daily_briefing_tool(self) -> dict:
        """
        Retrieve complete data for today's briefing: date, active prioritized tasks, today's reminders, and core memory.
        """
        try:
            data = database.get_briefing_data(self.user_id)
            return {"status": "success", "briefing_data": data}
        except Exception as e:
            return {"error": str(e)}

    # ─── Main Execution ──────────────────────────────────────────────────────
    async def process_message(self, user_text: str) -> str:
        """
        Process the user message with Gemini using Automatic Function Calling (AFC).
        """
        now_cairo = database.get_current_time_cairo()
        current_time_str = now_cairo.strftime("%Y-%m-%d %I:%M %p (%A)")

        # Retrieve user key memories and active projects to inject as persistent context
        memories = database.list_memories(self.user_id, limit=7)
        memories_context = "\n".join([f"- [{m['category']}] {m['content']}" for m in memories]) if memories else "None yet."

        runtime_context = (
            f"{BASE_SYSTEM_INSTRUCTION}\n\n"
            f"## Runtime Environment\n"
            f"- Current Date & Time (Africa/Cairo): {current_time_str}\n"
            f"- Default Timezone: Africa/Cairo\n\n"
            f"## Known User Memory & Confirmed Preferences:\n"
            f"{memories_context}\n"
        )

        tools = [
            self.task_tool,
            self.reminder_tool,
            self.memory_tool,
            self.expense_tool,
            self.note_tool,
            self.daily_briefing_tool
        ]

        models_to_try = [
            "gemini-3.5-flash-lite",
            "gemini-3.5-flash",
            "gemini-flash-latest"
        ]

        last_err = None
        for model_name in models_to_try:
            try:
                chat = self.client.chats.create(
                    model=model_name,
                    config=types.GenerateContentConfig(
                        system_instruction=runtime_context,
                        tools=tools
                    )
                )

                response = chat.send_message(user_text)
                return response.text.strip()
            except Exception as e:
                logger.warning(f"[AI AGENT] Model {model_name} failed: {e}. Trying next fallback...")
                last_err = e
                continue

        logger.error(f"[AI AGENT ERROR] All models failed. Last error: {last_err}")
        return f"عذراً، حدث ضغط مؤقت في الخدمة: {last_err}"
