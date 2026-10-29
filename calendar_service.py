import os
import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, List, Dict, Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)
CAIRO_TZ = ZoneInfo("Africa/Cairo")
SCOPES = ["https://www.googleapis.com/auth/calendar"]

_service = None
_init_attempted = False


def get_calendar_service():
    global _service, _init_attempted
    if _service is not None:
        return _service
    if _init_attempted:
        return None

    _init_attempted = True
    cred = None
    cred_json_str = os.getenv("FIREBASE_CREDENTIALS_JSON")
    key_file_path = os.getenv("FIREBASE_KEY_PATH", os.path.join(os.path.dirname(__file__), "firebase_key.json"))

    try:
        if cred_json_str:
            cred_dict = json.loads(cred_json_str)
            cred = Credentials.from_service_account_info(cred_dict, scopes=SCOPES)
        elif os.path.exists(key_file_path):
            cred = Credentials.from_service_account_file(key_file_path, scopes=SCOPES)

        if cred:
            _service = build("calendar", "v3", credentials=cred, cache_discovery=False)
            logger.info("Google Calendar API client initialized successfully.")
            return _service
    except Exception as e:
        logger.error(f"Failed to initialize Google Calendar API: {e}")

    return None


def is_calendar_available() -> bool:
    return get_calendar_service() is not None


def add_event(summary: str, start_iso: str, end_iso: str = "",
              description: str = "", calendar_id: str = "primary") -> dict:
    """
    Creates an event on Google Calendar.
    start_iso: ISO 8601 string (e.g. '2026-10-30T17:00:00')
    """
    service = get_calendar_service()
    if not service:
        return {"error": "Google Calendar service is not available."}

    try:
        # Parse or default end time (+1 hour if not specified)
        start_clean = start_iso.replace("Z", "")
        start_dt = datetime.fromisoformat(start_clean)
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=CAIRO_TZ)

        if end_iso:
            end_clean = end_iso.replace("Z", "")
            end_dt = datetime.fromisoformat(end_clean)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=CAIRO_TZ)
        else:
            end_dt = start_dt + timedelta(hours=1)

        event_body = {
            "summary": summary,
            "description": description or f"تمت الإضافة تلقائياً بواسطة مساعدي الذكي ({datetime.now(CAIRO_TZ).strftime('%Y-%m-%d %I:%M %p')})",
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": "Africa/Cairo"
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": "Africa/Cairo"
            },
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 30},
                    {"method": "popup", "minutes": 10}
                ]
            }
        }

        created = service.events().insert(calendarId=calendar_id, body=event_body).execute()
        return {
            "status": "success",
            "id": created.get("id"),
            "summary": created.get("summary"),
            "htmlLink": created.get("htmlLink"),
            "start": created.get("start", {}).get("dateTime")
        }
    except HttpError as http_err:
        logger.error(f"Google Calendar API HttpError: {http_err}")
        return {"error": f"Calendar API error: {http_err.reason}"}
    except Exception as e:
        logger.error(f"Error creating calendar event: {e}")
        return {"error": str(e)}


def list_events(calendar_id: str = "primary", max_results: int = 10,
                time_min_iso: str = "") -> list:
    """
    Lists upcoming events from Google Calendar starting from time_min_iso (or now).
    """
    service = get_calendar_service()
    if not service:
        return []

    try:
        if not time_min_iso:
            now_cairo = datetime.now(CAIRO_TZ)
            time_min_iso = now_cairo.isoformat()

        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min_iso,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        items = events_result.get("items", [])
        formatted = []
        for item in items:
            start = item.get("start", {}).get("dateTime", item.get("start", {}).get("date"))
            formatted.append({
                "id": item.get("id"),
                "summary": item.get("summary", "بدون عنوان"),
                "start": start,
                "description": item.get("description", ""),
                "htmlLink": item.get("htmlLink", "")
            })
        return formatted
    except Exception as e:
        logger.error(f"Error listing calendar events: {e}")
        return []


def delete_event(event_id: str, calendar_id: str = "primary") -> bool:
    """Deletes an event from Google Calendar."""
    service = get_calendar_service()
    if not service:
        return False
    try:
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error deleting calendar event #{event_id}: {e}")
        return False
