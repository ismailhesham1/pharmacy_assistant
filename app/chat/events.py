from langchain_core.messages import AIMessage, HumanMessage

TOOL_RESULT_PREVIEW_CHARS = 150 # Maximum number of characters to display for tool results


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
        if node != "agent": 
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

        # Send the disclaimer node's full final content and have the
        # frontend REPLACE the message with it, rather than assuming it's
        # always just the disclaimer suffix appended onto whatever was
        # already streamed live. That assumption broke whenever
        # disclaimer_node substitutes a fallback message (e.g. the model
        # returned an empty/whitespace answer) - the fallback text isn't an
        # appended suffix, so the old diff-based "just send the suffix"
        # logic silently dropped it and the user saw what looked like an
        # empty response. Sending the full content here is correct in both
        # cases and self-heals any other streamed/final mismatch too.
        final_content = getattr(messages[0], "content", "") or ""
        return {"type": "replace", "content": final_content}

    return None