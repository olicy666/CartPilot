from __future__ import annotations

import unittest

from backend.prompts.registry import get_prompt


class PromptRegistryTest(unittest.TestCase):
    def test_prompt_versions_are_registered(self) -> None:
        agent_prompt = get_prompt("agentic_planner_system")
        intent_prompt = get_prompt("intent_parser_system")

        self.assertEqual(agent_prompt.version, "agentic-planner-v1")
        self.assertEqual(intent_prompt.version, "intent-parser-v1")
        self.assertIn("只输出 JSON", agent_prompt.text)
        self.assertIn("候选品类", intent_prompt.text)


if __name__ == "__main__":
    unittest.main()
