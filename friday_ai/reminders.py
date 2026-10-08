import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List


class ReminderStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.reminders: List[Dict[str, Any]] = []
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self.reminders = data

    def _save(self) -> None:
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.reminders, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def list(self) -> List[Dict[str, Any]]:
        return list(reversed(self.reminders))

    def create(self, title: str, due_at: str, recurrence: str = "none") -> Dict[str, Any]:
        if recurrence not in {"none", "daily", "weekly"}:
            raise ValueError("Recurrence must be none, daily, or weekly.")
        due = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
        if due.tzinfo is None:
            due = due.astimezone()
        reminder = {
            "id": uuid.uuid4().hex,
            "title": title.strip(),
            "due_at": due.isoformat(),
            "recurrence": recurrence,
            "active": True,
            "notified": False,
        }
        if not reminder["title"]:
            raise ValueError("Reminder title cannot be empty.")
        self.reminders.append(reminder)
        self._save()
        return reminder

    def due(self) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        return [
            item for item in self.reminders if item.get("active")
            and not item.get("notified")
            and datetime.fromisoformat(item["due_at"]).astimezone(timezone.utc) <= now
        ]

    def acknowledge(self, reminder_id: str) -> Dict[str, Any] | None:
        for reminder in self.reminders:
            if reminder["id"] != reminder_id:
                continue
            cadence = {"daily": timedelta(days=1), "weekly": timedelta(weeks=1)}
            if reminder["recurrence"] in cadence:
                next_due = datetime.fromisoformat(reminder["due_at"])
                now = datetime.now(next_due.tzinfo or timezone.utc)
                while next_due <= now:
                    next_due += cadence[reminder["recurrence"]]
                reminder["due_at"] = next_due.isoformat()
                reminder["notified"] = False
            else:
                reminder["active"] = False
                reminder["notified"] = True
            self._save()
            return reminder
        return None

    def delete(self, reminder_id: str) -> bool:
        remaining = [item for item in self.reminders if item["id"] != reminder_id]
        if len(remaining) == len(self.reminders):
            return False
        self.reminders = remaining
        self._save()
        return True
