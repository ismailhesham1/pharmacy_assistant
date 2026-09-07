from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    lang: str  # "en" or "ar" - detected fresh each turn in detect_language_node