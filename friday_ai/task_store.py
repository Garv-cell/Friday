import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


class TaskStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.tasks: List[Dict[str, Any]] = []
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self.tasks = data

    def _save(self) -> None:
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.tasks, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def list(self) -> List[Dict[str, Any]]:
        return list(reversed(self.tasks))

    def create(self, title: str, steps: List[str]) -> Dict[str, Any]:
        clean_steps = [str(step).strip() for step in steps if str(step).strip()]
        clean_steps = clean_steps[:30]
        task = {
            "id": uuid.uuid4().hex,
            "title": title.strip(),
            "status": "planned",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "steps": [
                {
                    "id": uuid.uuid4().hex,
                    "text": text,
                    "status": "pending",
                    "approved": False,
                    "requires_approval": True,
                }
                for text in clean_steps
            ],
        }
        self.tasks.append(task)
        self._save()
        return task

    def update(self, task_id: str, step_id: str, *, text: str | None = None,
               status: str | None = None, approved: bool | None = None) -> Dict[str, Any] | None:
        if status not in {None, "pending", "in_progress", "done"}:
            raise ValueError("Step status must be pending, in_progress, or done.")
        for task in self.tasks:
            if task["id"] != task_id:
                continue
            for step in task["steps"]:
                if step["id"] != step_id:
                    continue
                if text is not None:
                    if not text.strip():
                        raise ValueError("Step text cannot be empty.")
                    step["text"] = text.strip()
                next_approval = step["approved"] if approved is None else approved
                if status is not None:
                    if status in {"in_progress", "done"} and not next_approval:
                        raise ValueError("Approve a step before marking it in progress.")
                    step["status"] = status
                if approved is not None:
                    if not approved and step["status"] != "pending":
                        raise ValueError("Return a step to pending before revoking its approval.")
                    step["approved"] = approved
                task["status"] = (
                    "done" if task["steps"] and all(item["status"] == "done" for item in task["steps"])
                    else "in_progress" if any(item["status"] == "in_progress" for item in task["steps"])
                    else "planned"
                )
                self._save()
                return task
        return None

    def delete(self, task_id: str) -> bool:
        remaining = [task for task in self.tasks if task["id"] != task_id]
        if len(remaining) == len(self.tasks):
            return False
        self.tasks = remaining
        self._save()
        return True
