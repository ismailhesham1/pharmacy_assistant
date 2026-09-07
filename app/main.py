
"""
FastAPI entry point. Run with:
    cd app
    uvicorn main:app --reload
"""
from fastapi import FastAPI, WebSocket

from chat.websocket_handler import handle_connection

app = FastAPI(title="Pharmacy Assistant API")


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await handle_connection(websocket)


@app.get("/")
async def health_check():
    return {"status": "ok"}