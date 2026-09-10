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


import io
import wave


def pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 16000, channels: int = 1) -> bytes:
    """Convert raw 16-bit linear PCM bytes to a WAV file in memory."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


class StreamingSTTClient:
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._base_url = config.stt_base_url.rstrip("/")
        self._api_key = config.stt_api_key
        self._model = config.stt_model
        self._language = config.stt_language
        self._running = False
        self._audio_queue: asyncio.Queue = asyncio.Queue()
        self._result_callback: Optional[Callable[[STTResult], None]] = None

    async def __aenter__(self):
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=aiohttp.ClientTimeout(total=60),
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def connect(self, result_callback: Callable[[STTResult], None]):
        self._result_callback = result_callback
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=aiohttp.ClientTimeout(total=60),
            )
        self._running = True
        print(f"STT Client ready for {self._base_url} (model: {self._model})")

    async def transcribe_audio(
        self,
        pcm_data: bytes,
        response_id: int,
        sample_rate: int = 16000,
    ) -> Optional[str]:
        """Transcribe an audio slice via Groq's OpenAI-compatible /audio/transcriptions endpoint."""
        if not pcm_data or not self._running:
            return None

        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=aiohttp.ClientTimeout(total=60),
            )

        wav_data = pcm_to_wav(pcm_data, sample_rate=sample_rate)

        form = aiohttp.FormData()
        form.add_field(
            "file",
            wav_data,
            filename="speech.wav",
            content_type="audio/wav",
        )
        form.add_field("model", self._model)
        form.add_field("response_format", "json")
        if self._language:
            form.add_field("language", self._language)

        endpoint = f"{self._base_url}/audio/transcriptions"
        try:
            async with self._session.post(endpoint, data=form) as resp:
                if resp.status != 200:
                    err_msg = await resp.text()
                    print(f"Groq STT error ({resp.status}): {err_msg}")
                    return None

                data = await resp.json()
                text = data.get("text", "").strip()

                if state_manager.is_stale(response_id):
                    return None

                return text
        except Exception as e:
            print(f"Groq STT request failed: {e}")
            return None

    async def send_audio(self, audio_data: bytes):
        if self._running:
            await self._audio_queue.put(audio_data)

    async def close(self):
        self._running = False
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None


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