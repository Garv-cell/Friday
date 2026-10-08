import os
from pathlib import Path

APP_NAME = "Friday"
DEFAULT_MODEL = os.getenv("FRIDAY_MODEL", "llama3.2")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
FRIDAY_HOME = Path(os.getenv("FRIDAY_HOME", Path.home() / ".friday"))
MEMORY_PATH = Path(os.getenv("FRIDAY_MEMORY_PATH", FRIDAY_HOME / "memory.json"))
KNOWLEDGE_PATH = Path(os.getenv("FRIDAY_KNOWLEDGE_PATH", FRIDAY_HOME / "knowledge.json"))
TASKS_PATH = Path(os.getenv("FRIDAY_TASKS_PATH", FRIDAY_HOME / "tasks.json"))
REMINDERS_PATH = Path(os.getenv("FRIDAY_REMINDERS_PATH", FRIDAY_HOME / "reminders.json"))
JOBS_PATH = Path(os.getenv("FRIDAY_JOBS_PATH", FRIDAY_HOME / "jobs.json"))
SETTINGS_PATH = Path(os.getenv("FRIDAY_SETTINGS_PATH", FRIDAY_HOME / "settings.json"))

FRIDAY_HOME.mkdir(parents=True, exist_ok=True)
MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
