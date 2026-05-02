"""
Exception hierarchy for the agent framework.

All errors inherit from AudioAgentError, allowing callers to catch
agent-specific failures separately from generic Python exceptions.

Structure:
    AudioAgentError (base)
    ├── FrontendError      # Audio processing / caption generation failed
    ├── PlannerError       # Planning / decision-making failed
    ├── ToolExecutionError # Tool invocation failed
    ├── FusionError        # Evidence fusion failed
    └── StateValidationError # State is missing required fields
"""


class AudioAgentError(Exception):
    """
    Base exception for all agent-related errors.
    
    Args:
        message: Human-readable error description
        details: Optional dict with extra context (e.g., which tool failed)
    """

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} | details={self.details}"
        return self.message


class FrontendError(AudioAgentError):
    """Raised when the frontend (audio model) fails to process audio."""
    pass


class PlannerError(AudioAgentError):
    """Raised when the planner (text LLM) fails to plan or decide."""
    pass


class ToolExecutionError(AudioAgentError):
    """Raised when a tool invocation fails or returns invalid output."""
    pass


class FusionError(AudioAgentError):
    """Raised when evidence fusion fails to convert tool results."""
    pass


class StateValidationError(AudioAgentError):
    """Raised when the agent state is missing required fields or is malformed."""
    pass
