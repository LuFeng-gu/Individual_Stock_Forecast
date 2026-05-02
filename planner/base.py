"""
Abstract base class for planner modules.

The planner is the "brain" of the agent. It makes decisions about:
- What the initial approach should be (plan)
- What action to take next (decide)
- How to summarize evidence before final answer
- How to generate a question-oriented prompt for the frontend
"""

from abc import ABC, abstractmethod

from core.state import AgentState
from core.schemas import FrontendOutput, InitialPlan, PlannerDecision, ToolSpec
from core.errors import PlannerError


class BasePlanner(ABC):
    """
    Abstract base class for planners.
    
    The planner has four main jobs:
    1. plan() — Create initial strategy from question + caption
    2. decide() — Choose next action based on current state
    3. generate_question_oriented_prompt() — Craft a better prompt for frontend
    4. summarize_evidence() — Compress all evidence into a narrative
    
    Concrete implementations might use:
    - Local LLMs (Qwen2.5, etc.)
    - Remote API-based LLMs (OpenAI, DashScope, etc.)
    - Rule-based planners for testing
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this planner for logging."""
        raise NotImplementedError

    @abstractmethod
    def plan(self, question: str, frontend_output: FrontendOutput | None = None) -> InitialPlan:
        """
        Build an initial plan using question and optional frontend caption.
        
        Called once at the start, after frontend produces its caption.
        
        Args:
            question: User's question about the audio
            frontend_output: Caption from the frontend (may be None initially)
        
        Returns:
            InitialPlan with approach, focus_points, etc.
        """
        raise NotImplementedError

    @abstractmethod
    def generate_question_oriented_prompt(self, question: str) -> str:
        """
        Generate a customized prompt to guide the frontend audio model.
        
        This is called by initial_prompt_node BEFORE the frontend runs.
        The output helps the frontend produce a richer, more targeted caption.
        
        Args:
            question: User's original question
        
        Returns:
            A prompt string that decomposes the question into focus points
        """
        raise NotImplementedError

    @abstractmethod
    def decide(self, state: AgentState, available_tools: list[ToolSpec]) -> PlannerDecision:
        """
        Make a decision based on current state and available tools.
        
        This is called at each step of the loop. The planner reviews all
        evidence and decides what to do next.
        
        Args:
            state: Current agent state with evidence, history, etc.
            available_tools: List of tools the planner can choose from
        
        Returns:
            PlannerDecision with action (answer/call_tool/fail)
        """
        raise NotImplementedError

    @abstractmethod
    def summarize_evidence(self, state: AgentState) -> str:
        """
        Summarize all accumulated evidence into a concise narrative.
        
        Called before final_answer_node. The summary is given to the frontend
        model along with the audio, so it can generate a well-informed answer.
        
        Args:
            state: Current agent state with full evidence log
        
        Returns:
            A neutral, comprehensive summary string
        """
        raise NotImplementedError

    def validate_state(self, state: AgentState) -> None:
        """
        Validate that state has required fields for decision-making.
        
        Raises:
            PlannerError: If state is invalid
        """
        if not state.get("question"):
            raise PlannerError(
                "Cannot plan without a question",
                details={"state_keys": list(state.keys())}
            )
        if state.get("initial_frontend_output") is None:
            raise PlannerError(
                "Cannot decide without frontend output",
                details={"question": state.get("question")}
            )
        if state.get("initial_plan") is None:
            raise PlannerError(
                "Cannot decide without initial plan",
                details={"question": state.get("question")}
            )

    def validate_question(self, question: str) -> str:
        """Validate and return stripped question."""
        if not question or not isinstance(question, str):
            raise PlannerError(
                "Question must be a non-empty string",
                details={"question_type": type(question).__name__}
            )
        stripped = question.strip()
        if not stripped:
            raise PlannerError("Question must be a non-empty string")
        return stripped
