import asyncio
import aiohttp
import json
from typing import AsyncGenerator, Optional
from dataclasses import dataclass

from backend.config import config
from backend.agent.state import state_manager
from backend.agent.cancellation import create_tagged_result, fence_result


@dataclass
class RimeAudioChunk:
    audio_data: bytes
    is_final: bool
    response_id: int


class RimeTTSClient:
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._base_url = config.rime_base_url
        self._api_key = config.rime_api_key
        self._voice = config.rime_voice
        self._model = config.rime_model
        self._sample_rate = config.rime_sample_rate
        self._encoding = config.rime_encoding

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=30),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()
            self._session = None

    async def stream_tts(
        self,
        text: str,
        response_id: int,
        on_chunk: Optional[callable] = None,
    ) -> AsyncGenerator[RimeAudioChunk, None]:
        if not self._session:
            raise RuntimeError("RimeTTSClient not initialized. Use async context manager.")

        payload = {
            "text": text,
            "voice": self._voice,
            "model": self._model,
            "sample_rate": self._sample_rate,
            "encoding": self._encoding,
            "streaming": True,
        }

        async with self._session.post(f"{self._base_url}/tts/stream", json=payload) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise RuntimeError(f"Rime TTS error: {resp.status} - {error_text}")

            async for line in resp.content:
                if not line:
                    continue
                line = line.decode("utf-8").strip()
                if not line or line == "data: [DONE]":
                    continue
                if line.startswith("data: "):
                    line = line[6:]
                try:
                    data = json.loads(line)
                    if "audio" in data:
                        audio_bytes = bytes.fromhex(data["audio"])
                        is_final = data.get("is_final", False)
                        chunk = RimeAudioChunk(
                            audio_data=audio_bytes,
                            is_final=is_final,
                            response_id=response_id,
                        )
                        if on_chunk:
                            on_chunk(chunk)
                        yield chunk
                except json.JSONDecodeError:
                    continue


class RimeTTSManager:
    def __init__(self):
        self._client: Optional[RimeTTSClient] = None
        self._current_task: Optional[asyncio.Task] = None
        self._playback_callback: Optional[callable] = None

    async def initialize(self):
        self._client = RimeTTSClient()
        await self._client.__aenter__()

    async def close(self):
        if self._current_task:
            self._current_task.cancel()
            try:
                await self._current_task
            except asyncio.CancelledError:
                pass
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None

    def set_playback_callback(self, callback: callable):
        self._playback_callback = callback

    async def speak(
        self,
        text: str,
        response_id: int,
    ) -> AsyncGenerator[RimeAudioChunk, None]:
        if not self._client:
            raise RuntimeError("RimeTTSManager not initialized")

        async def _on_chunk(chunk: RimeAudioChunk):
            if self._playback_callback:
                self._playback_callback(chunk.audio_data)

        tagged = create_tagged_result(text, response_id)

        async for chunk in self._client.stream_tts(text, response_id, on_chunk=_on_chunk):
            fenced = fence_result(chunk)
            if fenced is None:
                break
            yield fenced


rime_tts_manager = RimeTTSManager()