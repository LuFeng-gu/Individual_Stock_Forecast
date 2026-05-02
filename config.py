"""
Configuration management for the agent.

Loads settings from:
1. Environment variables (via python-dotenv)
2. Command-line arguments (via argparse)
3. Default fallbacks

Priority: CLI args > .env > defaults
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

    All fields have sensible defaults for local testing.
    Production usage should override via .env or CLI args.
    """

    # API settings
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    frontend_model: str = "gpt-4o-audio-preview"
    planner_model: str = "gpt-4o"

    # Agent behavior
    max_steps: int = 10
    temperature: float = 0.3

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
        return bool(self.api_key and self.audio_path and self.question)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Audio Agent: Ask questions about audio files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --audio test.wav --question "What is happening?" --api-key sk-xxx
  python main.py --audio test.wav --question "What is happening?" --model gpt-4o
        """,
    )

    parser.add_argument("--audio", required=True, help="Path to the audio file")
    parser.add_argument("--question", required=True, help="Question about the audio")
    parser.add_argument("--api-key", default="", help="API key (or set in .env)")
    parser.add_argument("--base-url", default="", help="API base URL")
    parser.add_argument("--frontend-model", default="", help="Frontend model name")
    parser.add_argument("--planner-model", default="", help="Planner model name")
    parser.add_argument("--max-steps", type=int, default=0, help="Max agent steps")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--trace", action="store_true", help="Enable execution tracing")
    parser.add_argument("--trace-dir", default=".", help="Directory for trace output files")

    return parser


def load_config(argv: list[str] | None = None) -> AgentConfig:
    """
    Load configuration from .env + CLI args.

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

    def pick_float(cli_value: float, env_name: str, default: float) -> float:
        if cli_value != 0.0:
            return cli_value
        env_value = os.environ.get(env_name, "")
        if env_value:
            return float(env_value)
        return default

    config = AgentConfig(
        api_key=pick(args.api_key, "API_KEY", ""),
        base_url=pick(args.base_url, "BASE_URL", "https://api-2.xi-ai.cn/v1"),
        frontend_model=pick(args.frontend_model, "FRONTEND_MODEL", "gpt-4o-audio-preview"),
        planner_model=pick(args.planner_model, "PLANNER_MODEL", "gpt-4o"),
        max_steps=pick_int(args.max_steps, "MAX_STEPS", 10),
        temperature=pick_float(args.temperature, "TEMPERATURE", 0.3),
        audio_path=args.audio,
        question=args.question,
        verbose=args.verbose,
        trace=args.trace,
        trace_dir=args.trace_dir,
    )

    return config
