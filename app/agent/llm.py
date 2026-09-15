import os

MODEL_NAME = "inclusionai/ling-3.0-flash-sante:free"  
                                 


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