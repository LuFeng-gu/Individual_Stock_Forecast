"""
Frontend module: audio understanding components.

This package contains the base interface and concrete implementations
for processing audio and generating captions/answers.
"""

from frontend.base import BaseFrontend
from frontend.openai_compatible_frontend import OpenAICompatibleFrontend

__all__ = [
    "BaseFrontend",
    "OpenAICompatibleFrontend",
]
