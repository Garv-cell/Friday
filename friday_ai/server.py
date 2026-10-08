import json
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
from urllib.parse import parse_qs, urlparse

from .agent import FridayAgent
from .config import JOBS_PATH, KNOWLEDGE_PATH, MEMORY_PATH, REMINDERS_PATH, SETTINGS_PATH, TASKS_PATH
from .job_store import JobStore
from .knowledge import KnowledgeBase, KnowledgeError
from .llm import PROVIDER_DEFAULTS
from .reminders import ReminderStore
from .settings import FridaySettings
from .task_store import TaskStore
from .tools import ToolError, run_shell
from .workflow import MultiAgentWorkflow


class FridayRequestHandler(BaseHTTPRequestHandler):
    server_version = "FridayServer/1.0"

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json({"status": "ok", "name": "Friday"})
        elif parsed.path == "/":
            try:
                content = Path(__file__).with_name("ui.html").read_text(encoding="utf-8")
            except OSError as exc:
                self._send_json({"error": f"Could not load Friday UI: {exc}"}, status=500)
                return
            encoded = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
        elif parsed.path == "/settings":
            self._send_json(self.server.settings.public())
        elif parsed.path == "/knowledge":
            self._send_json({"documents": self.server.knowledge.list_documents()})
        elif parsed.path == "/memory":
            query = parse_qs(parsed.query).get("q", [""])[0]
            self._send_json({"entries": self.server.agent.memory.entries(query, limit=40)})
        elif parsed.path == "/tasks":
            self._send_json({"tasks": self.server.tasks.list()})
        elif parsed.path == "/jobs":
            self._send_json({"jobs": self.server.jobs.list()})
        elif parsed.path == "/reminders":
            self._send_json({"reminders": self.server.reminders.list()})
        elif parsed.path == "/reminders/due":
            self._send_json({"reminders": self.server.reminders.due()})
        else:
            self._send_json({"error": "Not found"}, status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        data = self._read_json()
        if data is None:
            return

        if parsed.path in {"/chat", "/workflow"}:
            prompt = str(data.get("message", "")).strip()
            if not prompt:
                self._send_json({"error": "Message is required"}, status=400)
                return
            if parsed.path == "/workflow":
                self._send_json(self.server.workflow.run(prompt))
                return

            if self.server.agent._determine_tool(prompt) == "run_shell":
                command = self.server.agent._extract_command(prompt)
                if not command:
                    self._send_json({"error": "Specify a shell command to review and approve."}, status=400)
                    return
                self._send_json({
                    "reply": "This request would run a shell command. Review it and explicitly approve before execution.",
                    "requires_confirmation": True,
                    "command": command,
                })
                return
            self._send_json({"reply": self.server.agent.respond(prompt)})
        elif parsed.path == "/commands/execute":
            command = str(data.get("command", "")).strip()
            if not data.get("confirmed"):
                self._send_json({"error": "Explicit confirmation is required before running a command."}, status=403)
                return
            if not command or len(command) > 1000:
                self._send_json({"error": "Command must be between 1 and 1000 characters."}, status=400)
                return
            try:
                result = run_shell(command, timeout=15)
            except (OSError, ToolError, subprocess.TimeoutExpired, subprocess.SubprocessError) as exc:
                self._send_json({"error": f"Command failed: {exc}"}, status=400)
                return
            self._send_json({"result": result})
        elif parsed.path == "/settings":
            provider = str(data.get("provider", ""))
            model = data.get("model")
            try:
                settings = self.server.settings.update(provider, str(model) if model is not None else None)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self.server.agent.provider = settings["provider"]
            self.server.agent.model = settings["model"]
            self._send_json(settings)
        elif parsed.path == "/knowledge/index":
            source = str(data.get("path", "")).strip()
            if not source:
                self._send_json({"error": "Provide a file or directory path to index."}, status=400)
                return
            try:
                path = Path(source).expanduser()
                if path.is_dir():
                    indexed = self.server.knowledge.index_directory(path)
                else:
                    indexed = [self.server.knowledge.index_file(path)]
            except (KnowledgeError, OSError, ValueError) as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json({"indexed": indexed})
        elif parsed.path == "/knowledge/search":
            query = str(data.get("query", "")).strip()
            self._send_json({"results": self.server.knowledge.search(query)})
        elif parsed.path == "/tasks":
            title = str(data.get("title", "")).strip()
            if not title:
                self._send_json({"error": "Task title is required."}, status=400)
                return
            plan_prompt = (
                "You are Friday's task planner. Return an ordered list of 3 to 7 concise "
                "actionable steps for this task. One step per line, no numbering required. "
                "Do not execute actions.\n\nTask: " + title
            )
            plan = self.server.agent._call_ollama(plan_prompt)
            if plan:
                steps = [
                    line.strip().lstrip("-•0123456789. )")
                    for line in plan.splitlines() if line.strip()
                ]
            else:
                steps = [
                    "Review the goal, constraints, and required approvals",
                    "Gather the information or materials needed",
                    "Complete the requested work",
                    "Review the result and report limitations",
                ]
            self._send_json({"task": self.server.tasks.create(title, steps)}, status=201)
        elif parsed.path == "/jobs":
            if data.get("approved") is not True:
                self._send_json({"error": "Explicit confirmation is required before scheduling a job."}, status=403)
                return
            try:
                job = self.server.jobs.create(
                    str(data.get("title", "")),
                    str(data.get("prompt", "")),
                    str(data.get("run_at", "")),
                    str(data.get("recurrence", "none")),
                    approved=True,
                )
            except (ValueError, TypeError) as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json({"job": job}, status=201)
        elif parsed.path == "/reminders":
            try:
                reminder = self.server.reminders.create(
                    str(data.get("title", "")),
                    str(data.get("due_at", "")),
                    str(data.get("recurrence", "none")),
                )
            except (ValueError, TypeError) as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json({"reminder": reminder}, status=201)
        elif parsed.path.startswith("/reminders/") and parsed.path.endswith("/ack"):
            reminder_id = parsed.path.split("/")[2]
            reminder = self.server.reminders.acknowledge(reminder_id)
            if reminder is None:
                self._send_json({"error": "Reminder not found."}, status=404)
                return
            self._send_json({"reminder": reminder})
        elif parsed.path == "/memory/clear":
            self.server.agent.memory.clear()
            self._send_json({"cleared": True})
        else:
            self._send_json({"error": "Unsupported route"}, status=404)

    def do_PUT(self):
        parsed = urlparse(self.path)
        data = self._read_json()
        if data is None:
            return
        if parsed.path.startswith("/tasks/"):
            parts = parsed.path.strip("/").split("/")
            if len(parts) != 4 or parts[0] != "tasks" or parts[2] != "steps":
                self._send_json({"error": "Expected /tasks/{task_id}/steps/{step_id}."}, status=404)
                return
            task_id, step_id = parts[1], parts[3]
            try:
                task = self.server.tasks.update(
                    task_id,
                    step_id,
                    text=data.get("text"),
                    status=data.get("status"),
                    approved=data.get("approved"),
                )
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            if task is None:
                self._send_json({"error": "Task or step not found."}, status=404)
                return
            self._send_json({"task": task})
        elif parsed.path == "/memory":
            try:
                index = int(data.get("index", -1))
            except (TypeError, ValueError):
                self._send_json({"error": "Memory index must be an integer."}, status=400)
                return
            content = str(data.get("content", ""))
            if not content.strip():
                self._send_json({"error": "Memory content cannot be empty."}, status=400)
                return
            if not self.server.agent.memory.update(index, content):
                self._send_json({"error": "Memory entry not found."}, status=404)
                return
            self._send_json({"updated": True})
        else:
            self._send_json({"error": "Unsupported route"}, status=404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path == "/memory":
            try:
                index = int(parse_qs(parsed.query).get("index", ["-1"])[0])
            except ValueError:
                self._send_json({"error": "Memory index must be an integer."}, status=400)
                return
            if not self.server.agent.memory.delete(index):
                self._send_json({"error": "Memory entry not found."}, status=404)
                return
            self._send_json({"deleted": True})
        elif parsed.path == "/knowledge":
            source = parse_qs(parsed.query).get("source", [""])[0]
            if not source or not self.server.knowledge.remove(source):
                self._send_json({"error": "Document not found in the index."}, status=404)
                return
            self._send_json({"deleted": True})
        elif parsed.path.startswith("/tasks/"):
            task_id = parsed.path.split("/")[2]
            if not self.server.tasks.delete(task_id):
                self._send_json({"error": "Task not found."}, status=404)
                return
            self._send_json({"deleted": True})
        elif parsed.path.startswith("/reminders/"):
            reminder_id = parsed.path.split("/")[2]
            if not self.server.reminders.delete(reminder_id):
                self._send_json({"error": "Reminder not found."}, status=404)
                return
            self._send_json({"deleted": True})
        elif parsed.path.startswith("/jobs/"):
            job_id = parsed.path.split("/")[2]
            if not self.server.jobs.delete(job_id):
                self._send_json({"error": "Scheduled job not found."}, status=404)
                return
            self._send_json({"deleted": True})
        else:
            self._send_json({"error": "Unsupported route"}, status=404)

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 1_000_000:
                self._send_json({"error": "JSON request body must be between 1 byte and 1 MB."}, status=400)
                return None
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json({"error": "Invalid JSON payload."}, status=400)
            return None
        if not isinstance(data, dict):
            self._send_json({"error": "JSON payload must be an object."}, status=400)
            return None
        return data

    def _send_json(self, payload, status=200):
        response = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, *args):
        return


class FridayServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765, model: str | None = None,
                 provider: str | None = None):
        self.host = host
        self.port = port
        self.settings = FridaySettings(SETTINGS_PATH)
        public_settings = self.settings.public()
        if provider:
            selected_model = model or (
                public_settings["model"]
                if provider == public_settings["provider"]
                else PROVIDER_DEFAULTS[provider]
            )
            public_settings = self.settings.update(provider, selected_model)
        elif model:
            public_settings["model"] = model
        self.agent = FridayAgent(
            model=public_settings["model"],
            provider=public_settings["provider"],
            memory_path=MEMORY_PATH,
        )
        self.knowledge = KnowledgeBase(KNOWLEDGE_PATH)
        self.agent.knowledge = self.knowledge
        self.tasks = TaskStore(TASKS_PATH)
        self.reminders = ReminderStore(REMINDERS_PATH)
        self.jobs = JobStore(JOBS_PATH)
        self.workflow = MultiAgentWorkflow(self.agent)

    def _run_jobs(self, stop_event: Event) -> None:
        while not stop_event.is_set():
            for job in self.jobs.claim_due():
                try:
                    result = self.agent.respond(job["prompt"])
                except (OSError, RuntimeError, ValueError) as exc:
                    result = f"Scheduled task failed: {exc}"
                self.jobs.complete(job["id"], result)
            stop_event.wait(10)

    def run(self):
        httpd = ThreadingHTTPServer((self.host, self.port), FridayRequestHandler)
        httpd.agent = self.agent
        httpd.workflow = self.workflow
        httpd.settings = self.settings
        httpd.knowledge = self.knowledge
        httpd.tasks = self.tasks
        httpd.reminders = self.reminders
        httpd.jobs = self.jobs
        print(f"Friday server is running at http://{self.host}:{self.port}")
        stop_event = Event()
        Thread(target=self._run_jobs, args=(stop_event,), daemon=True).start()
        httpd.serve_forever()
