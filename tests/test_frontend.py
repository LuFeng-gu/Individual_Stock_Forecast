"""
Test script for Module 2: Frontend

Usage:
    cd agent-basic
    D:\anaconda3\envs\agent-basic\python.exe tests\test_frontend.py --api-key sk-xxxxx

Optional arguments:
    --api-key    Your API key (required for real API test)
    --base-url   API base URL (default: https://api-2.xi-ai.cn/v1)
    --model      Model name (default: gpt-4o-audio-preview)
    --audio      Path to audio file (default: your IC0001W0001.wav)
"""

import sys
import os
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from frontend import BaseFrontend, OpenAICompatibleFrontend
from core.errors import FrontendError

DEFAULT_AUDIO_PATH = r"D:\PythonProject\audio-agent\IC0001W0001.wav"
DEFAULT_BASE_URL = "https://api-2.xi-ai.cn/v1"
DEFAULT_MODEL = "gpt-4o-audio-preview"


def test_abstract_base():
    print("\n" + "=" * 50)
    print("TEST 1: BaseFrontend is abstract")
    print("=" * 50)
    try:
        BaseFrontend()
        print("  XX Should have failed!")
    except TypeError as e:
        print(f"  Correctly blocked: {e}")
        print("  OK")


def test_prompt_loading():
    print("\n" + "=" * 50)
    print("TEST 2: Prompt loading")
    print("=" * 50)
    class TestFrontend(OpenAICompatibleFrontend):
        def __init__(self):
            self._model = "test"
    frontend = TestFrontend()
    system = frontend._load_prompt("frontend_system")
    user = frontend._load_prompt("frontend_user")
    print(f"  System: {len(system)} chars")
    print(f"  User: {len(user)} chars")
    print("  OK")


def test_audio_encoding(audio_path: str):
    print("\n" + "=" * 50)
    print("TEST 3: Audio encoding")
    print("=" * 50)
    class TestFrontend(OpenAICompatibleFrontend):
        def __init__(self):
            self._model = "test"
    frontend = TestFrontend()
    encoded = frontend._encode_audio(audio_path)
    print(f"  File: {audio_path}")
    print(f"  Size: {os.path.getsize(audio_path) / 1024:.1f} KB")
    print(f"  Base64: {len(encoded)} chars")
    print("  OK")


def test_no_api_key():
    print("\n" + "=" * 50)
    print("TEST 4: Missing API key")
    print("=" * 50)
    original = os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("DASHSCOPE_API_KEY", None)
    try:
        OpenAICompatibleFrontend(api_key=None)
        print("  XX Should have raised error!")
    except FrontendError as e:
        print(f"  Correctly caught: {e.message}")
        print("  OK")
    finally:
        if original:
            os.environ["OPENAI_API_KEY"] = original


def test_real_api_call(api_key: str, base_url: str, model: str, audio_path: str):
    print("\n" + "=" * 50)
    print("TEST 5: REAL API CALL")
    print("=" * 50)
    
    if not os.path.exists(audio_path):
        print(f"  SKIP Audio not found: {audio_path}")
        return
    
    print(f"  Model: {model}")
    print(f"  Base URL: {base_url}")
    print(f"  Audio: {audio_path}")
    print("  Creating frontend...")
    
    frontend = OpenAICompatibleFrontend(
        model=model,
        api_key=api_key,
        base_url=base_url,
    )
    
    print("  Calling API... (this may take 10-60 seconds)")
    print()
    
    try:
        result = frontend.run(
            question="What is being said in this audio?",
            audio_path=audio_path,
        )
        print(f"  === CAPTION ===")
        print(f"  {result.question_guided_caption}")
        print()
        print("  OK API call succeeded!")
    except Exception as e:
        print(f"  XX Error: {e}")
        import traceback
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(description="Frontend module tests")
    parser.add_argument("--api-key", type=str, default=None, help="API key for real test")
    parser.add_argument("--base-url", type=str, default=DEFAULT_BASE_URL, help="API base URL")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help="Model name")
    parser.add_argument("--audio", type=str, default=DEFAULT_AUDIO_PATH, help="Audio file path")
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("MODULE 2 TESTS: Frontend")
    print("=" * 60)
    
    test_abstract_base()
    test_prompt_loading()
    test_audio_encoding(args.audio)
    test_no_api_key()
    
    if args.api_key:
        test_real_api_call(args.api_key, args.base_url, args.model, args.audio)
    else:
        print("\n" + "=" * 50)
        print("TEST 5: REAL API CALL")
        print("=" * 50)
        print("  SKIP No --api-key provided.")
        print("  Run with: python tests/test_frontend.py --api-key sk-xxxxx")
    
    print("\n" + "=" * 50)
    print("ALL TESTS COMPLETED")
    print("=" * 50)


if __name__ == "__main__":
    main()
