"""
Quick standalone check that your OpenRouter API key works, using the same
library (langchain-openai) the real agent will use - OpenRouter exposes an
OpenAI-compatible API, so ChatOpenAI just needs its base_url pointed at
OpenRouter instead of OpenAI.

Setup:
    1. Get a free API key from https://openrouter.ai/settings/keys
    2. Set it as an environment variable:
         Windows (PowerShell): $env:OPENROUTER_API_KEY="your-key-here"
         Mac/Linux:            export OPENROUTER_API_KEY="your-key-here"
    3. Run: python check_llm_key.py
"""
import os
import sys

MODEL_NAME = "google/gemma-4-31b-it:free"


def run():
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY environment variable is not set.")
        print("Get a free key from https://openrouter.ai/settings/keys and set it, then re-run.")
        sys.exit(1)

    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        print("ERROR: langchain-openai is not installed.")
        print("Run: pip install langchain-openai")
        sys.exit(1)

    print(f"Testing OpenRouter API key against model '{MODEL_NAME}'...")

    try:
        llm = ChatOpenAI(
            model=MODEL_NAME,
            openai_api_key=api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            timeout=20,
            max_retries=1,
        )
        response = llm.invoke("Reply with exactly the word: OK")
    except Exception as e:
        print(f"\nFAILED - the API call raised an error (or timed out after 20s):\n{e}")
        print("\nCommon causes: invalid/expired key, the model was deprecated/removed "
              "(free models on OpenRouter rotate - check https://openrouter.ai/models "
              "for a current free model if this looks like a 'model not found' error), "
              "or you've hit the free tier's daily/rate limit (200 requests/day, "
              "20/minute, shared across all free models).")
        sys.exit(1)

    print(f"\nSUCCESS - model responded: {response.content!r}")
    print("Your API key works and the langchain-openai + OpenRouter integration is functional.")


if __name__ == "__main__":
    run()