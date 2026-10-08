import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from threading import Event
from pathlib import Path
from unittest.mock import patch

from docx import Document
from pypdf import PdfWriter

from friday_ai.agent import FridayAgent
from friday_ai.knowledge import KnowledgeBase
from friday_ai.job_store import JobStore
from friday_ai.llm import ModelClient, PROVIDER_DEFAULTS
from friday_ai.memory import MemoryStore
from friday_ai.reminders import ReminderStore
from friday_ai.server import FridayRequestHandler
from friday_ai.server import FridayServer
from friday_ai.settings import FridaySettings
from friday_ai.task_store import TaskStore
from friday_ai.workflow import MultiAgentWorkflow


class LocalFeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.addCleanup(self.temp_dir.cleanup)

    def test_knowledge_index_search_and_remove(self):
        source = self.root / "notes.txt"
        source.write_text("Friday supports private local document retrieval.", encoding="utf-8")
        knowledge = KnowledgeBase(self.root / "index.json")

        indexed = knowledge.index_file(source)
        matches = knowledge.search("private document retrieval")

        self.assertEqual(indexed["chunks"], 1)
        self.assertEqual(matches[0]["citation"], "notes.txt")
        self.assertTrue(knowledge.remove(str(source)))
        self.assertEqual(knowledge.search("private document"), [])

    def test_knowledge_extracts_docx_and_pdf_documents(self):
        docx_path = self.root / "brief.docx"
        document = Document()
        document.add_paragraph("Friday indexes editable office documents.")
        document.save(docx_path)

        pdf_path = self.root / "blank.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        knowledge = KnowledgeBase(self.root / "index.json")
        self.assertEqual(knowledge.index_file(docx_path)["chunks"], 1)
        self.assertEqual(knowledge.search("editable office")[0]["name"], "brief.docx")
        self.assertEqual(knowledge.index_file(pdf_path)["name"], "blank.pdf")

    def test_task_requires_approval_before_progress(self):
        tasks = TaskStore(self.root / "tasks.json")
        task = tasks.create("Prepare report", ["Gather sources"])
        step = task["steps"][0]

        with self.assertRaises(ValueError):
            tasks.update(task["id"], step["id"], status="in_progress")

        updated = tasks.update(task["id"], step["id"], approved=True, status="in_progress")
        self.assertEqual(updated["steps"][0]["status"], "in_progress")

    def test_memory_can_search_edit_and_delete(self):
        memory = MemoryStore(self.root / "memory.json")
        memory.remember("user", "Remember the project codename Friday.")

        self.assertEqual(len(memory.entries("codename")), 1)
        self.assertTrue(memory.update(0, "Updated project note"))
        self.assertEqual(memory.entries("Updated")[0]["content"], "Updated project note")
        self.assertTrue(memory.delete(0))
        self.assertEqual(memory.entries(), [])

    def test_daily_reminder_advances_after_acknowledgement(self):
        reminders = ReminderStore(self.root / "reminders.json")
        reminder = reminders.create("Check the report", "2020-01-01T09:00:00+00:00", "daily")

        due = reminders.due()
        self.assertEqual(len(due), 1)
        updated = reminders.acknowledge(reminder["id"])

        self.assertFalse(reminders.due())
        self.assertEqual(updated["recurrence"], "daily")

    def test_scheduled_job_requires_approval_and_reschedules_recurrence(self):
        jobs = JobStore(self.root / "jobs.json")
        with self.assertRaises(ValueError):
            jobs.create("Daily summary", "Summarize my notes", "2020-01-01T09:00:00+00:00", "daily", False)

        job = jobs.create(
            "Daily summary", "Summarize my notes", "2020-01-01T09:00:00+00:00", "daily", True
        )
        claimed = jobs.claim_due()
        self.assertEqual(claimed[0]["id"], job["id"])
        updated = jobs.complete(job["id"], "Summary ready")

        self.assertEqual(updated["status"], "scheduled")
        self.assertGreater(
            datetime.fromisoformat(updated["run_at"]),
            datetime.now(timezone.utc),
        )

    def test_scheduler_runs_due_job_and_saves_result(self):
        jobs = JobStore(self.root / "jobs.json")
        job = jobs.create(
            "One-time calculation",
            "Calculate 4 * 5",
            "2020-01-01T09:00:00+00:00",
            "none",
            True,
        )
        stop_event = Event()

        class StubAgent:
            def respond(self, prompt):
                self.prompt = prompt
                stop_event.set()
                return "Result: 20.0"

        scheduler = object.__new__(FridayServer)
        scheduler.jobs = jobs
        scheduler.agent = StubAgent()
        scheduler._run_jobs(stop_event)

        completed = jobs.list()[0]
        self.assertEqual(completed["id"], job["id"])
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["last_result"], "Result: 20.0")

    def test_settings_never_return_api_keys(self):
        settings = FridaySettings(self.root / "settings.json")
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-secret"}):
            public = settings.update("openai", "gpt-test")
        self.assertEqual(public["provider"], "openai")
        self.assertNotIn("test-secret", json.dumps(public))

    def test_openai_provider_defaults_to_current_documented_flagship(self):
        self.assertEqual(PROVIDER_DEFAULTS["openai"], "gpt-6-astra")
        client = ModelClient("openai")
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-secret"}):
            with patch.object(client, "_post_json", return_value={
                "choices": [{"message": {"content": "Friday connected."}}]
            }) as request:
                self.assertEqual(client.generate("ping"), "Friday connected.")
        self.assertEqual(request.call_args.args[0], "https://api.openai.com/v1/chat/completions")
        self.assertEqual(request.call_args.args[1]["model"], "gpt-6-astra")
        self.assertEqual(request.call_args.args[2]["Authorization"], "Bearer test-secret")

    def test_chat_requires_confirmation_before_running_shell(self):
        agent = FridayAgent(memory_path=self.root / "memory.json")
        server = ThreadingHTTPServer(("127.0.0.1", 0), FridayRequestHandler)
        server.agent = agent
        server.workflow = MultiAgentWorkflow(agent)
        server.settings = FridaySettings(self.root / "settings.json")
        server.knowledge = KnowledgeBase(self.root / "knowledge.json")
        server.tasks = TaskStore(self.root / "tasks.json")
        server.reminders = ReminderStore(self.root / "reminders.json")
        server.jobs = JobStore(self.root / "jobs.json")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.addCleanup(thread.join, 2)

        base = f"http://127.0.0.1:{server.server_port}"
        body = json.dumps({"message": "Run command: echo Friday-approved"}).encode("utf-8")
        request = urllib.request.Request(
            base + "/chat", data=body, headers={"Content-Type": "application/json"}
        )
        with patch("friday_ai.server.run_shell") as run:
            with urllib.request.urlopen(request, timeout=5) as response:
                preview = json.loads(response.read().decode("utf-8"))
            run.assert_not_called()

        denied = urllib.request.Request(
            base + "/commands/execute",
            data=json.dumps({"command": "echo no", "confirmed": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(denied, timeout=5)
        self.assertEqual(error.exception.code, 403)
        self.assertTrue(preview["requires_confirmation"])
        self.assertEqual(preview["command"], "echo Friday-approved")


if __name__ == "__main__":
    unittest.main()
