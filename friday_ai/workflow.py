from typing import Dict, List, Optional

from .agent import FridayAgent


class MultiAgentWorkflow:
    def __init__(self, assistant: FridayAgent):
        self.assistant = assistant

    def _ask_role(self, role: str, instructions: str, task: str, context: str = "") -> Optional[str]:
        prompt = (
            f"You are Friday's {role} agent. {instructions}\n"
            "Be accurate and do not claim actions or research that were not performed.\n\n"
            f"User task:\n{task}\n"
        )
        if context:
            prompt += f"\nWorkflow context:\n{context}\n"
        return self.assistant._call_ollama(prompt)

    def _plan(self, task: str) -> str:
        result = self._ask_role(
            "planner",
            "Break the user's task into a short, ordered plan of at most four steps. "
            "Do not execute the steps.",
            task,
        )
        if result:
            return result
        return (
            "1. Clarify the desired outcome and constraints.\n"
            "2. Gather relevant context using available Friday tools.\n"
            "3. Complete the task or prepare the most useful result.\n"
            "4. Review the result for accuracy and limitations."
        )

    def _research(self, task: str) -> str:
        tool_name = self.assistant._determine_tool(task)
        if tool_name and tool_name != "run_shell":
            tool_result = self.assistant._tool_call(task)
            if tool_result:
                return f"Available tool result ({tool_name}):\n{tool_result}"

        result = self._ask_role(
            "researcher",
            "Identify useful context and evidence for the task. Distinguish known information "
            "from assumptions and do not invent citations.",
            task,
        )
        if result:
            return result
        if tool_name == "run_shell":
            return "No commands were run during research. Shell execution is not automatic in workflows."
        return "No external or local-source lookup was requested, and the local model is unavailable."

    def _execute(self, task: str, plan: str, research: str) -> str:
        tool_name = self.assistant._determine_tool(task)
        if tool_name == "run_shell":
            return (
                "No shell command was executed. Friday requires a separate explicit command request "
                "outside workflow mode before running shell commands."
            )
        if tool_name and tool_name != "run_shell":
            return research

        result = self._ask_role(
            "executor",
            "Use the plan and research to produce the requested deliverable. Be concrete and "
            "state any missing information instead of pretending work was performed.",
            task,
            f"Plan:\n{plan}\n\nResearch:\n{research}",
        )
        if result:
            return result
        return (
            "The task plan is ready, but no local language model is available to generate the "
            "requested deliverable. Start Ollama with a model configured for Friday, then retry."
        )

    def _review(self, task: str, plan: str, research: str, execution: str) -> str:
        context = (
            f"Plan:\n{plan}\n\nResearch:\n{research}\n\nExecution:\n{execution}"
        )
        result = self._ask_role(
            "reviewer",
            "Review the work for relevance, unsupported claims, and incomplete steps. "
            "Return a concise quality check and note any limitations.",
            task,
            context,
        )
        if result:
            return result
        if "local language model is available" in execution:
            return "Review: the plan is provided, but the deliverable remains incomplete until a local model is available."
        if "No shell command was executed" in execution:
            return "Review: no command was run; execute shell requests separately and explicitly."
        return "Review: the workflow completed with the available tools. Verify important results before relying on them."

    def run(self, task: str) -> Dict[str, object]:
        plan = self._plan(task)
        research = self._research(task)
        execution = self._execute(task, plan, research)
        review = self._review(task, plan, research, execution)
        steps: List[Dict[str, str]] = [
            {"agent": "Planner", "result": plan},
            {"agent": "Researcher", "result": research},
            {"agent": "Executor", "result": execution},
            {"agent": "Reviewer", "result": review},
        ]
        reply = "\n\n".join(
            f"{step['agent']}:\n{step['result']}" for step in steps
        )
        self.assistant.memory.remember("user", f"[Multi-agent workflow] {task}")
        self.assistant.memory.remember("assistant", reply)
        return {"reply": reply, "steps": steps}
