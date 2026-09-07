import os

MODEL_NAME = "openrouter/free"  # after THREE specific free models failed today in
                                  # different ways (nex-agi deprecated, both Gemma
                                  # variants persistently rate-limited, gpt-oss-120b
                                  # unavailable) - hand-picking a specific free model
                                  # is clearly not reliable today. The auto-router
                                  # dynamically selects from whatever's CURRENTLY
                                  # available and filters for tool-calling support,
                                  # trading predictability of which exact model
                                  # answers for actual uptime.


def get_llm():
    from langchain_openai import ChatOpenAI

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY environment variable is not set. "
            "Get a free key from https://openrouter.ai/settings/keys"
        )

    return ChatOpenAI(
        model=MODEL_NAME,
        openai_api_key=api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        timeout=30,
        max_retries=3,
    )