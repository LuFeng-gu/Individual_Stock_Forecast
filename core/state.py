"""
Agent state definition for LangGraph.

This module defines the central state object that flows through every node
in the graph. Think of it as the agent's "memory" — every node reads from
it and writes updates back to it.

LangGraph uses TypedDict (not a regular class) because it needs to merge
partial updates from each node efficiently.
"""

from typing import TypedDict, Annotated, Any
from operator import add

from core.schemas import (
    FrontendOutput,
    InitialPlan,
    EvidenceItem,
    ToolCallRecord,
    PlannerDecision,
    FinalAnswer,
    ToolResult,
)
from core.constants import AgentStatus


# =============================================================================
# Reducers — tell LangGraph how to merge state updates
# =============================================================================

def _replace(existing: Any, new: Any) -> Any:
    """Replace the existing value entirely (for single-value fields)."""
    return new


def _append(existing: list | None, new: list | None) -> list:
    """Append new items to the existing list (for log/history fields)."""
    if existing is None:
        existing = []
    if new is None:
        return existing
    return existing + new


# =============================================================================
# AgentState — the central memory of the agent
# =============================================================================

class AgentState(TypedDict, total=False):
    """
    Central state object for the agent graph.
    
    This state flows through all nodes. Each node receives the FULL state,
    and returns a DICTIONARY with only the fields it wants to update.
    
    Fields marked with `Annotated[..., _append]` are lists that grow over time.
    Fields marked with `Annotated[..., _replace]` are overwritten each time.
    
    Visual diagram of the state lifecycle:
    
        [START]
           │
           ▼  question, audio_path, max_steps, temp_dir  (set once)
        ┌─────────────────────────────────────────────────────────┐
        │  question_oriented_prompt  ← initial_prompt_node        │
        │  initial_frontend_output   ← frontend_evidence_node     │
        │  initial_plan              ← initial_plan_node          │
        │  current_decision          ← planner_decision_node      │
        │  latest_tool_result        ← tool_executor_node         │
        │  evidence_log (growing)    ← evidence_fusion_node       │
        │  tool_call_history (growing) ← tool_executor_node       │
        │  planner_trace (growing)   ← planner_decision_node      │
        │  evidence_summary          ← evidence_summarization_node│
        │  final_answer              ← final_answer_node          │
        │  step_count (increments)   ← evidence_fusion_node       │
        │  status                    ← various nodes              │
        └─────────────────────────────────────────────────────────┘
           │
           ▼  final_answer or error_message
         [END]
    """
    
    # ===== Inputs (set once at start, never change) =====
    question: str
    audio_path: str
    temp_dir: str
    max_steps: int
    config: dict[str, Any] | None
    
    # ===== Set by initial_prompt_node =====
    question_oriented_prompt: str | None
    
    # ===== Set by frontend_evidence_node =====
    initial_frontend_output: Annotated[FrontendOutput | None, _replace]
    
    # ===== Set by initial_plan_node =====
    initial_plan: Annotated[InitialPlan | None, _replace]
    
    # ===== Growing logs (accumulate over the loop) =====
    evidence_log: Annotated[list[EvidenceItem], _append]
    tool_call_history: Annotated[list[ToolCallRecord], _append]
    planner_trace: Annotated[list[PlannerDecision], _append]
    
    # ===== Current cycle state (overwritten each iteration) =====
    current_decision: Annotated[PlannerDecision | None, _replace]
    latest_tool_result: Annotated[ToolResult | None, _replace]
    
    # ===== Set by evidence_summarization_node =====
    evidence_summary: str | None
    
    # ===== Final outputs =====
    final_answer: Annotated[FinalAnswer | None, _replace]
    error_message: Annotated[str | None, _replace]
    
    # ===== Counters and status =====
    step_count: int
    status: AgentStatus


# =============================================================================
# Factory function
# =============================================================================

def create_initial_state(
    question: str,
    audio_path: str,
    max_steps: int = 10,
    temp_dir: str | None = None,
    config: dict[str, Any] | None = None,
) -> AgentState:
    """
    Create a valid initial agent state.
    
    This is called once at the very beginning, before the graph starts running.
    It sets up all the "empty" fields so nodes can safely read them.
    
    Args:
        question: The user's question about the audio
        audio_path: Path to the audio file
        max_steps: Maximum steps before forcing termination
        temp_dir: Temporary directory for generated files
        config: Optional configuration dict
    
    Returns:
        A properly initialized AgentState with all fields set
    """
    if not question or not question.strip():
        raise ValueError("question must be a non-empty string")
    if not audio_path or not audio_path.strip():
        raise ValueError("audio_path must be a non-empty string")
    if max_steps < 1:
        raise ValueError("max_steps must be at least 1")
    
    return AgentState(
        question=question.strip(),
        audio_path=audio_path.strip(),
        temp_dir=temp_dir or "",
        max_steps=max_steps,
        config=config,
        # Everything else starts empty
        question_oriented_prompt=None,
        initial_frontend_output=None,
        initial_plan=None,
        evidence_log=[],
        tool_call_history=[],
        planner_trace=[],
        current_decision=None,
        latest_tool_result=None,
        evidence_summary=None,
        final_answer=None,
        error_message=None,
        step_count=0,
        status=AgentStatus.RUNNING,
    )
