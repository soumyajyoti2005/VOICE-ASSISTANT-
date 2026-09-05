import asyncio
import aiohttp
import json
import base64
from typing import AsyncGenerator, Optional, Callable
from dataclasses import dataclass

from backend.config import config
from backend.agent.state import state_manager
from backend.agent.cancellation import create_tagged_result, fence_result


@dataclass
class STTResult:
    text: str
    is_final: bool
    response_id: int
    timestamp: float


class StreamingSTTClient:
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._base_url = config.stt_base_url
        self._api_key = config.stt_api_key
        self._model = config.stt_model
        self._language = config.stt_language
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._running = False
        self._send_task: Optional[asyncio.Task] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._audio_queue: asyncio.Queue = asyncio.Queue()
        self._result_callback: Optional[Callable[[STTResult], None]] = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=aiohttp.ClientTimeout(total=60),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        if self._session:
            await self._session.close()
            self._session = None

    async def connect(self, result_callback: Callable[[STTResult], None]):
        self._result_callback = result_callback
        self._ws = await self._session.ws_connect(
            f"{self._base_url}/realtime/transcription",
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        self._running = True
        self._send_task = asyncio.create_task(self._send_loop())
        self._receive_task = asyncio.create_task(self._receive_loop())
        await self._send_config()

    async def _send_config(self):
        config_msg = {
            "type": "transcription_session.update",
            "session": {
                "model": self._model,
                "language": self._language,
                "response_format": "json",
            },
        }
        await self._ws.send_json(config_msg)

    async def _send_loop(self):
        while self._running:
            try:
                audio_chunk = await asyncio.wait_for(self._audio_queue.get(), timeout=0.1)
                if audio_chunk is None:
                    break
                await self._ws.send_bytes(audio_chunk)
            except asyncio.TimeoutError:
                continue
            except Exception:
                break

    async def _receive_loop(self):
        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    if data.get("type") == "transcription.text":
                        result = STTResult(
                            text=data.get("text", ""),
                            is_final=data.get("is_final", False),
                            response_id=state_manager.get_current_response_id(),
                            timestamp=asyncio.get_event_loop().time(),
                        )
                        if self._result_callback:
                            self._result_callback(result)
                except json.JSONDecodeError:
                    continue
            elif msg.type == aiohttp.WSMsgType.ERROR:
                break

    async def send_audio(self, audio_data: bytes):
        if self._running:
            await self._audio_queue.put(audio_data)

    async def close(self):
        self._running = False
        await self._audio_queue.put(None)
        if self._send_task:
            self._send_task.cancel()
            try:
                await self._send_task
            except asyncio.CancelledError:
                pass
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()
            self._ws = None


class MockSTTClient:
    """Mock STT for testing without API keys"""

    def __init__(self):
        self._running = False
        self._result_callback: Optional[Callable[[STTResult], None]] = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def connect(self, result_callback: Callable[[STTResult], None]):
        self._result_callback = result_callback
        self._running = True

    async def send_audio(self, audio_data: bytes):
        pass

    async def close(self):
        self._running = False


stt_client = StreamingSTTClient()