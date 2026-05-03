"""
Test script for Module 3: Planner

Usage:
    cd agent-basic
    D:\anaconda3\envs\agent-basic\python.exe tests\test_planner.py --api-key sk-xxxxx

Optional arguments:
    --api-key    Your API key (required for real API tests)
    --base-url   API base URL (default: https://api-2.xi-ai.cn/v1)
    --model      Model name (default: gpt-4o)
"""

import sys
import os
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from planner import BasePlanner, OpenAICompatiblePlanner
from core import create_initial_state, FrontendOutput, AgentStatus
from core.errors import PlannerError

DEFAULT_BASE_URL = "https://api-2.xi-ai.cn/v1"
DEFAULT_MODEL = "gpt-4o"


def test_abstract_base():
    print("\n" + "=" * 50)
    print("TEST 1: BasePlanner is abstract")
    print("=" * 50)
    try:
        BasePlanner()
        print("  XX Should have failed!")
    except TypeError as e:
        print(f"  Correctly blocked: {e}")
        print("  OK")


def test_prompt_loading():
    print("\n" + "=" * 50)
    print("TEST 2: Prompt loading")
    print("=" * 50)
    class TestPlanner(OpenAICompatiblePlanner):
        def __init__(self):
            self._model = "test"
    planner = TestPlanner()
    
    prompts = ["plan_system", "plan_user", "decide_system", "decide_user", "decide_rules"]
    for p in prompts:
        text = planner._load_prompt(p)
        print(f"  {p}.md: {len(text)} chars")
    print("  OK")


def test_question_oriented_prompt(planner: OpenAICompatiblePlanner):
    print("\n" + "=" * 50)
    print("TEST 3: generate_question_oriented_prompt")
    print("=" * 50)
    
    question = "What language is spoken in this audio?"
    print(f"  Input question: {question}")
    print("  Calling API...")
    
    try:
        prompt = planner.generate_question_oriented_prompt(question)
        print(f"\n  === GENERATED PROMPT ===")
        print(f"  {prompt[:300]}{'...' if len(prompt) > 300 else ''}")
        print(f"\n  OK (length: {len(prompt)})")
    except Exception as e:
        print(f"  XX Error: {e}")


def test_plan(planner: OpenAICompatiblePlanner):
    print("\n" + "=" * 50)
    print("TEST 4: plan()")
    print("=" * 50)
    
    question = "What is being said in this audio?"
    caption = FrontendOutput(question_guided_caption="A male speaker says 'kitchen utensils' in Chinese.")
    
    print(f"  Question: {question}")
    print(f"  Caption: {caption.question_guided_caption}")
    print("  Calling API...")
    
    try:
        plan = planner.plan(question, caption, available_tools=[])
        print(f"\n  === PLAN ===")
        print(f"  Approach: {plan.approach}")
        print(f"  Focus: {plan.focus_points}")
        print(f"  Tool types: {plan.possible_tool_types}")
        print(f"  Intent: {plan.clarified_intent}")
        print(f"\n  OK")
    except Exception as e:
        print(f"  XX Error: {e}")


def test_decide(planner: OpenAICompatiblePlanner):
    print("\n" + "=" * 50)
    print("TEST 5: decide()")
    print("=" * 50)
    
    # Create a mock state
    state = create_initial_state(
        question="What language is spoken?",
        audio_path="D:\\test.wav",
        max_steps=5,
    )
    state["initial_frontend_output"] = FrontendOutput(
        question_guided_caption="A speaker says words in a foreign language."
    )
    state["initial_plan"] = planner.plan(
        "What language is spoken?",
        state["initial_frontend_output"],
        available_tools=[],
    )
    
    # Mock available tools
    from core.schemas import ToolSpec
    tools = [
        ToolSpec(name="asr_transcribe", description="Transcribe audio to text"),
        ToolSpec(name="language_id", description="Identify spoken language"),
    ]
    
    print(f"  Question: {state['question']}")
    print(f"  Step: {state['step_count']} / {state['max_steps']}")
    print(f"  Tools: {[t.name for t in tools]}")
    print("  Calling API...")
    
    try:
        decision = planner.decide(state, tools)
        print(f"\n  === DECISION ===")
        print(f"  Action: {decision.action.value}")
        print(f"  Rationale: {decision.rationale[:150]}{'...' if len(decision.rationale) > 150 else ''}")
        if decision.selected_tool_name:
            print(f"  Selected tool: {decision.selected_tool_name}")
        if decision.draft_answer:
            print(f"  Draft answer: {decision.draft_answer[:100]}")
        print(f"\n  OK")
    except Exception as e:
        print(f"  XX Error: {e}")


def test_summarize_evidence(planner: OpenAICompatiblePlanner):
    print("\n" + "=" * 50)
    print("TEST 6: summarize_evidence()")
    print("=" * 50)
    
    from core.schemas import EvidenceItem
    state = create_initial_state(
        question="What is being said?",
        audio_path="D:\\test.wav",
    )
    state["evidence_log"] = [
        EvidenceItem(source="frontend", content="Male speaker, Chinese language", confidence=0.8),
        EvidenceItem(source="asr_tool", content="Transcription: kitchen utensils", confidence=0.9),
    ]
    
    print("  Evidence:")
    for e in state["evidence_log"]:
        print(f"    - [{e.source}] {e.content}")
    print("  Calling API...")
    
    try:
        summary = planner.summarize_evidence(state)
        print(f"\n  === SUMMARY ===")
        print(f"  {summary[:300]}{'...' if len(summary) > 300 else ''}")
        print(f"\n  OK (length: {len(summary)})")
    except Exception as e:
        print(f"  XX Error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Planner module tests")
    parser.add_argument("--api-key", type=str, default=None, help="API key for real tests")
    parser.add_argument("--base-url", type=str, default=DEFAULT_BASE_URL, help="API base URL")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help="Model name")
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("MODULE 3 TESTS: Planner (Decision Making)")
    print("=" * 60)
    
    test_abstract_base()
    test_prompt_loading()
    
    if args.api_key:
        print("\n" + "-" * 50)
        print("Creating planner with provided API key...")
        print("-" * 50)
        
        planner = OpenAICompatiblePlanner(
            model=args.model,
            api_key=args.api_key,
            base_url=args.base_url,
        )
        print(f"  Planner: {planner.name}")
        print(f"  Base URL: {args.base_url}")
        
        test_question_oriented_prompt(planner)
        test_plan(planner)
        test_decide(planner)
        test_summarize_evidence(planner)
    else:
        print("\n" + "=" * 50)
        print("TEST 3-6: REAL API CALLS")
        print("=" * 50)
        print("  SKIP No --api-key provided.")
        print("  Run with: python tests/test_planner.py --api-key sk-xxxxx")
    
    print("\n" + "=" * 50)
    print("ALL TESTS COMPLETED")
    print("=" * 50)


if __name__ == "__main__":
    main()
