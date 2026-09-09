from langchain_core.messages import AIMessage, HumanMessage

from agent.disclaimer import DISCLAIMER

TOOL_RESULT_PREVIEW_CHARS = 150


def serialize_history(messages: list) -> list[dict]:
    """
    Converts a thread's checkpointed LangGraph messages into the plain
    {role, content} shape the frontend already renders for each turn (see
    App.jsx). Tool-call/tool-result messages and the SystemMessage aren't
    included - the chat UI never displayed those directly, only the final
    streamed answer per turn, so restored history looks the same as what
    was on screen originally.
    """
    history = []
    for m in messages:
        if isinstance(m, HumanMessage) and m.content:
            history.append({"role": "user", "content": m.content})
        elif isinstance(m, AIMessage) and m.content and not getattr(m, "tool_calls", None):
            history.append({"role": "assistant", "content": m.content})
    return history


def translate_event(event: dict) -> dict | None:
    event_type = event.get("event")
#chat
    if event_type == "on_chat_model_stream":
        node = event.get("metadata", {}).get("langgraph_node")
        if node != "agent": #filters out duplicates
            return None

        chunk = event.get("data", {}).get("chunk")
        content = getattr(chunk, "content", None) if chunk is not None else None
        if content:
            return {"type": "token", "content": content}
        return None
#tool
    if event_type == "on_tool_start":
        return {
            "type": "tool_call",
            "tool": event.get("name"),
            "args": event.get("data", {}).get("input") or {},
        }

    if event_type == "on_tool_end":
        output = event.get("data", {}).get("output")
        content = getattr(output, "content", str(output)) if output is not None else ""
        preview = content[:TOOL_RESULT_PREVIEW_CHARS]
        if len(content) > TOOL_RESULT_PREVIEW_CHARS:
            preview += "..."
        return {
            "type": "tool_result",
            "tool": event.get("name"),
            "preview": preview,
        }
#end and disclaimer
    if event_type == "on_chain_end":
        node = event.get("metadata", {}).get("langgraph_node")
        if node != "disclaimer":
            return None

        output = event.get("data", {}).get("output") or {}
        messages = output.get("messages") or []
        if not messages:
            return None

        final_content = getattr(messages[0], "content", "") or ""
        for disclaimer_text in DISCLAIMER.values():
            suffix = f"\n\n{disclaimer_text}"
            if final_content.endswith(suffix):
                return {"type": "token", "content": suffix}
        return None

    return None