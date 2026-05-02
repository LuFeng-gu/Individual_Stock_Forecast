"""
Pydantic schemas for structured data throughout the agent framework.

These schemas define explicit contracts between components.
All schemas use Pydantic v2 with strict validation.

Think of this file as the "data dictionary" of the entire project:
every piece of structured data flowing between frontend, planner, tools,
and graph nodes is defined here.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


# =============================================================================
# Enums
# =============================================================================

class PlannerActionType(str, Enum):
    """
    Actions the planner can decide to take.
    
    These are the ONLY three actions our 7-node graph supports:
    - ANSWER: Ready to generate final answer
    - CALL_TOOL: Need to invoke a tool for more evidence
    - FAIL: Unrecoverable state, stop execution
    """
    ANSWER = "answer"
    CALL_TOOL = "call_tool"
    FAIL = "fail"


# =============================================================================
# Frontend Schemas
# =============================================================================

class FrontendInput(BaseModel):
    """Input to the frontend module — a question about one audio file."""
    question: str = Field(..., min_length=1, description="User question about the audio")
    audio_path: str = Field(..., min_length=1, description="Path to the audio file")


class FrontendOutput(BaseModel):
    """
    Output from the frontend module.
    
    The frontend (audio-capable LLM) processes the audio and produces
    a caption focused on information relevant to the user question.
    """
    question_guided_caption: str = Field(
        ...,
        min_length=1,
        description="Caption focused on info relevant to the user question",
    )
    timestamp: datetime = Field(default_factory=datetime.now)
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_caption(self) -> "FrontendOutput":
        if not self.question_guided_caption.strip():
            raise ValueError("caption must be non-empty after stripping")
        return self


# =============================================================================
# Evidence Schemas
# =============================================================================

class EvidenceItem(BaseModel):
    """
    A single piece of evidence accumulated during agent execution.
    
    Evidence can come from the frontend caption, tool results, or fusion.
    The planner uses the evidence_log (a list of these) to make decisions.
    """
    source: str = Field(..., description="Source: 'frontend', tool name, etc.")
    content: str = Field(..., description="The evidence content")
    evidence_type: str = Field(default="text", description="Type: text, structured, etc.")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)


# =============================================================================
# Tool Schemas
# =============================================================================

class ToolSpec(BaseModel):
    """
    Specification of a tool, exposed to the planner for decision-making.
    
    The planner sees a list of these and decides which tool to call.
    """
    name: str = Field(..., min_length=1, description="Unique tool identifier")
    description: str = Field(..., description="What this tool does")
    input_schema: dict[str, Any] = Field(default_factory=dict, description="Expected input format (JSON schema)")
    output_schema: dict[str, Any] = Field(default_factory=dict, description="Expected output format")
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")


class ToolCallRequest(BaseModel):
    """Request to invoke a tool."""
    tool_name: str = Field(..., min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict, description="Optional context (e.g., current step, question)")


class ToolResult(BaseModel):
    """Result returned by a tool after execution."""
    tool_name: str = Field(...)
    success: bool = Field(...)
    output: dict[str, Any] = Field(default_factory=dict, description="Structured output from the tool")
    error_message: str | None = Field(default=None)
    execution_time_ms: float = Field(default=0.0)
    timestamp: datetime = Field(default_factory=datetime.now)


class ToolCallRecord(BaseModel):
    """Record of a tool call for history tracking. Stores request + result together."""
    request: ToolCallRequest
    result: ToolResult
    step_number: int = Field(ge=0)


# =============================================================================
# Planner Schemas
# =============================================================================

class ExecutionStep(BaseModel):
    """A single step in the execution plan."""
    step_number: int = Field(..., ge=1, description="Step order: 1, 2, 3...")
    description: str = Field(..., min_length=1, description="What this step does")
    tool_type: str | None = Field(default=None, description="Suggested tool category")
    expected_output: str | None = Field(default=None, description="What we expect from this step")
    model_config = {"extra": "forbid"}


class InitialPlan(BaseModel):
    """
    Initial high-level plan generated by the planner.
    
    Created after the frontend produces its caption. Guides the planner's
    subsequent decisions about which tools to call.
    """
    approach: str = Field(..., min_length=1, description="High-level strategy")
    focus_points: list[str] = Field(default_factory=list, description="Key aspects to focus on")
    possible_tool_types: list[str] = Field(default_factory=list, description="Tool categories that may help")
    clarified_intent: str | None = Field(default=None, description="What the question is really asking")
    expected_output_format: str | None = Field(default=None, description="Expected format of final answer")
    detailed_plan: list[ExecutionStep] = Field(default_factory=list, description="Optional todo list for complex questions")
    timestamp: datetime = Field(default_factory=datetime.now)
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_plan(self) -> "InitialPlan":
        if not self.approach.strip():
            raise ValueError("approach must be non-empty")
        return self


class PlannerDecision(BaseModel):
    """
    Decision made by the planner at each step.
    
    This is the "brain's output" — it tells the graph what to do next.
    - ANSWER: go to evidence_summarization → final_answer
    - CALL_TOOL: go to tool_executor (needs selected_tool_name)
    - FAIL: go to failure_node
    """
    action: PlannerActionType
    rationale: str = Field(..., min_length=1, description="Why this decision was made")
    selected_tool_name: str | None = Field(default=None)
    selected_tool_args: dict[str, Any] = Field(default_factory=dict)
    selected_audio_id: str | None = Field(default=None, description="Optional audio ID for multi-audio scenarios")
    draft_answer: str | None = Field(default=None, description="Draft answer if action is ANSWER")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=datetime.now)
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_action_consistency(self) -> "PlannerDecision":
        """Ensure action-specific fields are populated."""
        if self.action == PlannerActionType.CALL_TOOL:
            if not self.selected_tool_name:
                raise ValueError("CALL_TOOL requires selected_tool_name")
        return self


# =============================================================================
# Final Answer Schema
# =============================================================================

class FinalAnswer(BaseModel):
    """The final answer produced by the agent."""
    answer: str = Field(..., min_length=1)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_summary: str = Field(default="")
    reasoning_trace: str = Field(default="")
    timestamp: datetime = Field(default_factory=datetime.now)
