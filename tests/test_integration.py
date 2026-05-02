"""
Integration tests for the agent CLI and end-to-end workflow.

These tests verify that config loading, component assembly,
and result printing work correctly. API calls are mocked.
"""

import sys
from pathlib import Path
from io import StringIO
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
from datetime import datetime

from config import load_config, AgentConfig
from main import print_results, run_agent
from core.schemas import FinalAnswer
from core.constants import AgentStatus


class TestConfig(unittest.TestCase):
    """Test configuration loading."""

    def test_load_config_from_args(self):
        """Config should parse CLI arguments."""
        config = load_config([
            "--audio", "test.wav",
            "--question", "What is this?",
            "--api-key", "sk-test",
            "--max-steps", "5",
        ])
        self.assertEqual(config.audio_path, "test.wav")
        self.assertEqual(config.question, "What is this?")
        self.assertEqual(config.api_key, "sk-test")
        self.assertEqual(config.max_steps, 5)

    def test_config_valid(self):
        """Valid config passes is_valid check."""
        config = AgentConfig(
            api_key="sk-test",
            audio_path="test.wav",
            question="What?",
        )
        self.assertTrue(config.is_valid)

    def test_config_invalid_missing_key(self):
        """Config without API key is invalid."""
        config = AgentConfig(
            audio_path="test.wav",
            question="What?",
        )
        self.assertFalse(config.is_valid)


class TestPrintResults(unittest.TestCase):
    """Test result formatting."""

    def test_print_answered(self):
        """Should print answer and confidence."""
        state = {
            "status": AgentStatus.ANSWERED,
            "final_answer": FinalAnswer(
                answer="It is a dog barking",
                confidence=0.95,
                evidence_summary="Kitchen sounds detected",
            ),
            "step_count": 2,
            "tool_call_history": [MagicMock()],
            "evidence_log": [MagicMock(), MagicMock()],
        }
        captured = StringIO()
        with patch("sys.stdout", new=captured):
            print_results(state)
        output = captured.getvalue()
        self.assertIn("It is a dog barking", output)
        self.assertIn("0.95", output)
        self.assertIn("Kitchen sounds detected", output)
        self.assertIn("Steps taken: 2", output)

    def test_print_failed(self):
        """Should print error message."""
        state = {
            "status": AgentStatus.FAILED,
            "error_message": "Max steps exceeded",
            "step_count": 3,
            "tool_call_history": [],
            "evidence_log": [],
        }
        captured = StringIO()
        with patch("sys.stdout", new=captured):
            print_results(state)
        output = captured.getvalue()
        self.assertIn("Max steps exceeded", output)
        self.assertIn("Agent failed", output)


class TestRunAgent(unittest.TestCase):
    """Test run_agent with mocked components."""

    def test_run_agent_success(self):
        """Full agent run should return answered state."""
        config = AgentConfig(
            api_key="sk-test",
            audio_path="fake.wav",
            question="What is this?",
            max_steps=5,
        )

        # Mock all components
        mock_frontend = MagicMock()
        mock_planner = MagicMock()
        mock_fusion = MagicMock()
        mock_executor = MagicMock()
        mock_registry = MagicMock()

        # Mock graph
        mock_graph = MagicMock()
        mock_final_state = {
            "status": AgentStatus.ANSWERED,
            "final_answer": FinalAnswer(answer="Mock answer", confidence=0.9),
            "step_count": 1,
            "evidence_log": [MagicMock()],
            "tool_call_history": [MagicMock()],
        }
        mock_graph.invoke.return_value = mock_final_state

        with patch("main.create_components", return_value=(
            mock_frontend, mock_planner, mock_fusion, mock_executor, mock_registry
        )):
            with patch("main.build_agent_graph", return_value=mock_graph):
                final_state = run_agent(config)

        self.assertEqual(final_state["status"], AgentStatus.ANSWERED)
        self.assertEqual(final_state["final_answer"].answer, "Mock answer")
        mock_graph.invoke.assert_called_once()


if __name__ == "__main__":
    unittest.main()
