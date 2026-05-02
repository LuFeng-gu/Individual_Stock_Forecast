"""
OpenAI-compatible API frontend implementation.

This frontend sends audio to any OpenAI-compatible API endpoint
(e.g., OpenAI, DashScope, xi-ai.cn, etc.) and returns a caption.

Supports both:
- Standard text models (reads response.choices[0].message.content)
- Audio-native models like gpt-4o-audio-preview (reads message.audio.transcript)

Audio is sent as a base64-encoded input_audio block.
"""

import base64
import os
from pathlib import Path

from frontend.base import BaseFrontend
from core.schemas import FrontendOutput
from core.errors import FrontendError
from core.logging import log_node_start, log_node_end, log_error


class OpenAICompatibleFrontend(BaseFrontend):
    """
    Frontend that uses any OpenAI-compatible API for audio understanding.
    
    Supports providers like:
    - OpenAI (gpt-4o-audio-preview)
    - xi-ai.cn (gpt-4o-audio-preview, gpt-audio)
    - DashScope / Alibaba Cloud (qwen3-omni-flash, qwen3.5-omni-plus)
    - Any other OpenAI-compatible endpoint
    
    For gpt-4o-audio-preview, pass modalities and audio explicitly:
        modalities=["text", "audio"]
        audio={"voice": "alloy", "format": "wav"}
    
    For DashScope qwen3-omni models, leave modalities/audio as None
    (the API only needs the input_audio message block).
    
    Args:
        model: Model name (default: "gpt-4o-audio-preview")
        api_key: API key. If None, reads from environment variable.
        base_url: API base URL
        modalities: OpenAI modalities param. Pass None to omit (e.g., for DashScope).
        audio: OpenAI audio config. Pass None to omit (e.g., for DashScope).
        max_retries: Number of retries on API failure
    """

    def __init__(
        self,
        model: str = "gpt-4o-audio-preview",
        api_key: str | None = None,
        base_url: str = "https://api-2.xi-ai.cn/v1",
        modalities: list[str] | None = None,
        audio: dict[str, str] | None = None,
        max_retries: int = 3,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        self._base_url = base_url
        self._modalities = modalities
        self._audio = audio
        self._max_retries = max_retries

        if not self._api_key:
            raise FrontendError(
                "No API key provided. Set OPENAI_API_KEY or DASHSCOPE_API_KEY env var, "
                "or pass api_key explicitly.",
            )

        try:
            from openai import OpenAI
        except ImportError:
            raise FrontendError(
                "openai package not installed. Run: pip install openai"
            )
        
        self._client = OpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=60.0,
        )

    @property
    def name(self) -> str:
        return f"openai_compatible_{self._model}"

    def run(
        self,
        question: str,
        audio_path: str,
        question_oriented_prompt: str | None = None,
    ) -> FrontendOutput:
        """
        Send audio to API and get caption.
        """
        log_node_start("frontend.run", {"model": self._model, "audio": audio_path})

        # Step 1: Validate
        self.validate_inputs(question, audio_path)
        if not os.path.exists(audio_path):
            raise FrontendError(
                f"Audio file not found: {audio_path}",
                details={"audio_path": audio_path},
            )

        # Step 2: Read and encode audio
        try:
            audio_data_url, audio_format = self._encode_audio(audio_path)
        except Exception as e:
            raise FrontendError(
                f"Failed to read/encode audio: {e}",
                details={"audio_path": audio_path},
            ) from e

        # Step 3: Load prompts from external markdown files
        system_prompt = self._load_prompt("frontend_system")
        user_prompt_template = self._load_prompt("frontend_user")
        
        effective_question = question_oriented_prompt or question
        user_prompt = user_prompt_template.format(
            question=effective_question,
            audio_path=audio_path,
        )
        
        # Step 4: Call API
        try:
            caption = self._call_api(system_prompt, user_prompt, audio_data_url, audio_format)
        except Exception as e:
            log_error("frontend.run", e)
            raise FrontendError(
                f"API call failed: {e}",
                details={"model": self._model, "base_url": self._base_url},
            ) from e

        # Step 5: Build output
        output = FrontendOutput(question_guided_caption=caption)
        
        log_node_end("frontend.run", {"caption_length": len(caption)})
        return output

    def generate_final_answer(
        self,
        question: str,
        audio_path: str,
        context: dict,
    ) -> str:
        """
        Generate final answer with all accumulated context.
        """
        log_node_start("frontend.generate_final_answer")

        self.validate_inputs(question, audio_path)
        
        if not os.path.exists(audio_path):
            raise FrontendError(f"Audio file not found: {audio_path}")

        audio_data_url, audio_format = self._encode_audio(audio_path)

        evidence_summary = context.get("evidence_summary", "")
        initial_plan = context.get("initial_plan", {})
        
        system_prompt = (
            "You are an expert audio analyst. Based on the audio and the provided context, "
            "give a precise, well-reasoned answer to the user's question."
        )
        
        user_parts = [
            f"Question: {question}",
            f"Initial Plan: {initial_plan.get('approach', 'N/A') if isinstance(initial_plan, dict) else getattr(initial_plan, 'approach', 'N/A')}",
            f"Evidence Summary: {evidence_summary}",
            "\nPlease listen to the audio and provide your final answer.",
        ]
        user_prompt = "\n".join(user_parts)

        answer = self._call_api(system_prompt, user_prompt, audio_data_url, audio_format)
        
        log_node_end("frontend.generate_final_answer", {"answer_length": len(answer)})
        return answer

    def _encode_audio(self, audio_path: str) -> tuple[str, str]:
        """
        Read audio file and return base64 data URL + format.
        
        Returns:
            Tuple of (data_url, audio_format)
            data_url format: data:;base64,{encoded_data}
        """
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
        return f"data:;base64,{audio_base64}", self._get_audio_format(audio_path)

    def _load_prompt(self, prompt_name: str) -> str:
        """Load a prompt from the prompts/ directory."""
        module_dir = Path(__file__).parent.parent
        prompt_path = module_dir / "prompts" / f"{prompt_name}.md"
        
        if not prompt_path.exists():
            raise FrontendError(
                f"Prompt file not found: {prompt_path}",
                details={"prompt_name": prompt_name},
            )
        
        return prompt_path.read_text(encoding="utf-8")

    def _call_api(
        self,
        system_prompt: str,
        user_prompt: str,
        audio_data_url: str,
        audio_format: str,
    ) -> str:
        """
        Make the actual API call.
        
        For DashScope qwen3-omni models:
        - audio_data_url must be "data:;base64,{xxx}" format
        - modalities and audio params should NOT be passed
        - Result is read from msg.content
        
        For gpt-4o-audio-preview:
        - Pass modalities=["text", "audio"] and audio={"voice":...} explicitly
        - Result may be in msg.audio.transcript
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": audio_data_url,
                            "format": audio_format,
                        },
                    },
                ],
            },
        ]

        from openai import APIError, APIConnectionError, RateLimitError
        
        last_error = None
        for attempt in range(self._max_retries):
            try:
                # Build kwargs conditionally
                kwargs = {
                    "model": self._model,
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 2048,
                }
                if self._modalities is not None:
                    kwargs["modalities"] = self._modalities
                if self._audio is not None:
                    kwargs["audio"] = self._audio
                
                response = self._client.chat.completions.create(**kwargs)
                
                msg = response.choices[0].message
                
                # For gpt-4o-audio-preview, try audio transcript first
                if self._modalities is not None and hasattr(msg, "audio") and msg.audio and hasattr(msg.audio, "transcript"):
                    return msg.audio.transcript or ""
                
                # Default: read text content (works for DashScope and standard models)
                return msg.content or ""
                
            except (APIError, APIConnectionError, RateLimitError) as e:
                last_error = e
                import time
                time.sleep(0.5 * (2 ** attempt))
                continue
        
        raise FrontendError(
            f"API call failed after {self._max_retries} retries: {last_error}",
            details={"model": self._model},
        )

    def _get_audio_format(self, audio_path: str) -> str:
        """Determine audio format from file extension."""
        ext = Path(audio_path).suffix.lower()
        format_map = {
            ".wav": "wav",
            ".mp3": "mp3",
            ".m4a": "m4a",
            ".ogg": "ogg",
            ".webm": "webm",
        }
        return format_map.get(ext, "wav")
