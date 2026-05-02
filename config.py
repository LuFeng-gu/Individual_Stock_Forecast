"""
Configuration management for the agent.

Loads settings from:
1. Environment variables (via python-dotenv)
2. Command-line arguments (via argparse)
3. Default fallbacks

Priority: CLI args > .env > defaults

Frontend and planner each have their own API key, base URL, and model.
No shared fallback -- specify both explicitly even if they are the same.
"""

import os
import argparse
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def _load_dotenv() -> None:
    """Load .env file if it exists in the project root."""
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)


@dataclass
class AgentConfig:
    """
    Complete configuration for running the agent.

    Frontend and planner each have separate API credentials.
    Even if using the same provider, specify both explicitly.
    """

    # Frontend API settings (audio-capable model)
    frontend_api_key: str = ""
    frontend_base_url: str = ""
    frontend_model: str = "gpt-4o-audio-preview"

    # Planner API settings (text reasoning model)
    planner_api_key: str = ""
    planner_base_url: str = ""
    planner_model: str = "gpt-4o"

    # Agent behavior
    max_steps: int = 10

    # Paths
    audio_path: str = ""
    question: str = ""

    # Optional
    verbose: bool = False
    trace: bool = False
    trace_dir: str = "."
    extra: dict = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        """Check if config has minimum required fields to run."""
        return bool(
            self.frontend_api_key
            and self.frontend_base_url
            and self.planner_api_key
            and self.planner_base_url
            and self.audio_path
            and self.question
        )


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Audio Agent: Ask questions about audio files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Both frontend and planner use the same provider (specify both explicitly)
  python main.py --audio test.wav --question "What is happening?" \
      --frontend-api-key sk-key-1 --frontend-base-url https://api.xxx/v1 \
      --planner-api-key sk-key-1 --planner-base-url https://api.xxx/v1

  # Frontend and planner use different providers
  python main.py --audio test.wav --question "What is happening?" \
      --frontend-api-key sk-dashscope-key --frontend-base-url https://dashscope... \
      --planner-api-key sk-openai-key --planner-base-url https://api.openai.com/v1
        """,
    )

    # Audio + Question (always required)
    parser.add_argument("--audio", required=True, help="Path to the audio file")
    parser.add_argument("--question", required=True, help="Question about the audio")

    # Frontend-specific API settings
    parser.add_argument("--frontend-api-key", default="", help="Frontend (audio model) API key")
    parser.add_argument("--frontend-base-url", default="", help="Frontend API base URL")
    parser.add_argument("--frontend-model", default="", help="Frontend model name (e.g., gpt-4o-audio-preview, qwen3-omni-flash)")

    # Planner-specific API settings
    parser.add_argument("--planner-api-key", default="", help="Planner (text model) API key")
    parser.add_argument("--planner-base-url", default="", help="Planner API base URL")
    parser.add_argument("--planner-model", default="", help="Planner model name (e.g., gpt-4o)")

    # Other settings
    parser.add_argument("--max-steps", type=int, default=0, help="Max agent steps")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--trace", action="store_true", help="Enable execution tracing")
    parser.add_argument("--trace-dir", default=".", help="Directory for trace output files")

    return parser


def load_config(argv: list[str] | None = None) -> AgentConfig:
    """
    Load configuration from .env + CLI args.

    Priority: CLI args > env vars > defaults

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:])

    Returns:
        AgentConfig with merged settings
    """
    _load_dotenv()

    parser = build_parser()
    args = parser.parse_args(argv)

    # Priority: CLI args > env vars > defaults
    def pick(cli_value: str, env_name: str, default: str) -> str:
        if cli_value:
            return cli_value
        env_value = os.environ.get(env_name, "")
        if env_value:
            return env_value
        return default

    def pick_int(cli_value: int, env_name: str, default: int) -> int:
        if cli_value > 0:
            return cli_value
        env_value = os.environ.get(env_name, "")
        if env_value:
            return int(env_value)
        return default

    config = AgentConfig(
        # Frontend specific
        frontend_api_key=pick(args.frontend_api_key, "FRONTEND_API_KEY", ""),
        frontend_base_url=pick(args.frontend_base_url, "FRONTEND_BASE_URL", ""),
        frontend_model=pick(args.frontend_model, "FRONTEND_MODEL", "gpt-4o-audio-preview"),

        # Planner specific
        planner_api_key=pick(args.planner_api_key, "PLANNER_API_KEY", ""),
        planner_base_url=pick(args.planner_base_url, "PLANNER_BASE_URL", ""),
        planner_model=pick(args.planner_model, "PLANNER_MODEL", "gpt-4o"),

        # Other
        max_steps=pick_int(args.max_steps, "MAX_STEPS", 10),
        audio_path=args.audio,
        question=args.question,
        verbose=args.verbose,
        trace=args.trace,
        trace_dir=args.trace_dir,
    )

    return config
