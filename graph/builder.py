"""
Build and compile the LangGraph agent workflow.

This module wires all nodes together into a StateGraph and defines
the conditional edges that create the agent's decision loop.
"""

from functools import partial

from langgraph.graph import StateGraph, END

from core.state import AgentState
from core.logging import log_info, log_error
from frontend.base import BaseFrontend
from planner.base import BasePlanner
from fusion.base import BaseFusion
from tools.registry import ToolRegistry
from tools.executor import ToolExecutor
from graph.trace import make_traced_node, clear_trace
from graph.nodes import (
    initial_prompt_node,
    frontend_evidence_node,
    initial_plan_node,
    planner_decision_node,
    tool_executor_node,
    evidence_fusion_node,
    evidence_summarization_node,
    final_answer_node,
    failure_node,
)


def _route_after_decision(state: AgentState) -> str:
    """
    Conditional routing after planner_decision_node.

    Reads the planner's decision and routes to:
    - "evidence_summarization" if ANSWER
    - "tool_executor" if CALL_TOOL
    - "failure" if FAIL or max_steps exceeded
    """
    step_count = state.get("step_count", 0)
    max_steps = state.get("max_steps", 10)
    decision = state.get("current_decision")

    # Guard: force failure if max steps reached
    if step_count >= max_steps:
        log_error("router", RuntimeError(f"Max steps ({max_steps}) reached"))
        return "failure"

    if not decision:
        log_error("router", RuntimeError("No decision found in state"))
        return "failure"

    action = decision.action.value if hasattr(decision.action, "value") else decision.action

    if action == "answer":
        return "evidence_summarization"
    elif action == "call_tool":
        return "tool_executor"
    else:
        return "failure"


def build_agent_graph(
    planner: BasePlanner,
    frontend: BaseFrontend,
    fusion: BaseFusion,
    executor: ToolExecutor,
    registry: ToolRegistry,
    enable_trace: bool = False,
) -> StateGraph:
    """
    Build and compile the complete agent workflow graph.

    Args:
        planner: Decision-making component
        frontend: Audio understanding component
        fusion: Evidence conversion component
        executor: Tool execution component
        registry: Tool registration component
        enable_trace: If True, wrap all nodes to record input/output

    Returns:
        A compiled LangGraph ready to be invoked with an AgentState
    """
    log_info("graph_builder", {"event": "building_graph", "trace": enable_trace})

    if enable_trace:
        clear_trace()

    # Helper to optionally wrap a node with tracer
    def bind(node_func, **kwargs):
        wrapped = make_traced_node(node_func, node_func.__name__) if enable_trace else node_func
        return partial(wrapped, **kwargs)

    # ------------------------------------------------------------------
    # Bind dependencies to node functions via partial
    # ------------------------------------------------------------------
    bound_prompt = bind(initial_prompt_node, planner=planner)
    bound_frontend = bind(frontend_evidence_node, frontend=frontend, fusion=fusion)
    bound_plan = bind(initial_plan_node, planner=planner)
    bound_decide = bind(planner_decision_node, planner=planner, registry=registry)
    bound_execute = bind(tool_executor_node, executor=executor)
    bound_fuse = bind(evidence_fusion_node, fusion=fusion)
    bound_summarize = bind(evidence_summarization_node, planner=planner)
    bound_answer = bind(final_answer_node, frontend=frontend)
    bound_fail = make_traced_node(failure_node, "failure_node") if enable_trace else failure_node

    # ------------------------------------------------------------------
    # Create the graph
    # ------------------------------------------------------------------
    graph = StateGraph(AgentState)

    # ------------------------------------------------------------------
    # Add nodes
    # ------------------------------------------------------------------
    graph.add_node("initial_prompt", bound_prompt)
    graph.add_node("frontend_evidence", bound_frontend)
    graph.add_node("initial_plan", bound_plan)
    graph.add_node("planner_decision", bound_decide)
    graph.add_node("tool_executor", bound_execute)
    graph.add_node("evidence_fusion", bound_fuse)
    graph.add_node("evidence_summarization", bound_summarize)
    graph.add_node("final_answer", bound_answer)
    graph.add_node("failure", bound_fail)

    # ------------------------------------------------------------------
    # Define edges
    # ------------------------------------------------------------------
    # Entry point
    graph.set_entry_point("initial_prompt")

    # Linear startup sequence
    graph.add_edge("initial_prompt", "frontend_evidence")
    graph.add_edge("frontend_evidence", "initial_plan")
    graph.add_edge("initial_plan", "planner_decision")

    # Conditional branch from decision
    graph.add_conditional_edges(
        "planner_decision",
        _route_after_decision,
        {
            "evidence_summarization": "evidence_summarization",
            "tool_executor": "tool_executor",
            "failure": "failure",
        },
    )

    # Tool execution loop
    graph.add_edge("tool_executor", "evidence_fusion")
    graph.add_edge("evidence_fusion", "planner_decision")

    # Answer path
    graph.add_edge("evidence_summarization", "final_answer")
    graph.add_edge("final_answer", END)

    # Failure path
    graph.add_edge("failure", END)

    log_info("graph_builder", {"event": "graph_built"})
    return graph.compile()
