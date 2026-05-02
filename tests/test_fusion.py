"""
Tests for the fusion module.

No API calls required -- all tests are local unit tests.
"""

import sys
from pathlib import Path

# Add parent directory to path so we can import 'core', 'fusion'
sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
from datetime import datetime

from core.schemas import FrontendOutput, ToolResult, EvidenceItem
from core.errors import FusionError
from fusion import SimpleFusion


class TestSimpleFusion(unittest.TestCase):
    """Test SimpleFusion evidence conversion and validation."""

    def setUp(self):
        self.fusion = SimpleFusion()

    # ------------------------------------------------------------------
    # frontend_to_evidence
    # ------------------------------------------------------------------
    def test_frontend_to_evidence_success(self):
        """Normal conversion of a frontend caption."""
        fe_out = FrontendOutput(
            question_guided_caption="  A dog barking in the park.  ",
            timestamp=datetime(2025, 1, 1, 12, 0, 0),
        )
        ev = self.fusion.frontend_to_evidence(fe_out)

        self.assertEqual(ev.source, "frontend")
        self.assertEqual(ev.content, "A dog barking in the park.")
        self.assertEqual(ev.evidence_type, "caption")
        self.assertEqual(ev.confidence, 0.8)
        self.assertIn("timestamp", ev.metadata)

    def test_frontend_to_evidence_empty_caption(self):
        """Empty caption should raise FusionError."""
        # Bypass Pydantic validation to test Fusion's own defense
        fe_out = FrontendOutput.model_construct(
            question_guided_caption="   ",
            timestamp=datetime.now(),
        )
        with self.assertRaises(FusionError) as ctx:
            self.fusion.frontend_to_evidence(fe_out)
        self.assertIn("empty", str(ctx.exception).lower())

    # ------------------------------------------------------------------
    # tool_result_to_evidence
    # ------------------------------------------------------------------
    def test_tool_result_to_evidence_success(self):
        """Successful tool result becomes structured evidence."""
        tr = ToolResult(
            tool_name="asr_transcribe",
            success=True,
            output={"text": "Hello world", "language": "en"},
            execution_time_ms=150.0,
        )
        ev = self.fusion.tool_result_to_evidence(tr)

        self.assertEqual(ev.source, "asr_transcribe")
        self.assertIn("Hello world", ev.content)
        self.assertEqual(ev.evidence_type, "structured")
        self.assertEqual(ev.confidence, 0.9)
        self.assertTrue(ev.metadata["success"])
        self.assertEqual(ev.metadata["execution_time_ms"], 150.0)

    def test_tool_result_to_evidence_failure(self):
        """Failed tool result becomes error evidence."""
        tr = ToolResult(
            tool_name="vad_detect",
            success=False,
            output={},
            error_message="Audio too short",
            execution_time_ms=50.0,
        )
        ev = self.fusion.tool_result_to_evidence(tr)

        self.assertEqual(ev.source, "vad_detect")
        self.assertEqual(ev.content, "Audio too short")
        self.assertEqual(ev.evidence_type, "error")
        self.assertEqual(ev.confidence, 0.0)
        self.assertFalse(ev.metadata["success"])

    def test_tool_result_to_evidence_no_tool_name(self):
        """Tool result without name should raise FusionError."""
        tr = ToolResult(tool_name="", success=True, output={})
        with self.assertRaises(FusionError) as ctx:
            self.fusion.tool_result_to_evidence(tr)
        self.assertIn("tool_name", str(ctx.exception).lower())

    # ------------------------------------------------------------------
    # format_check
    # ------------------------------------------------------------------
    def test_format_check_valid(self):
        """A well-formed evidence item passes."""
        ev = EvidenceItem(source="frontend", content="Valid content", confidence=0.5)
        ok, msg = self.fusion.format_check(ev)
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_format_check_empty_source(self):
        """Empty source fails."""
        ev = EvidenceItem(source="", content="content", confidence=0.5)
        ok, msg = self.fusion.format_check(ev)
        self.assertFalse(ok)
        self.assertIn("source", msg.lower())

    def test_format_check_empty_content(self):
        """Empty content fails."""
        ev = EvidenceItem(source="tool", content="   ", confidence=0.5)
        ok, msg = self.fusion.format_check(ev)
        self.assertFalse(ok)
        self.assertIn("content", msg.lower())

    def test_format_check_none_content(self):
        """None content fails."""
        # Bypass Pydantic validation to test Fusion's own check
        ev = EvidenceItem.model_construct(source="tool", content=None, confidence=0.5)
        ok, msg = self.fusion.format_check(ev)
        self.assertFalse(ok)
        self.assertIn("content", msg.lower())

    def test_format_check_confidence_negative(self):
        """Negative confidence fails."""
        ev = EvidenceItem.model_construct(source="tool", content="content", confidence=-0.1)
        ok, msg = self.fusion.format_check(ev)
        self.assertFalse(ok)
        self.assertIn("confidence", msg.lower())

    def test_format_check_confidence_over_one(self):
        """Confidence > 1.0 fails."""
        ev = EvidenceItem.model_construct(source="tool", content="content", confidence=1.5)
        ok, msg = self.fusion.format_check(ev)
        self.assertFalse(ok)
        self.assertIn("confidence", msg.lower())

    # ------------------------------------------------------------------
    # validate_evidence (convenience wrapper)
    # ------------------------------------------------------------------
    def test_validate_evidence_passes(self):
        """Valid evidence returns unchanged."""
        ev = EvidenceItem(source="frontend", content="OK", confidence=0.5)
        result = self.fusion.validate_evidence(ev)
        self.assertIs(result, ev)

    def test_validate_evidence_raises(self):
        """Invalid evidence raises FusionError."""
        ev = EvidenceItem(source="", content="OK", confidence=0.5)
        with self.assertRaises(FusionError) as ctx:
            self.fusion.validate_evidence(ev)
        self.assertIn("source", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
