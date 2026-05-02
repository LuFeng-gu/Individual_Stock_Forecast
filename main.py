"""
Main entry point for the audio agent.

Usage:
    # With API key via CLI
    python main.py --audio test.wav --question "What is happening?" --api-key sk-xxx

    # With API key in .env file (auto-loaded)
    python main.py --audio test.wav --question "What is happening?"

    # With execution tracing enabled
    python main.py --audio test.wav --question "What is happening?" --trace --trace-dir ./traces

This script:
1. Loads configuration (.env + CLI args)
2. Creates all agent components
3. Builds the LangGraph workflow
4. Runs the agent on the given audio + question
5. Prints the final answer
6. Optionally writes trace files (trace.jsonl + trace_report.md)
"""

import sys
from pathlib import Path

# Ensure project root is on path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config import load_config, AgentConfig
from core.state import create_initial_state
from core.constants import AgentStatus
from core.logging import log_info, log_error
from frontend import OpenAICompatibleFrontend
from planner import OpenAICompatiblePlanner
from fusion import SimpleFusion
from tools import ToolRegistry, ToolExecutor, register_all_mcp_tools
from tools.mcp import MCPServerManager
from graph import build_agent_graph, write_traces, set_trace_dir


def create_components(config: AgentConfig):
    """
    Create and wire all agent components.

    Args:
        config: Loaded agent configuration

    Returns:
        Tuple of (frontend, planner, fusion, executor, registry)
    """
    log_info("main", {"event": "creating_components"})

    # Frontend: audio-capable model
    frontend = OpenAICompatibleFrontend(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.frontend_model,
    )

    # Planner: text reasoning model
    planner = OpenAICompatiblePlanner(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.planner_model,
    )

    # Fusion: evidence conversion
    fusion = SimpleFusion()

    # Tools: registry + executor
    registry = ToolRegistry()
    executor = ToolExecutor(registry)

    # Auto-discover MCP tools from catalog/
    log_info("main", {"event": "scanning_catalog"})
    server_manager = MCPServerManager()
    # Note: register_all_mcp_tools is async, but we run it sync here
    import asyncio
    try:
        asyncio.run(register_all_mcp_tools(registry, server_manager, verbose=config.verbose))
    except RuntimeError:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(register_all_mcp_tools(registry, server_manager, verbose=config.verbose))
    except Exception as e:
        log_error("main", RuntimeError(f"MCP catalog scan failed: {e}"))

    tool_specs = registry.list_specs()
    log_info("main", {"event": "components_ready", "tools_registered": len(tool_specs)})

    return frontend, planner, fusion, executor, registry


def run_agent(config: AgentConfig):
    """
    Run the agent on a single audio file + question.

    Args:
        config: Agent configuration with audio_path, question, api_key, etc.

    Returns:
        Final agent state dictionary
    """
    if not config.is_valid:
        print("Error: Missing required configuration. Need --audio, --question, and --api-key")
        sys.exit(1)

    # Create components
    frontend, planner, fusion, executor, registry = create_components(config)

    # Setup trace if enabled
    if config.trace:
        set_trace_dir(config.trace_dir)
        print(f"[Run] Trace enabled. Output dir: {config.trace_dir}")

    # Build graph
    graph = build_agent_graph(
        planner, frontend, fusion, executor, registry,
        enable_trace=config.trace,
    )

    # Create initial state
    initial_state = create_initial_state(
        question=config.question,
        audio_path=config.audio_path,
        max_steps=config.max_steps,
    )

    # Run!
    log_info("main", {"event": "graph_invoke_start", "question": config.question})
    try:
        final_state = graph.invoke(initial_state)
        log_info("main", {"event": "graph_invoke_end", "status": final_state.get("status")})
    except Exception as e:
        log_error("main", RuntimeError(f"Agent execution failed: {e}"))
        final_state = {"status": "failed", "error_message": str(e)}
    finally:
        # Write traces even if execution failed
        if config.trace:
            jsonl_path, md_path = write_traces(config.trace_dir)
            if jsonl_path:
                print(f"[Trace] JSONL: {jsonl_path}")
                print(f"[Trace] Markdown: {md_path}")

    return final_state


def print_results(final_state: dict):
    """Pretty-print the agent's final output."""
    status = final_state.get("status")

    print("\n" + "=" * 60)
    print("AGENT RESULT")
    print("=" * 60)

    if status == AgentStatus.ANSWERED:
        final_answer = final_state.get("final_answer")
        if final_answer:
            print(f"\nAnswer: {final_answer.answer}")
            print(f"Confidence: {final_answer.confidence}")
            if final_answer.evidence_summary:
                print(f"\nEvidence Summary:\n{final_answer.evidence_summary}")
        else:
            print("\nStatus: ANSWERED but no final_answer found")

    elif status == AgentStatus.FAILED:
        error = final_state.get("error_message", "Unknown error")
        print(f"\nAgent failed: {error}")

    else:
        print(f"\nUnexpected final status: {status}")

    # Debug info
    step_count = final_state.get("step_count", 0)
    tool_history = final_state.get("tool_call_history", [])
    evidence_count = len(final_state.get("evidence_log", []))

    print(f"\nSteps taken: {step_count}")
    print(f"Tools called: {len(tool_history)}")
    print(f"Evidence items: {evidence_count}")
    print("=" * 60)


def main():
    """CLI entry point."""
    config = load_config()
    final_state = run_agent(config)
    print_results(final_state)


if __name__ == "__main__":
    main()
