import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


class MemoryStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data: Dict[str, List[Dict[str, Any]]] = {"entries": []}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                with self.path.open("r", encoding="utf-8") as handle:
                    loaded = json.load(handle)
                    if isinstance(loaded, dict):
                        self.data = loaded
                if "entries" not in self.data:
                    self.data["entries"] = []
            except json.JSONDecodeError:
                self.data = {"entries": []}
        else:
            self.data = {"entries": []}

    def save(self) -> None:
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(self.data, handle, indent=2)

    def remember(self, role: str, content: str) -> None:
        entry = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.data.setdefault("entries", []).append(entry)
        self.save()

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        query_terms = {part.lower() for part in query.split() if part}
        matches: List[Dict[str, Any]] = []
        for entry in reversed(self.data.get("entries", [])):
            content = str(entry.get("content", "")).lower()
            if not query_terms or any(term in content for term in query_terms):
                matches.append(entry)
                if len(matches) >= limit:
                    break
        return matches

    def recent(self, limit: int = 5) -> List[Dict[str, Any]]:
        entries = list(reversed(self.data.get("entries", [])))
        return entries[:limit]

    def update(self, index: int, content: str) -> bool:
        entries = self.data.get("entries", [])
        if index < 0 or index >= len(entries):
            return False
        entries[index]["content"] = content
        self.save()
        return True

    def delete(self, index: int) -> bool:
        entries = self.data.get("entries", [])
        if index < 0 or index >= len(entries):
            return False
        del entries[index]
        self.save()
        return True

    def clear(self) -> None:
        self.data = {"entries": []}
        self.save()

    def entries(self, query: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        entries = self.data.get("entries", [])
        selected = list(enumerate(entries))
        if query:
            term = query.casefold()
            selected = [
                (index, entry) for index, entry in selected
                if term in str(entry.get("content", "")).casefold()
                or term in str(entry.get("role", "")).casefold()
            ]
        return [
            {"index": index, **entry}
            for index, entry in reversed(selected[-max(1, min(limit, 500)):])
        ]
