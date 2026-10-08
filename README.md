# Friday

Friday is a local-first Python AI assistant inspired by the OpenJarvis philosophy: private, local, extensible, and capable of using tools to complete real tasks on the user’s machine.

## Features

- Local-first chat assistant
- Optional Ollama integration for model-backed responses
- Persistent memory for previous conversations
- File and directory access tools
- Calculator and shell execution support
- Lightweight web search and URL fetch
- Simple task-oriented agent loop
- Optional planner, researcher, executor, and reviewer workflow
- Human-like conversational style with empathy and redirect behavior
- Voice input (browser microphone) and voice reply support
- Local web UI for interactive conversations
- Searchable document knowledge base with citations
- Editable task plans with per-step approval and progress
- Daily and weekly reminders
- User-approved one-time and recurring scheduled jobs
- Configurable Ollama, OpenAI-compatible, OpenAI, Anthropic, and Google model providers
- Searchable, editable, and deletable conversation memory
- Browser wake phrase, push-to-talk, speech language, and voice selection
- Explicit confirmation before shell command execution
- Local workflow history and review

## Run the interactive app

```bash
python friday.py --interactive
```

## Run a single prompt

```bash
python friday.py --prompt "List files in this folder"
```

## Run a task through the agent team

```bash
python friday.py --workflow --prompt "Calculate 14 * 8 and explain the result"
```

In the web UI, enter a task and select **Use agents**. Friday runs the planner,
researcher, executor, and reviewer in order. When Ollama is available, each
role can use the configured local model. Without Ollama, Friday still uses
available built-in tools and reports when a language-model-generated result
is unavailable. Workflow mode does not execute shell commands automatically.

## Dashboard features

- **Knowledge:** index a local file or a directory. TXT, Markdown, CSV, JSON,
  and log files are supported. PDF and DOCX extraction use the optional
  dependencies in `requirements.txt`. Friday retrieves relevant snippets and
  gives source labels in model-backed answers.
- **Task planner:** create editable plans, approve steps, and track status.
  Planning does not perform the task by itself.
- **Reminders:** set one-time, daily, or weekly reminders. Keep Friday's web UI
  open to receive in-app reminder notifications.
- **Scheduled jobs:** explicitly approve a prompt to run once, daily, or weekly.
  Friday must be running. Jobs use Friday's selected model and tools, never run
  shell commands, and show their last result in the dashboard.
- **Memory:** search, edit, delete individual entries, or clear all memory.
- **Voice:** use push-to-talk or explicitly enable the “Hey Friday” wake phrase.
  Microphone permission is required. Browser speech recognition may use the
  browser vendor's speech service; it is not guaranteed to run locally.
- **Workflow history:** review recent multi-agent results in this browser.

## Start the local web interface

```bash
python friday.py --serve
```

Then open:

```text
http://127.0.0.1:8765/
```

## Environment variables

- `FRIDAY_MODEL` - model name override for the configured provider
- `FRIDAY_PROVIDER` - provider default; `ollama` is the privacy-preserving default
- OpenAI's provider default is **GPT-6 Astra** (`gpt-6-astra`), verified against
  [OpenAI's model documentation](https://developers.openai.com/api/docs/models/gpt-6-astra.md).
- `FRIDAY_MEMORY_PATH` - custom memory storage path
- `FRIDAY_HOME` - home directory for Friday runtime data
- `OLLAMA_URL` - override the default Ollama base URL (`http://localhost:11434`)
- `FRIDAY_KNOWLEDGE_PATH`, `FRIDAY_TASKS_PATH`, `FRIDAY_REMINDERS_PATH`,
  `FRIDAY_JOBS_PATH`, `FRIDAY_SETTINGS_PATH` - override local JSON data paths
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` - configure optional cloud providers
- `FRIDAY_API_BASE`, `FRIDAY_API_KEY` - configure an OpenAI-compatible endpoint

Provider API keys should be supplied through environment variables, never saved
in Friday's settings file or entered in the dashboard. Selecting a cloud
provider sends prompts and retrieved context to that provider. Friday's server
defaults to `127.0.0.1`; do not expose it to an untrusted network because the
local dashboard can access local files and approve commands.

To enable OpenAI, configure `OPENAI_API_KEY` in the environment where Friday is
launched, then select **openai** in the dashboard provider menu. It defaults to
`gpt-6-astra`; the model field can be changed if your API account uses another
model. The same selection can be made from the CLI with
`python friday.py --provider openai --prompt "Hello Friday"`.

## Notes

- If Ollama is unavailable, Friday still offers built-in deterministic tools,
  plans, reminders, and memory management, but free-form model responses need
  a configured model provider.
- This is a practical personal AI prototype built to reflect the OpenJarvis direction without requiring external cloud dependencies.
