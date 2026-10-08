import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from friday_ai.agent import FridayAgent
from friday_ai.workflow import MultiAgentWorkflow


class MultiAgentWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        memory_path = Path(self.temp_dir.name) / "memory.json"
        self.assistant = FridayAgent(memory_path=memory_path)
        self.workflow = MultiAgentWorkflow(self.assistant)
        self.model_patch = patch.object(FridayAgent, "_call_ollama", return_value=None)
        self.model_patch.start()
        self.addCleanup(self.model_patch.stop)
        self.addCleanup(self.temp_dir.cleanup)

    def test_workflow_uses_tools_and_returns_all_agent_steps(self):
        result = self.workflow.run("Calculate 5 * 7")

        self.assertEqual(
            [step["agent"] for step in result["steps"]],
            ["Planner", "Researcher", "Executor", "Reviewer"],
        )
        self.assertIn("Result: 35.0", result["reply"])

    def test_workflow_does_not_run_shell_commands(self):
        with patch("friday_ai.tools.run_shell") as run_shell:
            result = self.workflow.run("Run command to delete temporary files")

        run_shell.assert_not_called()
        self.assertIn("No shell command was executed", result["reply"])

    def test_workflow_records_final_result_in_memory(self):
        result = self.workflow.run("Calculate 2 + 2")

        recent = self.assistant.memory.recent(limit=2)
        self.assertEqual(recent[0]["role"], "assistant")
        self.assertEqual(recent[0]["content"], result["reply"])


if __name__ == "__main__":
    unittest.main()
