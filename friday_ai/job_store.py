import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List


class JobStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = Lock()
        self.jobs: List[Dict[str, Any]] = []
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self.jobs = data
        changed = False
        for job in self.jobs:
            if job.get("status") == "running":
                job["status"] = "scheduled"
                changed = True
        if changed:
            self._save()

    def _save(self) -> None:
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.jobs, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def list(self) -> List[Dict[str, Any]]:
        with self.lock:
            return list(reversed(self.jobs))

    def create(self, title: str, prompt: str, run_at: str, recurrence: str,
               approved: bool) -> Dict[str, Any]:
        if not approved:
            raise ValueError("Explicit approval is required before scheduling a job.")
        if recurrence not in {"none", "daily", "weekly"}:
            raise ValueError("Recurrence must be none, daily, or weekly.")
        due = datetime.fromisoformat(run_at.replace("Z", "+00:00"))
        if due.tzinfo is None:
            due = due.astimezone()
        clean_title = title.strip()
        clean_prompt = prompt.strip()
        if not clean_title or not clean_prompt:
            raise ValueError("Job title and prompt are required.")
        if len(clean_prompt) > 2000:
            raise ValueError("Scheduled job prompt must be at most 2000 characters.")
        job = {
            "id": uuid.uuid4().hex,
            "title": clean_title,
            "prompt": clean_prompt,
            "run_at": due.isoformat(),
            "recurrence": recurrence,
            "approved": True,
            "status": "scheduled",
            "last_result": "",
            "last_run_at": None,
        }
        with self.lock:
            self.jobs.append(job)
            self._save()
        return job

    def claim_due(self) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        with self.lock:
            due = [
                job for job in self.jobs
                if job["approved"] and job["status"] == "scheduled"
                and datetime.fromisoformat(job["run_at"]).astimezone(timezone.utc) <= now
            ]
            for job in due:
                job["status"] = "running"
            if due:
                self._save()
            return [dict(job) for job in due]

    def complete(self, job_id: str, result: str) -> Dict[str, Any] | None:
        cadence = {"daily": timedelta(days=1), "weekly": timedelta(weeks=1)}
        with self.lock:
            for job in self.jobs:
                if job["id"] != job_id:
                    continue
                job["last_result"] = result
                job["last_run_at"] = datetime.now(timezone.utc).isoformat()
                if job["recurrence"] in cadence:
                    next_run = datetime.fromisoformat(job["run_at"])
                    now = datetime.now(next_run.tzinfo or timezone.utc)
                    while next_run <= now:
                        next_run += cadence[job["recurrence"]]
                    job["run_at"] = next_run.isoformat()
                    job["status"] = "scheduled"
                else:
                    job["status"] = "completed"
                self._save()
                return dict(job)
        return None

    def delete(self, job_id: str) -> bool:
        with self.lock:
            remaining = [job for job in self.jobs if job["id"] != job_id]
            if len(remaining) == len(self.jobs):
                return False
            self.jobs = remaining
            self._save()
            return True
