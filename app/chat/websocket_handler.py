import json
import logging #structured Logs
import uuid

from fastapi import WebSocket, WebSocketDisconnect
from langchain_core.messages import HumanMessage

from agent.injection_guard import check_for_injection
from chat.events import serialize_history, translate_event

logger = logging.getLogger("chat")


async def handle_connection(websocket: WebSocket) -> None:
    await websocket.accept()
    # A thread_id supplied by the client (persisted client-side across
    # reconnects/refreshes) resumes that same conversation via the
    # checkpointer; otherwise start a new one and hand its id back to the
    # client so it can remember it for next time.
    thread_id = websocket.query_params.get("thread_id") or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    agent_app = websocket.app.state.agent_app

    try:
        state = await agent_app.aget_state(config)
        past_messages = state.values.get("messages", []) if state else []
        await websocket.send_json({
            "type": "history",
            "thread_id": thread_id,
            "messages": serialize_history(past_messages),
        })

        while True:
            try:
                data = await websocket.receive_json()
            except json.JSONDecodeError:
                # Not a WebSocketDisconnect - the socket is still open, the
                # client just sent a frame that isn't valid JSON. Ignore it
                # and keep the connection alive instead of crashing.
                logger.warning("Received malformed (non-JSON) message on thread %s; ignoring.", thread_id)
                continue

            user_text = data.get("content")
            if not isinstance(user_text, str):
                # "content" missing, null, or some other non-string type -
                # nothing sensible to send to the agent, skip this frame.
                continue
            user_text = user_text.strip()
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