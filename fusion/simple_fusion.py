"""
Simple fusion implementation.

Converts frontend and tool outputs into EvidenceItem objects with straightforward
serialization. No deduplication or advanced merging -- just clean conversion.
"""

import json

from core.schemas import FrontendOutput, ToolResult, EvidenceItem
from core.errors import FusionError
from fusion.base import BaseFusion


class SimpleFusion(BaseFusion):
    """
    Simple evidence fusion with JSON serialization and basic validation.

    - Frontend captions are stored as-is with source="frontend"
    - Tool results are JSON-serialized with source=tool_name
    - Format checks: non-empty content, valid confidence range
    """

    @property
    def name(self) -> str:
        return "simple_fusion"

    def frontend_to_evidence(self, frontend_output: FrontendOutput) -> EvidenceItem:
        """
        Convert a frontend caption into an EvidenceItem.

        The caption is stored as plain text. Confidence is set to a default
        of 0.8 since frontend captions are generally high-quality evidence.
        """
        caption = frontend_output.question_guided_caption
        if not caption or not caption.strip():
            raise FusionError(
                "Frontend caption is empty",
                details={"frontend_output": str(frontend_output)},
            )

        return EvidenceItem(
            source="frontend",
            content=caption.strip(),
            evidence_type="caption",
            confidence=0.8,
            metadata={
                "model": getattr(frontend_output, "model", None),
                "timestamp": frontend_output.timestamp.isoformat(),
            },
        )

    def tool_result_to_evidence(self, tool_result: ToolResult) -> EvidenceItem:
        """
        Convert a tool result into an EvidenceItem.

        On success: the output dict is JSON-serialized into the content field.
        On failure: the error_message is stored as content with evidence_type="error".
        """
        if not tool_result.tool_name:
            raise FusionError(
                "Tool result has no tool_name",
                details={"tool_result": str(tool_result)},
            )

        if tool_result.success:
            content = json.dumps(tool_result.output, ensure_ascii=False, default=str)
            evidence_type = "structured"
            confidence = 0.9
        else:
            content = tool_result.error_message or "Unknown tool error"
            evidence_type = "error"
            confidence = 0.0

        return EvidenceItem(
            source=tool_result.tool_name,
            content=content,
            evidence_type=evidence_type,
            confidence=confidence,
            metadata={
                "success": tool_result.success,
                "execution_time_ms": tool_result.execution_time_ms,
                "timestamp": tool_result.timestamp.isoformat(),
            },
        )

    def format_check(self, evidence: EvidenceItem) -> tuple[bool, str]:
        """
        Check if an evidence item meets basic quality standards.

        Validation rules:
        1. content must be non-empty after stripping
        2. confidence must be in [0.0, 1.0]
        3. source must be non-empty
        """
        if not evidence.source or not evidence.source.strip():
            return False, "Missing or empty source"

        if evidence.content is None or not str(evidence.content).strip():
            return False, "Missing or empty content"

        if not (0.0 <= evidence.confidence <= 1.0):
            return False, f"Confidence {evidence.confidence} out of range [0.0, 1.0]"

        return True, ""
