"""
Core module: contracts, state, and utilities.

This package contains the foundational data structures and constants
used by all other modules in the agent framework.
"""

from core.constants import AgentStatus
from core.errors import (
    AudioAgentError,
    FrontendError,
    PlannerError,
    ToolExecutionError,
    FusionError,
    StateValidationError,
)
from core.schemas import (
    PlannerActionType,
    FrontendInput,
    FrontendOutput,
    EvidenceItem,
    ToolSpec,
    ToolCallRequest,
    ToolResult,
    ToolCallRecord,
    ExecutionStep,
    InitialPlan,
    PlannerDecision,
    FinalAnswer,
)
from core.state import AgentState, create_initial_state
from core.logging import (
    log_node_start,
    log_node_end,
    log_planner_decision,
    log_error,
    log_info,
)

__all__ = [
    # Constants
    "AgentStatus",
    # Errors
    "AudioAgentError",
    "FrontendError",
    "PlannerError",
    "ToolExecutionError",
    "FusionError",
    "StateValidationError",
    # Schemas
    "PlannerActionType",
    "FrontendInput",
    "FrontendOutput",
    "EvidenceItem",
    "ToolSpec",
    "ToolCallRequest",
    "ToolResult",
    "ToolCallRecord",
    "ExecutionStep",
    "InitialPlan",
    "PlannerDecision",
    "FinalAnswer",
    # State
    "AgentState",
    "create_initial_state",
    # Logging
    "log_node_start",
    "log_node_end",
    "log_planner_decision",
    "log_error",
    "log_info",
]
