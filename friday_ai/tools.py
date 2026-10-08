import ast
import html
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


class ToolError(RuntimeError):
    pass


def safe_eval_math(expression: str) -> float:
    allowed_names = {"__builtins__": {}}
    parsed = ast.parse(expression, mode="eval")
    for node in ast.walk(parsed):
        if isinstance(node, (ast.BinOp, ast.UnaryOp, ast.Constant)):
            continue
        if isinstance(node, ast.Call):
            raise ToolError("Function calls are not allowed.")
        if isinstance(node, ast.Name):
            raise ToolError(f"Name '{node.id}' is not allowed.")
    result = eval(compile(parsed, "<math>", "eval"), allowed_names, {})
    return float(result)


def calculate(expression: str) -> str:
    cleaned = expression.strip()
    if not cleaned:
        raise ToolError("No mathematical expression was provided.")
    try:
        value = safe_eval_math(cleaned)
        return f"Result: {value}"
    except Exception as exc:  # pragma: no cover
        raise ToolError(f"Unable to evaluate expression: {exc}") from exc


def list_directory(path: str = ".") -> List[str]:
    directory = Path(path)
    if not directory.exists():
        raise ToolError(f"Path does not exist: {path}")
    if not directory.is_dir():
        raise ToolError(f"Not a directory: {path}")
    entries = sorted(p.name for p in directory.iterdir())
    return entries


def read_file(path: str, limit: int = 3000) -> str:
    file_path = Path(path)
    if not file_path.exists():
        raise ToolError(f"File does not exist: {path}")
    if not file_path.is_file():
        raise ToolError(f"Not a file: {path}")
    with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
        text = handle.read()
    if len(text) > limit:
        text = text[:limit] + "\n... (truncated)"
    return text


def search_files(path: str, query: str) -> List[str]:
    base = Path(path)
    if not base.exists():
        raise ToolError(f"Search directory does not exist: {path}")

    matches: List[str] = []
    for root, _, files in os.walk(base):
        for file_name in files:
            full = Path(root) / file_name
            try:
                text = full.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if query.lower() in text.lower() or query.lower() in file_name.lower():
                matches.append(str(full))
    return matches[:25]


def fetch_url(url: str, limit: int = 2000) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Friday/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = response.read().decode("utf-8", errors="ignore")
    text = re.sub(r"<script.*?</script>", " ", payload, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[:limit] + " ..."
    return text


def web_search(query: str, limit: int = 5) -> List[str]:
    encoded = urllib.parse.quote(query)
    url = f"https://duckduckgo.com/html/?q={encoded}"
    try:
        html_text = fetch_url(url, limit=6000)
    except Exception:
        return []
    results = []
    for match in re.finditer(r"result-link\">(.*?)</a>", html_text, flags=re.S | re.I):
        value = re.sub(r"<.*?>", "", match.group(1))
        value = html.unescape(value)
        value = re.sub(r"\s+", " ", value).strip()
        if value:
            results.append(value)
        if len(results) >= limit:
            break
    return results


def run_shell(command: str, timeout: int = 15) -> str:
    completed = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = completed.stdout.strip() or completed.stderr.strip() or "Command completed without output."
    return output[:4000]
