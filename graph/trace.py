"""
Execution tracing for the agent graph.

When enabled, every node's input state and output update is recorded
with timestamps and elapsed time. Traces are written to:
- trace.jsonl   (machine-readable, one JSON per line)
- trace_report.md (human-readable Markdown)

Usage:
    from graph import build_agent_graph
    graph = build_agent_graph(..., enable_trace=True, trace_dir="./traces")
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel


_TRACE_ENTRIES: list[dict] = []
_TRACE_DIR: Path = Path(".")


def clear_trace() -> None:
    """Clear accumulated trace entries."""
    global _TRACE_ENTRIES
    _TRACE_ENTRIES = []


def get_trace_entries() -> list[dict]:
    """Return all trace entries."""
    return _TRACE_ENTRIES.copy()


def set_trace_dir(path: str | Path) -> None:
    """Set the directory where trace files will be written."""
    global _TRACE_DIR
    _TRACE_DIR = Path(path)
    _TRACE_DIR.mkdir(parents=True, exist_ok=True)


def _is_likely_base64(s: str) -> bool:
    """Heuristic to detect base64-encoded binary data."""
    if not isinstance(s, str) or len(s) < 100:
        return False
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
    return len(set(s) - allowed) <= 2


def serialize_for_trace(obj: Any, depth: int = 0, max_depth: int = 10) -> Any:
    """Serialize objects for tracing, filtering out base64 data."""
    if depth > max_depth:
        return "<max depth reached>"

    if isinstance(obj, BaseModel):
        return serialize_for_trace(obj.model_dump(), depth + 1, max_depth)

    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            if isinstance(v, str) and _is_likely_base64(v):
                result[k] = f"<base64 data, {len(v)} chars>"
            else:
                result[k] = serialize_for_trace(v, depth + 1, max_depth)
        return result

    if isinstance(obj, list):
        return [serialize_for_trace(item, depth + 1, max_depth) for item in obj]

    if isinstance(obj, bytes):
        return f"<bytes, length={len(obj)}>"

    if isinstance(obj, datetime):
        return obj.isoformat()

    return obj


def make_traced_node(node_func, node_name: str):
    """Wrap a node function to record its execution."""
    import time

    def wrapper(state, *args, **kwargs):
        start_time = time.time()
        start_iso = datetime.now().isoformat()

        input_snapshot = serialize_for_trace(dict(state))
        result = node_func(state, *args, **kwargs)
        if result is None:
            result = {}

        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        _TRACE_ENTRIES.append({
            "node": node_name,
            "timestamp": start_iso,
            "elapsed_ms": elapsed_ms,
            "input": input_snapshot,
            "output": serialize_for_trace(result),
        })
        return result

    wrapper.__name__ = f"traced_{node_name}"
    return wrapper


def write_traces(trace_dir: str | Path | None = None) -> tuple[Path, Path]:
    """
    Write trace entries to JSONL and Markdown files.

    Returns:
        (jsonl_path, markdown_path)
    """
    import json

    out_dir = Path(trace_dir) if trace_dir else _TRACE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    entries = get_trace_entries()
    if not entries:
        return None, None

    # Write JSONL
    jsonl_path = out_dir / "trace.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

    # Write Markdown
    md_path = out_dir / "trace_report.md"
    lines = ["# Agent Execution Trace Report", ""]

    for i, entry in enumerate(entries, 1):
        node_name = entry["node"]
        lines.append(f"## Step {i}: `{node_name}` ({entry['elapsed_ms']} ms)")
        lines.append("")
        lines.append(f"- **Timestamp**: {entry['timestamp']}")
        lines.append("")

        lines.append("### Input State")
        lines.append("```json")
        lines.append(json.dumps(entry["input"], ensure_ascii=False, indent=2, default=str))
        lines.append("```")
        lines.append("")

        lines.append("### Output Update")
        lines.append("```json")
        lines.append(json.dumps(entry["output"], ensure_ascii=False, indent=2, default=str))
        lines.append("```")
        lines.append("")

        # Special summaries for key nodes
        output = entry.get("output", {})
        if node_name == "planner_decision_node":
            decision = output.get("current_decision", {})
            if decision:
                action = decision.get("action", "")
                rationale = decision.get("rationale", "")
                tool = decision.get("selected_tool_name", "")
                lines.append(f"> **Decision**: `{action}`")
                if tool:
                    lines.append(f"> **Tool**: `{tool}`")
                lines.append(f"> **Rationale**: {rationale}")
                lines.append("")

        elif node_name == "tool_executor_node":
            result = output.get("latest_tool_result", {})
            if result:
                success = result.get("success", False)
                tool_name = result.get("tool_name", "")
                out_data = result.get("output", {})
                lines.append(f"> **Result**: `{tool_name}` | Success: {success}")
                lines.append(f"> **Data**: `{json.dumps(out_data, ensure_ascii=False, default=str)}`")
                lines.append("")

        elif node_name == "final_answer_node":
            final = output.get("final_answer", {})
            if final:
                answer = final.get("answer", "")
                conf = final.get("confidence", 0)
                lines.append(f"> **Answer**: {answer}")
                lines.append(f"> **Confidence**: {conf}")
                lines.append("")

        lines.append("---")
        lines.append("")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return jsonl_path, md_path
