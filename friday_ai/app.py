import argparse

from .agent import FridayAgent
from .config import SETTINGS_PATH
from .llm import PROVIDER_DEFAULTS
from .server import FridayServer
from .settings import FridaySettings


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Friday, the local-first personal AI assistant.")
    parser.add_argument("--prompt", help="Ask Friday a single question.")
    parser.add_argument("--model", default=None, help="Model name for the selected provider.")
    parser.add_argument("--provider", choices=["ollama", "openai", "anthropic", "google", "openai-compatible"], help="Model provider; OpenAI uses GPT-6 Astra by default.")
    parser.add_argument("--workflow", action="store_true", help="Run a task through Friday's planner, researcher, executor, and reviewer agents.")
    parser.add_argument("--interactive", action="store_true", help="Run Friday in interactive chat mode.")
    parser.add_argument("--serve", action="store_true", help="Start the Friday web server.")
    parser.add_argument("--port", type=int, default=8765, help="Port to use for the Friday web server.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind the Friday web server to.")
    args = parser.parse_args()

    if args.workflow and not args.prompt:
        parser.error("--workflow requires --prompt")

    if args.serve:
        server = FridayServer(host=args.host, port=args.port, model=args.model, provider=args.provider)
        server.run()
        return 0

    settings = FridaySettings(SETTINGS_PATH).public()
    provider = args.provider or settings["provider"]
    model = args.model or (
        settings["model"] if provider == settings["provider"] else PROVIDER_DEFAULTS[provider]
    )
    agent = FridayAgent(
        model=model,
        provider=provider,
    )

    if args.prompt:
        if args.workflow:
            from .workflow import MultiAgentWorkflow

            result = MultiAgentWorkflow(agent).run(args.prompt)
            print(result["reply"])
            return 0
        print(agent.respond(args.prompt))
        return 0

    if args.interactive:
        agent.interactive()
        return 0

    print("Friday is ready. Use --interactive or --prompt to start.")
    return 0
