import logging #structured Logs 
import uuid

from fastapi import WebSocket, WebSocketDisconnect
from langchain_core.messages import HumanMessage

from agent.graph import build_graph
from agent.injection_guard import check_for_injection
from chat.events import translate_event

logger = logging.getLogger("chat")

_agent_app = None


def _get_agent_app():
    global _agent_app
    if _agent_app is None:
        _agent_app = build_graph()
    return _agent_app


async def handle_connection(websocket: WebSocket) -> None:
    await websocket.accept()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    agent_app = _get_agent_app()

    try:
        while True:
            data = await websocket.receive_json()
            user_text = data.get("content", "").strip()
            if not user_text:
                continue

            if check_for_injection(user_text):
                logger.warning("Possible prompt injection attempt on thread %s: %r", thread_id, user_text)

            input_state = {"messages": [HumanMessage(content=user_text)], "lang": ""}

            async for event in agent_app.astream_events(input_state, config=config, version="v2"):
                message = translate_event(event)
                if message:
                    await websocket.send_json(message)

            await websocket.send_json({"type": "done"})
#incase of crash/disconnection
    except WebSocketDisconnect:
        pass