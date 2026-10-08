import argparse

from .agent import FridayAgent


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Friday local AI assistant.")
    parser.add_argument("--prompt", help="Ask Friday a single question.")
    parser.add_argument("--model", default=None, help="Ollama model to use when available.")
    args = parser.parse_args()

    agent = FridayAgent(model=args.model or "llama3.2")

    if args.prompt:
        print(agent.respond(args.prompt))
        return 0

    agent.interactive()
    return 0
