import asyncio
import json
import uuid
from typing import Dict, Set, Optional
from dataclasses import dataclass, asdict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from backend.config import config
from backend.agent.agent import voice_agent, AgentState
from backend.agent.state import state_manager
from backend.agent.turn_manager import TurnStatus


app = FastAPI(title="Voice Assistant Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_states: Dict[str, AgentState] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        if len(self.active_connections) == 0:
            await voice_agent.start()
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.connection_states[client_id] = AgentState()

    async def disconnect(self, client_id: str):
        self.active_connections.pop(client_id, None)
        self.connection_states.pop(client_id, None)
        if len(self.active_connections) == 0:
            await voice_agent.stop()

    async def send_json(self, client_id: str, data: dict):
        ws = self.active_connections.get(client_id)
        if ws:
            try:
                await ws.send_json(data)
            except Exception:
                pass

    async def send_bytes(self, client_id: str, data: bytes):
        ws = self.active_connections.get(client_id)
        if ws:
            try:
                await ws.send_bytes(data)
            except Exception:
                pass

    async def broadcast(self, data: dict):
        for client_id, ws in list(self.active_connections.items()):
            try:
                await ws.send_json(data)
            except Exception:
                pass

    async def broadcast_bytes(self, data: bytes):
        for client_id, ws in list(self.active_connections.items()):
            try:
                await ws.send_bytes(data)
            except Exception:
                pass


manager = ConnectionManager()


async def agent_state_callback(state: AgentState):
    for client_id in manager.active_connections:
        await manager.send_json(client_id, {
            "type": "state",
            "status": state.status.value,
            "transcript": state.transcript,
            "transcript_final": state.transcript_final,
            "metrics": state.metrics,
        })


async def agent_transcript_callback(text: str, is_final: bool, is_user: bool = False):
    for client_id in manager.active_connections:
        await manager.send_json(client_id, {
            "type": "transcript",
            "text": text,
            "is_final": is_final,
            "is_user": is_user,
        })


async def agent_metrics_callback(metrics: dict):
    for client_id in list(manager.active_connections.keys()):
        await manager.send_json(client_id, {
            "type": "metrics",
            "data": metrics,
        })


def agent_audio_callback(chunk: bytes):
    pass
    # Double-playback via WebSocket and PyAudio causes echo. We rely on PyAudio.
    # try:
    #     loop = asyncio.get_running_loop()
    #     loop.create_task(manager.broadcast_bytes(chunk))
    # except RuntimeError:
    #     pass


voice_agent.on_state_change = agent_state_callback
voice_agent.on_transcript = agent_transcript_callback
voice_agent.on_metrics = agent_metrics_callback
voice_agent.on_audio_chunk = agent_audio_callback


@app.on_event("startup")
async def startup_event():
    pass


@app.on_event("shutdown")
async def shutdown_event():
    pass


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(websocket, client_id)
    try:
        await manager.send_json(client_id, {
            "type": "connected",
            "client_id": client_id,
            "state": voice_agent.get_state(),
        })

        while True:
            data = await websocket.receive_json()
            await handle_client_message(client_id, data)
    except WebSocketDisconnect:
        await manager.disconnect(client_id)
    except Exception as e:
        print(f"WebSocket error: {e}")
        await manager.disconnect(client_id)


async def handle_client_message(client_id: str, data: dict):
    msg_type = data.get("type")

    if msg_type == "interrupt":
        new_response_id = voice_agent.interrupt()
        await manager.send_json(client_id, {
            "type": "interrupted",
            "new_response_id": new_response_id,
        })

    elif msg_type in ("prompt", "message"):
        text = data.get("text", "").strip()
        if text:
            voice_agent.process_text_input(text)

    elif msg_type == "get_state":
        await manager.send_json(client_id, {
            "type": "state",
            "data": voice_agent.get_state(),
        })

    elif msg_type == "ping":
        await manager.send_json(client_id, {"type": "pong"})


@app.post("/api/prompt")
async def post_prompt(payload: dict):
    text = payload.get("text", "").strip()
    if not text:
        return {"error": "Missing text"}
    voice_agent.process_text_input(text)
    return {"status": "ok", "processed": text}


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/api/state")
async def get_state():
    return voice_agent.get_state()


@app.get("/api/metrics")
async def get_metrics():
    from backend.metrics.latency import latency_logger
    return {"records": latency_logger.get_recent_records()}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)