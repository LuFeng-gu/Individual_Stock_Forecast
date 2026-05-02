"""
LangGraph node functions for the agent workflow.

Each function takes the current AgentState and returns a dictionary of updates.
LangGraph merges these updates into the state using the reducers defined in state.py.

Dependencies (planner, frontend, fusion, executor, registry) are injected via
functools.partial in builder.py.
"""

from core.schemas import (
    ToolCallRequest,
    ToolCallRecord,
    FinalAnswer,
)
import asyncio

from core.state import AgentState
from core.constants import AgentStatus
from core.logging import log_node_start, log_node_end, log_info, log_error, log_planner_decision
from frontend.base import BaseFrontend
from planner.base import BasePlanner
from fusion.base import BaseFusion
from tools.registry import ToolRegistry
from tools.executor import ToolExecutor


def _run_async(coro):
    """Run an async coroutine, handling both sync and async contexts."""
    import inspect
    if not inspect.iscoroutine(coro):
        # Already a sync result (e.g., from mock or internal tool)
        return coro
    try:
        return asyncio.run(coro)
    except RuntimeError:
        # Already inside an event loop (e.g., Jupyter, or LangGraph async mode)
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(coro)


def _format_planner_trace(trace: list) -> str:
    """Format planner decision history into a readable string."""
    lines = []
    for i, decision in enumerate(trace, 1):
        lines.append(
            f"Step {i}: [{decision.action}] {decision.rationale[:100]}"
        )
    return "\n".join(lines)


# =============================================================================
# Initial Setup Nodes
# =============================================================================

def initial_prompt_node(state: AgentState, planner: BasePlanner) -> dict:
    """
    Generate a question-oriented prompt to guide the frontend.

    Called once at the start. The prompt helps the frontend produce a
    more focused caption relevant to the user's question.
    """
    log_node_start("initial_prompt_node")
    prompt = planner.generate_question_oriented_prompt(state["question"])
    log_node_end("initial_prompt_node")
    log_info("initial_prompt", {"prompt_length": len(prompt)})
    return {"question_oriented_prompt": prompt}


def frontend_evidence_node(
    state: AgentState,
    frontend: BaseFrontend,
    fusion: BaseFusion,
) -> dict:
    """
    Run the frontend on the audio and convert output to evidence.

    Produces both the raw FrontendOutput (for the planner) and an
    EvidenceItem (for the evidence log).
    """
    log_node_start("frontend_evidence_node")

    fe_out = frontend.run(
        question=state["question"],
        audio_path=state["audio_path"],
        question_oriented_prompt=state.get("question_oriented_prompt"),
    )
    evidence = fusion.frontend_to_evidence(fe_out)

    log_node_end("frontend_evidence_node")
    log_info("frontend_evidence", {"caption_preview": fe_out.question_guided_caption[:80]})
    return {
        "initial_frontend_output": fe_out,
        "evidence_log": [evidence],
    }


def initial_plan_node(state: AgentState, planner: BasePlanner) -> dict:
    """
    Generate the initial plan from question + frontend caption.

    Called once after frontend produces its caption.
    """
    log_node_start("initial_plan_node")
    plan = planner.plan(
        question=state["question"],
        frontend_output=state.get("initial_frontend_output"),
    )
    log_node_end("initial_plan_node")
    log_info("initial_plan", {"approach_preview": plan.approach[:80]})
    return {"initial_plan": plan}


# =============================================================================
# Decision & Loop Nodes
# =============================================================================

def planner_decision_node(
    state: AgentState,
    planner: BasePlanner,
    registry: ToolRegistry,
) -> dict:
    """
    The brain of the agent. Decides what to do next.

    Returns ANSWER, CALL_TOOL, or FAIL. The graph routes based on this.
    """
    log_node_start("planner_decision_node")

    available_tools = registry.list_specs()
    decision = planner.decide(state, available_tools)

    log_node_end("planner_decision_node")
    log_planner_decision(decision.action, decision.rationale[:120])
    return {
        "current_decision": decision,
        "planner_trace": [decision],
    }


def tool_executor_node(
    state: AgentState,
    executor: ToolExecutor,
) -> dict:
    """
    Execute the tool selected by the planner.

    The executor interface is async (for MCP tools), but LangGraph's
    sync invoke() requires sync nodes. We bridge with _run_async().
    """
    log_node_start("tool_executor_node")

    decision = state["current_decision"]
    if not decision or not decision.selected_tool_name:
        log_error("tool_executor", RuntimeError("No tool selected in current_decision"))
        return {
            "latest_tool_result": None,
            "tool_call_history": [],
        }

    request = ToolCallRequest(
        tool_name=decision.selected_tool_name,
        args=decision.selected_tool_args,
    )

    result = _run_async(executor.execute(request))
    record = ToolCallRecord(
        request=request,
        result=result,
        step_number=state.get("step_count", 0),
    )

    log_node_end("tool_executor_node")
    status = "OK" if result.success else "FAIL"
    log_info("tool_executor", {"tool": decision.selected_tool_name, "status": status})
    return {
        "latest_tool_result": result,
        "tool_call_history": [record],
    }


def evidence_fusion_node(state: AgentState, fusion: BaseFusion) -> dict:
    """
    Convert the latest tool result into evidence and append to log.

    Also increments step_count to track how many tool calls we've made.
    """
    log_node_start("evidence_fusion_node")

    tool_result = state.get("latest_tool_result")
    if tool_result is None:
        log_error("evidence_fusion", RuntimeError("No latest_tool_result to fuse"))
        return {"step_count": state.get("step_count", 0) + 1}

    evidence = fusion.tool_result_to_evidence(tool_result)
    new_step = state.get("step_count", 0) + 1

    log_node_end("evidence_fusion_node")
    log_info("evidence_fusion", {"source": evidence.source, "step": new_step})
    return {
        "evidence_log": [evidence],
        "step_count": new_step,
    }


# =============================================================================
# Finalization Nodes
# =============================================================================

def evidence_summarization_node(state: AgentState, planner: BasePlanner) -> dict:
    """
    Summarize all accumulated evidence before final answer generation.

    The summary is passed to the frontend along with the audio.
    """
    log_node_start("evidence_summarization_node")
    summary = planner.summarize_evidence(state)
    log_node_end("evidence_summarization_node")
    log_info("evidence_summary", {"summary_length": len(summary)})
    return {"evidence_summary": summary}


def final_answer_node(state: AgentState, frontend: BaseFrontend) -> dict:
    """
    Generate the final answer using the frontend model.

    The frontend sees the original audio plus all accumulated evidence.
    """
    log_node_start("final_answer_node")

    context = {
        "evidence_summary": state.get("evidence_summary", ""),
        "planner_trace": state.get("planner_trace", []),
        "initial_plan": state.get("initial_plan"),
        "evidence_log": state.get("evidence_log", []),
    }

    answer_text = frontend.generate_final_answer(
        question=state["question"],
        audio_path=state["audio_path"],
        context=context,
    )

    decision = state.get("current_decision")
    confidence = decision.confidence if decision else 0.0

    final = FinalAnswer(
        answer=answer_text,
        confidence=confidence,
        evidence_summary=state.get("evidence_summary", ""),
        reasoning_trace=_format_planner_trace(state.get("planner_trace", [])),
    )

    log_node_end("final_answer_node")
    log_info("final_answer", {"answer_length": len(answer_text)})
    return {
        "final_answer": final,
        "status": AgentStatus.ANSWERED,
    }


def failure_node(state: AgentState) -> dict:
    """
    Handle failure states. Sets error message and final status.

    Called when planner decides FAIL or when max_steps is exceeded.
    """
    log_node_start("failure_node")

    decision = state.get("current_decision")
    if decision and decision.rationale:
        error_msg = decision.rationale
    else:
        error_msg = state.get("error_message") or "Agent execution failed"

    log_error("failure_node", RuntimeError(error_msg))
    log_node_end("failure_node")
    return {
        "error_message": error_msg,
        "status": AgentStatus.FAILED,
    }
