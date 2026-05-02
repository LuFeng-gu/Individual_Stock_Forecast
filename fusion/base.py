"""
Abstract base class for fusion modules.

The fusion module is the "evidence clerk" of the agent. It:
1. Converts frontend captions into EvidenceItem objects
2. Converts tool results into EvidenceItem objects
3. Validates the quality and format of evidence
4. (Optionally) deduplicates or merges related evidence

Think of it as a secretary that organizes all findings into a uniform filing system.
"""

from abc import ABC, abstractmethod

from core.schemas import FrontendOutput, ToolResult, EvidenceItem
from core.errors import FusionError


class BaseFusion(ABC):
    """
    Abstract base class for evidence fusion.

    Fusion bridges the gap between raw outputs (frontend captions, tool results)
    and the uniform EvidenceItem format used by the planner.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this fusion module for logging."""
        raise NotImplementedError

    @abstractmethod
    def frontend_to_evidence(self, frontend_output: FrontendOutput) -> EvidenceItem:
        """
        Convert a frontend caption into an EvidenceItem.

        This is called by the frontend_evidence_node (or initial setup)
        to turn the audio model's caption into structured evidence.

        Args:
            frontend_output: The caption produced by the frontend

        Returns:
            An EvidenceItem with source="frontend"

        Raises:
            FusionError: If conversion fails
        """
        raise NotImplementedError

    @abstractmethod
    def tool_result_to_evidence(self, tool_result: ToolResult) -> EvidenceItem:
        """
        Convert a tool execution result into an EvidenceItem.

        This is called by the evidence_fusion_node after a tool runs,
        to add the tool's output to the evidence log.

        Args:
            tool_result: The result returned by the tool executor

        Returns:
            An EvidenceItem with source=tool_result.tool_name

        Raises:
            FusionError: If conversion fails
        """
        raise NotImplementedError

    @abstractmethod
    def format_check(self, evidence: EvidenceItem) -> tuple[bool, str]:
        """
        Validate the format and content quality of an evidence item.

        This is called by the format_check_node to verify that evidence
        is usable before passing it to the planner.

        Args:
            evidence: The evidence item to check

        Returns:
            (is_valid, error_message): True if valid, False with reason if invalid
        """
        raise NotImplementedError

    def validate_evidence(self, evidence: EvidenceItem) -> EvidenceItem:
        """
        Validate evidence and raise FusionError if invalid.

        This is a convenience wrapper around format_check() that raises
        instead of returning a tuple.

        Args:
            evidence: The evidence item to validate

        Returns:
            The same evidence item (passthrough)

        Raises:
            FusionError: If format_check returns False
        """
        is_valid, msg = self.format_check(evidence)
        if not is_valid:
            raise FusionError(
                f"Evidence validation failed: {msg}",
                details={
                    "source": evidence.source,
                    "content_preview": evidence.content[:200] if evidence.content else "",
                    "error": msg,
                },
            )
        return evidence
