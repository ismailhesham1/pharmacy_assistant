from langchain_core.messages import HumanMessage, ToolMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from agent.state import AgentState
from agent.language import detect_language
from agent.llm import get_llm
from agent.tools import build_tools
from agent.prompts import build_system_prompt
from agent.disclaimer import append_disclaimer, DISCLAIMER


def detect_language_node(state: AgentState) -> dict:
    last_human = None
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            last_human = msg
            break
    lang = detect_language(last_human.content) if last_human else "en"
    return {"lang": lang}


def _strip_known_disclaimer(content: str) -> str:     #error fix
    """
    Removes our own fixed disclaimer text from the end of previous AI messages
    before re-sending them to the model as history. Without this, the model
    literally sees its own past disclaimer text in its input on every later
    turn - which can trigger degenerate repetition (a weaker/free-tier model
    fixating on and repeating a phrase it's already seen), which is exactly
    what produced dozens of repeated disclaimers in one response during
    real testing. The disclaimer still gets correctly re-added fresh by
    disclaimer_node every turn - this only affects what the MODEL sees as
    history, never what the user actually sees.
    """
    for disclaimer_text in DISCLAIMER.values():
        suffix = f"\n\n{disclaimer_text}"  
        if content.endswith(suffix):
            return content[: -len(suffix)]
    return content


def agent_node(state: AgentState) -> dict:
    lang = state["lang"]
    tools = build_tools(lang)
    llm = get_llm().bind_tools(tools)

    system_prompt = build_system_prompt(lang)
    cleaned_history = [
        AIMessage(content=_strip_known_disclaimer(m.content), id=m.id,
                  tool_calls=getattr(m, "tool_calls", []) or [])   #error fix
        if isinstance(m, AIMessage) else m
        for m in state["messages"]
    ]
    messages = [SystemMessage(content=system_prompt)] + cleaned_history

    response = llm.invoke(messages)
    return {"messages": [response]}


def tools_node(state: AgentState) -> dict:
    lang = state["lang"]
    tools = build_tools(lang)
    tools_by_name = {t.name: t for t in tools}

    last_message = state["messages"][-1]
    tool_messages = []
    for tool_call in last_message.tool_calls:
        tool = tools_by_name.get(tool_call["name"])
        if tool is None:
            result = f"Unknown tool: {tool_call['name']}"
        else:
            result = tool.invoke(tool_call["args"])
        tool_messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))
    return {"messages": tool_messages}


def disclaimer_node(state: AgentState) -> dict:
    lang = state["lang"]
    last_message = state["messages"][-1]

    answer_text = last_message.content or ""
    if not answer_text.strip():
        fallback = {   #error fix
            "en": "I'm sorry, I wasn't able to generate a response to that. Could you try rephrasing your question?",
            "ar": "عذرًا، لم أتمكن من إنشاء رد على ذلك. هل يمكنك إعادة صياغة سؤالك؟",
        }
        answer_text = fallback.get(lang, fallback["en"])

    final_text = append_disclaimer(answer_text, lang)
    updated = AIMessage(content=final_text, id=last_message.id)
    return {"messages": [updated]}


def should_continue(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        return "tools"
    return "disclaimer"


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("detect_language", detect_language_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.add_node("disclaimer", disclaimer_node)

    graph.set_entry_point("detect_language")
    graph.add_edge("detect_language", "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "disclaimer": "disclaimer"})
    graph.add_edge("tools", "agent")
    graph.add_edge("disclaimer", END)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)