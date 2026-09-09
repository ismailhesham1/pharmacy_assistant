
"""
FastAPI entry point. Run with:
    cd app
    uvicorn main:app --reload
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from agent.graph import build_graph
from chat.websocket_handler import handle_connection

# Chat history lives here so it survives reconnects, page refreshes and
# server restarts (previously an in-memory MemorySaver - lost on any of
# those). Same app/data/ convention as the chroma vector store.
DB_PATH = Path(__file__).parent / "data" / "chat_history.sqlite3"


@asynccontextmanager
async def lifespan(app: FastAPI):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(DB_PATH)) as checkpointer:
        app.state.agent_app = build_graph(checkpointer=checkpointer)
        yield


app = FastAPI(title="Pharmacy Assistant API", lifespan=lifespan)


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await handle_connection(websocket)


@app.get("/")
async def health_check():
    return {"status": "ok"}