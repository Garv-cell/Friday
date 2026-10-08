import json
import re
from pathlib import Path
from typing import Optional

from .config import DEFAULT_MODEL, MEMORY_PATH
from .llm import ModelClient
from .memory import MemoryStore
from .tools import ToolError, calculate, list_directory, read_file, search_files, web_search


class FridayAgent:
    def __init__(self, model: str = DEFAULT_MODEL, memory_path: str | Path = MEMORY_PATH, provider: str = "ollama"):
        self.model = model
        self.provider = provider
        self.memory = MemoryStore(memory_path)
        self.knowledge = None
        self.last_model_error: Optional[str] = None

    def _call_ollama(self, prompt: str) -> Optional[str]:
        self.last_model_error = None
        try:
            return ModelClient(self.provider, self.model).generate(prompt)
        except (OSError, ValueError, KeyError, RuntimeError, json.JSONDecodeError) as exc:
            self.last_model_error = str(exc)
            return None

    def _extract_path(self, message: str) -> Optional[str]:
        lowered = message.lower()
        if "this folder" in lowered or "current folder" in lowered or "this directory" in lowered or "current directory" in lowered:
            return "."

        candidates = re.findall(r"(?:from|in|file|path|read|open)\s+[\"']?([A-Za-z0-9_./\\:\- ]+)[\"']?", message, flags=re.I)
        if candidates:
            candidate = candidates[0].strip()
            for keyword in ["file ", "path ", "read ", "open ", "from ", "in "]:
                if candidate.lower().startswith(keyword):
                    candidate = candidate[len(keyword):].strip()
            if candidate and not candidate.lower().startswith(("this ", "current ")):
                return candidate

        quoted = re.findall(r"[\"']([^\"']+\.[A-Za-z0-9]{1,5})[\"']", message)
        if quoted:
            return quoted[0]

        for token in re.findall(r"[A-Za-z0-9_.\\/: -]+(?:\.[A-Za-z0-9]{1,8})?", message):
            cleaned = token.strip(" \"'.,;")
            lowered = cleaned.lower()
            if "." in cleaned and not lowered.startswith(("http", "read ", "file ", "open ", "path ", "from ", "in ", "this ", "current ")):
                return cleaned

        parts = re.findall(r"(?:[A-Za-z]:\\[^\s]+|\.?\.?/[^\s]+|\.?\.?\\[^\s]+)", message)
        if parts:
            return parts[0]
        return None

    def _extract_expression(self, message: str) -> Optional[str]:
        match = re.search(r"(?:calculate|compute|what is|eval)\s+(.+)", message, flags=re.I)
        if match:
            return match.group(1).strip()
        for prefix in ["=", "sum", "plus"]:
            if prefix in message.lower():
                return message.split(prefix, 1)[1].strip()
        return None

    def _extract_command(self, message: str) -> Optional[str]:
        match = re.search(r"\b(?:run command|execute|shell|terminal|bash)\s*:?\s*(.+)", message, flags=re.I)
        if not match:
            return None
        command = match.group(1).strip()
        if len(command) >= 2 and command[0] == command[-1] and command[0] in {"'", '"', "`"}:
            command = command[1:-1].strip()
        return command or None

    def _determine_tool(self, message: str):
        lower = message.lower()
        if re.search(r"\b(calculate|compute|sum|plus|minus|multiply|divide|math)\b", lower):
            return "calculate"
        if re.search(r"\b(list files|ls\s|show files|directory|folder|list the files|list files in)\b", lower):
            return "list_directory"
        if re.search(r"\b(read file|open file|view file|cat\s|read\s|open\s|view\s)\b", lower):
            return "read_file"
        if re.search(r"\b(search file|find file|search for|grep\s)\b", lower):
            return "search_files"
        if re.search(r"\b(web search|search the web|browse|look up)\b", lower):
            return "web_search"
        if re.search(r"\b(run command|execute|terminal|shell|bash)\b", lower):
            return "run_shell"
        return None

    def _tool_call(self, message: str):
        tool_name = self._determine_tool(message)
        if not tool_name:
            return None

        if tool_name == "calculate":
            expr = self._extract_expression(message)
            if not expr:
                return "I can calculate expressions, but I need the math to evaluate."
            try:
                return calculate(expr)
            except ToolError as exc:
                return str(exc)

        if tool_name == "list_directory":
            path = self._extract_path(message) or "."
            try:
                listing = list_directory(path)
                return "Files and folders:\n" + "\n".join(f"- {name}" for name in listing)
            except ToolError as exc:
                return str(exc)

        if tool_name == "read_file":
            path = self._extract_path(message)
            if not path:
                return "I need a file path to read."
            try:
                return read_file(path)
            except ToolError as exc:
                return str(exc)

        if tool_name == "search_files":
            query = re.search(r"(?:search(?: for)?|find)\s+(.+)", message, flags=re.I)
            path = self._extract_path(message) or "."
            if not query:
                return "I need a search term to look for."
            matches = search_files(path, query.group(1).strip())
            if not matches:
                return "No matching files were found."
            return "Matches:\n" + "\n".join(f"- {match}" for match in matches)

        if tool_name == "web_search":
            query = re.search(r"(?:search(?: the web)?|look up|browse)\s+(.+)", message, flags=re.I)
            if not query:
                return "I need a query to search the web."
            results = web_search(query.group(1).strip())
            if not results:
                return "I could not retrieve web results right now."
            return "Web results:\n" + "\n".join(f"- {result}" for result in results)

        if tool_name == "run_shell":
            return (
                "For safety, shell commands are not run directly from chat. "
                "Use the local dashboard, review the exact command, and explicitly approve it."
            )

        return None

    def _fallback_reply(self, message: str, context: str = "") -> str:
        prompt = (
            "You are Friday, a local-first personal AI assistant. "
            "Answer helpfully, clearly, and concisely. "
            "Be warm, human-like, conversational, and emotionally aware. "
            "If the user asks for a task that needs tools, mention the capabilities.\n\n"
            f"User message: {message}\n"
        )
        if context:
            prompt += f"Relevant memory: {context}\n"
        if self.knowledge:
            matches = self.knowledge.search(message, limit=4)
            if matches:
                excerpts = "\n".join(
                    f"[{item['citation']}] {item['text']}" for item in matches
                )
                prompt += (
                    "\nUse these indexed document excerpts when relevant. Cite supporting "
                    "facts inline using the provided bracketed source labels. Do not invent "
                    "details beyond the excerpts.\n"
                    f"Document excerpts:\n{excerpts}\n"
                )
        return prompt

    def _detect_mood(self, message: str) -> str:
        lower = message.lower()
        if any(word in lower for word in ["sad", "stressed", "anxious", "upset", "down", "tired", "lonely", "hurt"]):
            return "empathetic"
        if any(word in lower for word in ["happy", "excited", "great", "amazing", "good", "joy", "love"]):
            return "cheerful"
        if any(word in lower for word in ["angry", "mad", "frustrated", "annoyed"]):
            return "calm"
        if any(word in lower for word in ["please", "thanks", "thank you", "help me", "support"]):
            return "supportive"
        return "friendly"

    def _extract_redirect_target(self, message: str) -> Optional[str]:
        match = re.search(r"(?:redirect|switch|move|take me to|focus on|go to)\s+(?:mode\s+)?(?:to\s+)?(.+)", message, flags=re.I)
        if match:
            target = match.group(1).strip().strip("?.,! ")
            return target or None
        return None

    def _humanize_response(self, message: str, response: str) -> str:
        lower = message.lower()
        mood = self._detect_mood(message)
        redirect_target = self._extract_redirect_target(message)

        prefix = {
            "empathetic": "I’m here with you. ",
            "cheerful": "Absolutely! ",
            "calm": "Let’s take this one step at a time. ",
            "supportive": "Of course — I’ve got you. ",
            "friendly": "Sure thing. ",
        }.get(mood, "Sure thing. ")

        if redirect_target:
            response = f"Absolutely — I’ll redirect us toward {redirect_target}. {response}"

        if "thank you" in lower or "thanks" in lower:
            response = "You’re very welcome. I’m glad I could help."

        if "tell me a joke" in lower or "joke" in lower:
            response = "Sure — why did the computer get invited to the party? Because it had great bytes."

        if any(word in lower for word in ["i am sad", "i feel sad", "i feel down", "i am stressed", "i am anxious"]):
            response = "I’m really sorry you’re feeling that way. Let’s slow down, breathe, and take this step by step. I can help you with a plan, a task, or just a calm conversation."

        if "hello" in lower or "hi" in lower:
            response = "Hey there! I’m Friday, your local AI companion. I can help you think, create, organize, and get work done with a warm human feel."

        if "who are you" in lower or "what are you" in lower:
            response = "I’m Friday — a local-first AI assistant built to feel helpful, warm, and human. I can remember context, handle files, calculate, search, and support your workflow locally."

        if "help" in lower and "me" in lower:
            response = "I’m here to help. We can break it down together, start with the goal, and build a simple path forward."

        response = prefix + response
        return response.strip()

    def respond(self, message: str, working_directory: str = ".") -> str:
        self.memory.remember("user", message)

        tool_response = self._tool_call(message)
        if tool_response:
            self.memory.remember("tool", str(tool_response))
            final = tool_response
            self.memory.remember("assistant", final)
            return final

        context = self.memory.search(message, limit=3)
        memory_block = "\n".join(
            f"- {entry['role']}: {entry['content']}" for entry in context
        )

        prompt = self._fallback_reply(message, memory_block)
        ollama_output = self._call_ollama(prompt)
        if ollama_output:
            ollama_output = self._humanize_response(message, ollama_output)
            self.memory.remember("assistant", ollama_output)
            return ollama_output
        if self.provider != "ollama" and self.last_model_error:
            response = f"The selected {self.provider} model could not respond: {self.last_model_error}"
            self.memory.remember("assistant", response)
            return response

        if "hello" in message.lower() or "hi" in message.lower():
            response = "Hello! I am Friday, your local-first AI assistant. I can chat, remember context, calculate, search files, and use local tools."
        elif "who are you" in message.lower() or "what are you" in message.lower():
            response = "I am Friday, a local-first AI assistant built in Python. I can work with memory, local files, shell commands, and Ollama-backed models when available."
        elif "help" in message.lower():
            response = "I can help with local file analysis, math, web lookups, shell tasks, and conversation. Try prompts like: 'List files in this folder', 'Read file app.py', or 'Calculate 14 * 8'."
        else:
            response = (
                "I am Friday. I can help with local reasoning, memory, file tools, shell execution, and model-backed chat. "
                "If Ollama is running, I can also use it as the local inference engine."
            )

        response = self._humanize_response(message, response)
        self.memory.remember("assistant", response)
        return response

    def interactive(self) -> None:
        print("Friday is online. Type 'exit' to quit.")
        while True:
            try:
                user_input = input("You> ")
            except KeyboardInterrupt:
                print("\nGoodbye.")
                break
            if user_input.strip().lower() in {"exit", "quit", "bye"}:
                print("Friday: Goodbye.")
                break
            print(f"Friday: {self.respond(user_input)}")
