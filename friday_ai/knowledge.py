import json
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List

SUPPORTED_EXTENSIONS = {".txt", ".md", ".rst", ".csv", ".log", ".json", ".pdf", ".docx"}
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_CHUNKS_PER_FILE = 500


class KnowledgeError(ValueError):
    pass


class KnowledgeBase:
    def __init__(self, index_path: str | Path):
        self.index_path = Path(index_path)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.chunks: List[Dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if not self.index_path.exists():
            return
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise KnowledgeError(f"Knowledge index is invalid JSON: {exc}") from exc
        if not isinstance(data, list):
            raise KnowledgeError("Knowledge index must contain a list.")
        self.chunks = [item for item in data if isinstance(item, dict)]

    def _save(self) -> None:
        temporary = self.index_path.with_suffix(self.index_path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.chunks, indent=2), encoding="utf-8")
        temporary.replace(self.index_path)

    def _extract(self, path: Path) -> List[Dict[str, Any]]:
        if not path.is_file():
            raise KnowledgeError(f"Not a file: {path}")
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise KnowledgeError(f"Unsupported document type: {path.suffix or '(no extension)'}")
        if path.stat().st_size > MAX_FILE_BYTES:
            raise KnowledgeError(f"File exceeds the 10 MB indexing limit: {path}")

        if path.suffix.lower() == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError as exc:
                raise KnowledgeError("PDF indexing requires the optional pypdf package. Install requirements.txt.") from exc
            try:
                pages = [
                    (number, page.extract_text() or "")
                    for number, page in enumerate(PdfReader(str(path)).pages, start=1)
                ]
            except (OSError, ValueError, KeyError) as exc:
                raise KnowledgeError(f"Could not extract text from PDF {path}: {exc}") from exc
        elif path.suffix.lower() == ".docx":
            try:
                from docx import Document
            except ImportError as exc:
                raise KnowledgeError("DOCX indexing requires the optional python-docx package. Install requirements.txt.") from exc
            try:
                pages = [(None, "\n".join(paragraph.text for paragraph in Document(str(path)).paragraphs))]
            except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
                raise KnowledgeError(f"Could not extract text from DOCX {path}: {exc}") from exc
        else:
            pages = [(None, path.read_text(encoding="utf-8", errors="replace"))]

        chunks: List[Dict[str, Any]] = []
        for page_number, text in pages:
            words = text.split()
            for offset in range(0, len(words), 160):
                content = " ".join(words[offset:offset + 190]).strip()
                if content:
                    chunks.append({
                        "source": str(path.resolve()),
                        "name": path.name,
                        "page": page_number,
                        "text": content,
                    })
                if len(chunks) >= MAX_CHUNKS_PER_FILE:
                    break
            if len(chunks) >= MAX_CHUNKS_PER_FILE:
                break
        return chunks

    def index_file(self, path: str | Path) -> Dict[str, Any]:
        file_path = Path(path).expanduser().resolve()
        new_chunks = self._extract(file_path)
        self.chunks = [chunk for chunk in self.chunks if chunk.get("source") != str(file_path)]
        self.chunks.extend(new_chunks)
        self._save()
        return {"source": str(file_path), "name": file_path.name, "chunks": len(new_chunks)}

    def index_directory(self, path: str | Path) -> List[Dict[str, Any]]:
        directory = Path(path).expanduser().resolve()
        if not directory.is_dir():
            raise KnowledgeError(f"Not a directory: {directory}")
        files = []
        for item in directory.rglob("*"):
            if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS:
                files.append(item)
                if len(files) == 100:
                    break
        indexed = [self.index_file(item) for item in files]
        return indexed

    def list_documents(self) -> List[Dict[str, Any]]:
        documents: Dict[str, Dict[str, Any]] = {}
        for chunk in self.chunks:
            source = str(chunk.get("source", ""))
            document = documents.setdefault(source, {
                "source": source,
                "name": chunk.get("name", Path(source).name),
                "chunks": 0,
            })
            document["chunks"] += 1
        return list(documents.values())

    def remove(self, source: str) -> bool:
        resolved = str(Path(source).expanduser().resolve())
        remaining = [chunk for chunk in self.chunks if chunk.get("source") != resolved]
        if len(remaining) == len(self.chunks):
            return False
        self.chunks = remaining
        self._save()
        return True

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        terms = {term for term in re.findall(r"\w+", query.lower()) if len(term) > 1}
        if not terms:
            return []
        ranked = []
        for chunk in self.chunks:
            words = set(re.findall(r"\w+", str(chunk.get("text", "")).lower()))
            score = len(terms & words)
            if score:
                ranked.append((score, chunk))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [
            {
                **chunk,
                "score": score,
                "citation": f"{chunk.get('name')}"+(f", page {chunk['page']}" if chunk.get("page") else ""),
            }
            for score, chunk in ranked[:limit]
        ]
