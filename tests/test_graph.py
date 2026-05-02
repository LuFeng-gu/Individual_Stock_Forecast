"""
Tests for the LangGraph agent workflow.

Uses mocked dependencies to verify graph structure and state flow
without making real API calls.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
from datetime import datetime

from core.schemas import (
    FrontendOutput,
    InitialPlan,
    PlannerDecision,
    ToolSpec,
    ToolCallRequest,
    ToolResult,
    FinalAnswer,
    EvidenceItem,
)
from core.state import AgentState, create_initial_state
from core.constants import AgentStatus
from core.schemas import PlannerActionType
from frontend.base import BaseFrontend
from planner.base import BasePlanner
from fusion import SimpleFusion
from tools.base import BaseTool
from tools.registry import ToolRegistry
from tools.executor import ToolExecutor
from graph.builder import build_agent_graph


# =============================================================================
# Mock Components
# =============================================================================

class MockFrontend(BaseFrontend):
    """Fake frontend that returns predictable captions."""

    @property
    def name(self) -> str:
        return "mock_frontend"

    def run(self, question, audio_path, question_oriented_prompt=None):
        return FrontendOutput(
            question_guided_caption="Mock caption: kitchen sounds",
            timestamp=datetime.now(),
        )

    def generate_final_answer(self, question, audio_path, context):
        return "Mock final answer"


class MockPlanner(BasePlanner):
    """Fake planner that cycles through decisions."""

    def __init__(self):
        self._call_count = 0

    @property
    def name(self) -> str:
        return "mock_planner"

    def generate_question_oriented_prompt(self, question: str) -> str:
        return f"Analyze this audio for: {question}"

    def plan(self, question, frontend_output=None):
        return InitialPlan(
            approach="Mock approach",
            focus_points=["mock_point"],
        )

    def decide(self, state: AgentState, available_tools: list[ToolSpec]):
        self._call_count += 1
        step = state.get("step_count", 0)

        # First decision: call tool
        if step == 0:
            return PlannerDecision(
                action=PlannerActionType.CALL_TOOL,
                rationale="Need more evidence",
                selected_tool_name="echo",
                selected_tool_args={"text": "hello"},
                confidence=0.7,
            )
        # Second decision: answer
        return PlannerDecision(
            action=PlannerActionType.ANSWER,
            rationale="Evidence is sufficient",
            confidence=0.9,
        )

    def summarize_evidence(self, state: AgentState) -> str:
        return "Mock evidence summary"


class EchoTool(BaseTool):
    """Simple echo tool for testing tool execution in the graph."""

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="echo",
            description="Echo the input text back",
        )

    def invoke(self, request: ToolCallRequest) -> ToolResult:
        text = request.args.get("text", "")
        return ToolResult(
            tool_name="echo",
            success=True,
            output={"echoed_text": text},
        )


# =============================================================================
# Test Cases
# =============================================================================

class TestAgentGraph(unittest.TestCase):
    """Test the compiled LangGraph workflow."""

    def setUp(self):
        self.planner = MockPlanner()
        self.frontend = MockFrontend()
        self.fusion = SimpleFusion()
        self.registry = ToolRegistry()
        self.registry.register(EchoTool())
        self.executor = ToolExecutor(self.registry)

    def test_graph_compiles(self):
        """The graph should compile without errors."""
        graph = build_agent_graph(
            planner=self.planner,
            frontend=self.frontend,
            fusion=self.fusion,
            executor=self.executor,
            registry=self.registry,
        )
        self.assertIsNotNone(graph)

    def test_full_workflow_with_tool_loop(self):
        """
        Full workflow: prompt -> frontend -> plan -> decide(CALL_TOOL)
        -> execute -> fuse -> decide(ANSWER) -> summarize -> final_answer -> END
        """
        graph = build_agent_graph(
            planner=self.planner,
            frontend=self.frontend,
            fusion=self.fusion,
            executor=self.executor,
            registry=self.registry,
        )

        initial_state = create_initial_state(
            question="What is in this audio?",
            audio_path="fake.wav",
            max_steps=5,
        )

        # LangGraph invoke returns the final state
        final_state = graph.invoke(initial_state)

        # Verify final status
        self.assertEqual(final_state["status"], AgentStatus.ANSWERED)

        # Verify final answer exists
        self.assertIsNotNone(final_state.get("final_answer"))
        self.assertIsInstance(final_state["final_answer"], FinalAnswer)
        self.assertEqual(final_state["final_answer"].answer, "Mock final answer")

        # Verify evidence log has both frontend and tool evidence
        evidence_log = final_state.get("evidence_log", [])
        self.assertGreaterEqual(len(evidence_log), 2)
        sources = [ev.source for ev in evidence_log]
        self.assertIn("frontend", sources)
        self.assertIn("echo", sources)

        # Verify planner was called twice (CALL_TOOL then ANSWER)
        self.assertEqual(self.planner._call_count, 2)

        # Verify step count incremented
        self.assertEqual(final_state["step_count"], 1)

        # Verify tool call history
        tool_history = final_state.get("tool_call_history", [])
        self.assertEqual(len(tool_history), 1)
        self.assertEqual(tool_history[0].request.tool_name, "echo")

    def test_direct_answer_no_tools(self):
        """
        If planner immediately says ANSWER, skip tool loop.
        """
        class ImmediateAnswerPlanner(MockPlanner):
            def decide(self, state, available_tools):
                self._call_count += 1
                return PlannerDecision(
                    action=PlannerActionType.ANSWER,
                    rationale="No tools needed",
                    confidence=0.95,
                )

        planner = ImmediateAnswerPlanner()
        graph = build_agent_graph(
            planner=planner,
            frontend=self.frontend,
            fusion=self.fusion,
            executor=self.executor,
            registry=self.registry,
        )

        initial_state = create_initial_state(
            question="Simple question",
            audio_path="fake.wav",
            max_steps=5,
        )

        final_state = graph.invoke(initial_state)

        self.assertEqual(final_state["status"], AgentStatus.ANSWERED)
        self.assertEqual(final_state["final_answer"].answer, "Mock final answer")
        # No tool calls
        self.assertEqual(len(final_state.get("tool_call_history", [])), 0)
        self.assertEqual(final_state["step_count"], 0)

    def test_max_steps_forces_failure(self):
        """
        If planner keeps calling tools, max_steps should force failure.
        """
        class LoopyPlanner(MockPlanner):
            def decide(self, state, available_tools):
                self._call_count += 1
                return PlannerDecision(
                    action=PlannerActionType.CALL_TOOL,
                    rationale="Always need more",
                    selected_tool_name="echo",
                    selected_tool_args={"text": "loop"},
                    confidence=0.5,
                )

        planner = LoopyPlanner()
        graph = build_agent_graph(
            planner=planner,
            frontend=self.frontend,
            fusion=self.fusion,
            executor=self.executor,
            registry=self.registry,
        )

        initial_state = create_initial_state(
            question="Loopy question",
            audio_path="fake.wav",
            max_steps=3,
        )

        final_state = graph.invoke(initial_state)

        self.assertEqual(final_state["status"], AgentStatus.FAILED)
        self.assertIsNotNone(final_state.get("error_message"))
        # Should have hit max_steps, not infinite loop
        self.assertLessEqual(final_state["step_count"], 3)


if __name__ == "__main__":
    unittest.main()
