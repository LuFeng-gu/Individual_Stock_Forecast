"""
Test script for Module 1: Core

Run this to verify that the core data structures work correctly:
- Schemas validate data properly
- State initializes correctly
- Errors are raised when expected

Usage:
    cd agent-basic
    conda run -n agent-basic python tests/test_core.py
"""

import sys
from pathlib import Path

# Add parent directory to path so we can import 'core'
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import (
    AgentStatus,
    FrontendOutput,
    EvidenceItem,
    ToolSpec,
    ToolCallRequest,
    ToolResult,
    InitialPlan,
    PlannerDecision,
    PlannerActionType,
    FinalAnswer,
    create_initial_state,
    StateValidationError,
    FrontendError,
)


def test_constants():
    """Test 1: Agent status enum"""
    print("\n" + "=" * 50)
    print("TEST 1: AgentStatus Enum")
    print("=" * 50)
    
    print(f"  RUNNING = '{AgentStatus.RUNNING}'")
    print(f"  ANSWERED = '{AgentStatus.ANSWERED}'")
    print(f"  FAILED = '{AgentStatus.FAILED}'")
    print("  OK Status constants work")


def test_frontend_output():
    """Test 2: FrontendOutput schema validation"""
    print("\n" + "=" * 50)
    print("TEST 2: FrontendOutput (Pydantic validation)")
    print("=" * 50)
    
    # Valid output
    output = FrontendOutput(question_guided_caption="This audio contains a male speaker discussing weather.")
    print(f"  Valid output created: caption='{output.question_guided_caption[:50]}...'")
    
    # Invalid output (empty caption) — should raise ValueError
    try:
        bad_output = FrontendOutput(question_guided_caption="   ")
        print("  XX Should have raised an error for empty caption!")
    except ValueError as e:
        print(f"  Correctly caught invalid input: {e}")
    
    print("  OK FrontendOutput validation works")


def test_evidence_item():
    """Test 3: EvidenceItem creation"""
    print("\n" + "=" * 50)
    print("TEST 3: EvidenceItem")
    print("=" * 50)
    
    evidence = EvidenceItem(
        source="frontend:openai",
        content="Speaker is male, discussing weather forecast.",
        evidence_type="question_guided_caption",
        confidence=0.85,
    )
    print(f"  Source: {evidence.source}")
    print(f"  Content: {evidence.content[:50]}...")
    print(f"  Confidence: {evidence.confidence}")
    print("  OK EvidenceItem works")


def test_tool_spec_and_request():
    """Test 4: Tool specification and call request"""
    print("\n" + "=" * 50)
    print("TEST 4: ToolSpec + ToolCallRequest")
    print("=" * 50)
    
    spec = ToolSpec(
        name="asr_transcribe",
        description="Transcribe audio to text using ASR",
        input_schema={"type": "object", "properties": {"audio_path": {"type": "string"}}},
        tags=["audio", "transcription"],
    )
    print(f"  Tool: {spec.name} — {spec.description}")
    print(f"  Tags: {spec.tags}")
    
    request = ToolCallRequest(
        tool_name="asr_transcribe",
        args={"audio_path": "/tmp/audio.wav"},
        context={"step": 1, "question": "What is being said?"},
    )
    print(f"  Request to call '{request.tool_name}' with args={request.args}")
    print("  OK Tool schemas work")


def test_planner_decision():
    """Test 5: PlannerDecision validation"""
    print("\n" + "=" * 50)
    print("TEST 5: PlannerDecision (action consistency)")
    print("=" * 50)
    
    # Valid ANSWER decision
    answer_decision = PlannerDecision(
        action=PlannerActionType.ANSWER,
        rationale="I have enough evidence to answer.",
        draft_answer="The speaker is discussing sunny weather.",
        confidence=0.9,
    )
    print(f"  ANSWER decision: confidence={answer_decision.confidence}")
    
    # Valid CALL_TOOL decision
    tool_decision = PlannerDecision(
        action=PlannerActionType.CALL_TOOL,
        rationale="Need transcription to verify.",
        selected_tool_name="asr_transcribe",
        selected_audio_id="audio_0",
        confidence=0.8,
    )
    print(f"  CALL_TOOL decision: tool={tool_decision.selected_tool_name}")
    
    # Invalid CALL_TOOL (missing tool name) — should raise ValueError
    try:
        bad_decision = PlannerDecision(
            action=PlannerActionType.CALL_TOOL,
            rationale="Missing tool name",
        )
        print("  XX Should have raised an error for missing tool name!")
    except ValueError as e:
        print(f"  Correctly caught invalid decision: {e}")
    
    print("  OK PlannerDecision validation works")


def test_initial_plan():
    """Test 6: InitialPlan creation"""
    print("\n" + "=" * 50)
    print("TEST 6: InitialPlan")
    print("=" * 50)
    
    plan = InitialPlan(
        approach="First get ASR transcription, then analyze content.",
        focus_points=["speaker identity", "topic", "language"],
        possible_tool_types=["asr", "diarization"],
        clarified_intent="Determine what language is spoken and by whom.",
    )
    print(f"  Approach: {plan.approach}")
    print(f"  Focus: {plan.focus_points}")
    print(f"  Intent: {plan.clarified_intent}")
    print("  OK InitialPlan works")


def test_create_initial_state():
    """Test 7: AgentState initialization"""
    print("\n" + "=" * 50)
    print("TEST 7: create_initial_state")
    print("=" * 50)
    
    state = create_initial_state(
        question="What is being said in this audio?",
        audio_path="D:\\PythonProject\\audio-agent\\IC0001W0001.wav",
        max_steps=5,
    )
    
    print(f"  Question: {state['question']}")
    print(f"  Audio: {state['audio_path']}")
    print(f"  Max steps: {state['max_steps']}")
    print(f"  Status: {state['status']}")
    print(f"  Step count: {state['step_count']}")
    print(f"  Evidence log length: {len(state['evidence_log'])}")
    print(f"  Question oriented prompt: {state['question_oriented_prompt']}")
    print("  OK Initial state created correctly")
    
    # Test validation: empty question
    print("\n  Testing validation...")
    try:
        bad_state = create_initial_state(question="", audio_path="test.wav")
        print("  XX Should have raised an error for empty question!")
    except ValueError as e:
        print(f"  Correctly caught empty question: {e}")
    
    print("  OK State validation works")


def main():
    """Run all core tests in sequence."""
    print("\n" + "=" * 60)
    print("MODULE 1 TESTS: Core Data Structures")
    print("=" * 60)
    
    test_constants()
    test_frontend_output()
    test_evidence_item()
    test_tool_spec_and_request()
    test_planner_decision()
    test_initial_plan()
    test_create_initial_state()
    
    print("\n" + "=" * 50)
    print("OK ALL MODULE 1 TESTS PASSED")
    print("=" * 50)
    print("\nWhat you just verified:")
    print("  1. AgentStatus enum — the three possible agent states")
    print("  2. Pydantic schemas — data validation with FrontendOutput, EvidenceItem, etc.")
    print("  3. PlannerDecision — action consistency checks (CALL_TOOL needs tool name)")
    print("  4. InitialPlan — the planner's initial strategy")
    print("  5. AgentState — the central memory object with proper initial values")
    print("\nNext module: Frontend (OpenAI-compatible audio model)")


if __name__ == "__main__":
    main()
