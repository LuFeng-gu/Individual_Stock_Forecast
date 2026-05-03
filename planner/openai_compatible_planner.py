"""
OpenAI-compatible API planner implementation.

This planner uses any OpenAI-compatible API endpoint for:
- Initial planning (plan)
- Decision-making (decide)
- Question-oriented prompt generation
- Evidence summarization

All prompts are loaded from external markdown files in prompts/.
"""

import json
import os
from pathlib import Path

from planner.base import BasePlanner
from core.state import AgentState
from core.schemas import (
    FrontendOutput,
    InitialPlan,
    PlannerDecision,
    PlannerActionType,
    ToolSpec,
    EvidenceItem,
)
from core.errors import PlannerError
from core.logging import log_node_start, log_node_end, log_error


class OpenAICompatiblePlanner(BasePlanner):
    """
    Planner that uses any OpenAI-compatible API for reasoning.
    
    Supports providers like OpenAI, DashScope, xi-ai.cn, etc.
    
    Args:
        model: Model name (default: "gpt-4o" or any text-capable model)
        api_key: API key. If None, reads from environment variable.
        base_url: API base URL
        max_retries: Number of retries on API failure
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str = "https://api-2.xi-ai.cn/v1",
        max_retries: int = 3,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        self._base_url = base_url
        self._max_retries = max_retries

        if not self._api_key:
            raise PlannerError(
                "No API key provided. Set OPENAI_API_KEY or DASHSCOPE_API_KEY env var, "
                "or pass api_key explicitly.",
            )

        try:
            from openai import OpenAI
        except ImportError:
            raise PlannerError("openai package not installed. Run: pip install openai")
        
        self._client = OpenAI(api_key=self._api_key, base_url=self._base_url, timeout=60.0)

    @property
    def name(self) -> str:
        return f"openai_compatible_planner_{self._model}"

    def generate_question_oriented_prompt(self, question: str) -> str:
        """
        Generate a customized prompt to guide the frontend.
        
        Called by initial_prompt_node BEFORE frontend runs.
        """
        log_node_start("planner.generate_question_oriented_prompt", {"question": question[:50]})
        
        question = self.validate_question(question)
        
        system_prompt = (
            "You are a prompt engineering expert. Your task is to take a user's "
            "question about an audio file and transform it into a detailed, "
            "task-oriented prompt that will guide an audio analysis model."
        )
        
        user_prompt = (
            f"User's question: {question}\n\n"
            f"Transform this into a detailed prompt that tells the audio analyst "
            f"exactly what to focus on. Include specific tasks and focus points."
        )
        
        try:
            prompt = self._call_api(system_prompt, user_prompt)
        except Exception as e:
            log_error("planner.generate_question_oriented_prompt", e)
            raise PlannerError(f"Failed to generate prompt: {e}") from e
        
        log_node_end("planner.generate_question_oriented_prompt", {"length": len(prompt)})
        return prompt

    def plan(
        self,
        question: str,
        frontend_output: FrontendOutput | None = None,
        available_tools: list[ToolSpec] | None = None,
    ) -> InitialPlan:
        """
        Create initial plan from question and frontend caption.
        
        Called by initial_plan_node after frontend produces caption.
        """
        log_node_start("planner.plan", {"question": question[:50]})
        
        question = self.validate_question(question)
        
        system_prompt = self._load_prompt("plan_system")
        user_template = self._load_prompt("plan_user")
        
        caption = frontend_output.question_guided_caption if frontend_output else "No caption available"
        tools_text = self._format_tools(available_tools or [])
        
        user_prompt = user_template.format(
            question=question,
            caption=caption,
            available_tools=tools_text,
        )
        
        try:
            response_text = self._call_api(system_prompt, user_prompt)
            plan = self._parse_plan_json(response_text)
        except Exception as e:
            log_error("planner.plan", e)
            raise PlannerError(f"Planning failed: {e}") from e
        
        log_node_end("planner.plan", {"approach": plan.approach[:50]})
        return plan

    def decide(self, state: AgentState, available_tools: list[ToolSpec]) -> PlannerDecision:
        """
        Make decision based on current state and available tools.
        
        Called by planner_decision_node at each step.
        """
        log_node_start("planner.decide")
        
        self.validate_state(state)
        
        system_prompt = self._load_prompt("decide_system")
        user_template = self._load_prompt("decide_user")
        rules = self._load_prompt("decide_rules")
        
        # Build evidence text
        evidence_items = state.get("evidence_log", [])
        evidence_text = self._format_evidence(evidence_items)
        
        # Build tool history text
        tool_history = state.get("tool_call_history", [])
        history_text = self._format_tool_history(tool_history)
        
        # Build available tools text
        tools_text = self._format_tools(available_tools)
        
        # Get frontend caption
        frontend_output = state.get("initial_frontend_output")
        caption = frontend_output.question_guided_caption if frontend_output else "N/A"
        
        # Get initial plan
        initial_plan = state.get("initial_plan")
        plan_text = initial_plan.approach if initial_plan else "N/A"
        
        user_prompt = user_template.format(
            question=state["question"],
            frontend_caption=caption,
            initial_plan=plan_text,
            evidence_count=len(evidence_items),
            evidence_log=evidence_text,
            tool_call_count=len(tool_history),
            tool_call_history=history_text,
            available_tools=tools_text,
            step_count=state.get("step_count", 0),
            max_steps=state.get("max_steps", 10),
        )
        
        # Append rules
        full_prompt = f"{user_prompt}\n\n{rules}"
        
        try:
            response_text = self._call_api(system_prompt, full_prompt)
            decision = self._parse_decision_json(response_text)
        except Exception as e:
            log_error("planner.decide", e)
            raise PlannerError(f"Decision failed: {e}") from e
        
        log_node_end("planner.decide", {"action": decision.action.value})
        return decision

    def summarize_evidence(self, state: AgentState) -> str:
        """
        Summarize all evidence into a concise narrative.
        
        Called by evidence_summarization_node before final answer.
        """
        log_node_start("planner.summarize_evidence")
        
        evidence_items = state.get("evidence_log", [])
        if not evidence_items:
            return "No evidence has been gathered."
        
        system_prompt = (
            "You are a neutral evidence summarizer. Your task is to compress "
            "multiple pieces of evidence into a single coherent narrative. "
            "Do not judge credibility or resolve contradictions. "
            "Simply report what has been found."
        )
        
        evidence_text = self._format_evidence(evidence_items)
        planner_trace = state.get("planner_trace", [])
        trace_text = "\n".join([f"Step {i+1}: {d.action.value} - {d.rationale[:100]}" 
                                for i, d in enumerate(planner_trace)])
        
        user_prompt = (
            f"Question: {state.get('question', 'N/A')}\n\n"
            f"Evidence:\n{evidence_text}\n\n"
            f"Planner decisions:\n{trace_text}\n\n"
            f"Please summarize all evidence into a concise narrative."
        )
        
        try:
            summary = self._call_api(system_prompt, user_prompt)
        except Exception as e:
            log_error("planner.summarize_evidence", e)
            raise PlannerError(f"Summarization failed: {e}") from e
        
        log_node_end("planner.summarize_evidence", {"length": len(summary)})
        return summary

    # =====================================================================
    # Private helpers
    # =====================================================================

    def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        """Call OpenAI-compatible API and return text response."""
        from openai import APIError, APIConnectionError, RateLimitError
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        
        last_error = None
        for attempt in range(self._max_retries):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    max_tokens=2048,
                    temperature=0.3,
                )
                return response.choices[0].message.content or ""
            except (APIError, APIConnectionError, RateLimitError) as e:
                last_error = e
                import time
                time.sleep(0.5 * (2 ** attempt))
                continue
        
        raise PlannerError(
            f"API call failed after {self._max_retries} retries: {last_error}",
            details={"model": self._model},
        )

    def _load_prompt(self, prompt_name: str) -> str:
        """Load a prompt from the prompts/ directory."""
        module_dir = Path(__file__).parent.parent
        prompt_path = module_dir / "prompts" / f"{prompt_name}.md"
        
        if not prompt_path.exists():
            raise PlannerError(
                f"Prompt file not found: {prompt_path}",
                details={"prompt_name": prompt_name},
            )
        
        return prompt_path.read_text(encoding="utf-8")

    def _parse_plan_json(self, text: str) -> InitialPlan:
        """Parse LLM response into InitialPlan."""
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code block
            if "```json" in text:
                json_text = text.split("```json")[1].split("```")[0].strip()
                data = json.loads(json_text)
            elif "```" in text:
                json_text = text.split("```")[1].split("```")[0].strip()
                data = json.loads(json_text)
            else:
                raise PlannerError(f"Failed to parse plan JSON: {text[:200]}")
        
        return InitialPlan(
            approach=data.get("approach", ""),
            focus_points=data.get("focus_points", []),
            possible_tool_types=data.get("possible_tool_types", []),
            clarified_intent=data.get("clarified_intent"),
            expected_output_format=data.get("expected_output_format"),
        )

    def _parse_decision_json(self, text: str) -> PlannerDecision:
        """Parse LLM response into PlannerDecision."""
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            if "```json" in text:
                json_text = text.split("```json")[1].split("```")[0].strip()
                data = json.loads(json_text)
            elif "```" in text:
                json_text = text.split("```")[1].split("```")[0].strip()
                data = json.loads(json_text)
            else:
                raise PlannerError(f"Failed to parse decision JSON: {text[:200]}")
        
        action_str = data.get("action", "fail").lower()
        action = PlannerActionType(action_str)
        
        return PlannerDecision(
            action=action,
            rationale=data.get("rationale", "No rationale provided"),
            selected_tool_name=data.get("selected_tool_name"),
            selected_audio_id=data.get("selected_audio_id"),
            draft_answer=data.get("draft_answer"),
            confidence=data.get("confidence", 0.5),
        )

    def _format_evidence(self, evidence_items: list[EvidenceItem]) -> str:
        """Format evidence items as readable text."""
        if not evidence_items:
            return "No evidence yet."
        lines = []
        for i, item in enumerate(evidence_items, 1):
            lines.append(f"{i}. [{item.source}] {item.content[:200]}")
        return "\n".join(lines)

    def _format_tool_history(self, tool_calls: list) -> str:
        """Format tool call history as readable text."""
        if not tool_calls:
            return "No tools called yet."
        lines = []
        for i, record in enumerate(tool_calls, 1):
            status = "OK" if record.result.success else "FAIL"
            lines.append(f"{i}. {record.request.tool_name} ({status})")
        return "\n".join(lines)

    def _format_tools(self, tools: list[ToolSpec]) -> str:
        """Format available tools as readable text."""
        if not tools:
            return "No tools available."
        lines = []
        for tool in tools:
            lines.append(f"- {tool.name}: {tool.description}")
        return "\n".join(lines)
