import asyncio
import time
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from backend.agent.state import state_manager, ConversationState
from backend.agent.cancellation import fence_result, create_tagged_result
from backend.services.stt import stt_client, STTResult
from backend.services.llm import llm_manager, LLMChunk
from backend.services.rime import rime_tts_manager, RimeAudioChunk
from backend.services.audio import FullDuplexAudio, AudioChunk
from backend.metrics.latency import log_turn_metrics


class TurnStatus(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    TOOL_RUNNING = "tool_running"


@dataclass
class TurnMetrics:
    turn_id: int
    response_id: int
    t0: Optional[float] = None
    t1: Optional[float] = None
    t2: Optional[float] = None
    t3: Optional[float] = None
    t4: Optional[float] = None
    t5: Optional[float] = None


class TurnManager:
    def __init__(
        self,
        on_status_change: Optional[Callable[[TurnStatus], None]] = None,
        on_transcript: Optional[Callable[[str, bool], None]] = None,
        on_metrics: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.on_status_change = on_status_change
        self.on_transcript = on_transcript
        self.on_metrics = on_metrics

        self.audio = FullDuplexAudio(on_input_chunk=self._handle_audio_input)
        self._stt_connected = False
        self._current_transcript = ""
        self._transcript_final = False
        self._pending_llm_task: Optional[asyncio.Task] = None
        self._pending_tool_task: Optional[asyncio.Task] = None
        self._current_turn_metrics: Optional[TurnMetrics] = None
        self._running = False

    def _set_status(self, status: TurnStatus):
        if self.on_status_change:
            self.on_status_change(status)

    async def start(self):
        self._running = True
        await llm_manager.initialize()
        await rime_tts_manager.initialize()
        await stt_client.connect(self._handle_stt_result)
        self._stt_connected = True
        rime_tts_manager.set_playback_callback(self.audio.write_playback)
        self.audio.start()
        self._set_status(TurnStatus.LISTENING)

    async def stop(self):
        self._running = False
        self.audio.stop()
        await stt_client.close()
        await rime_tts_manager.close()
        await llm_manager.close()

    def _handle_audio_input(self, chunk: AudioChunk):
        if self._stt_connected:
            asyncio.create_task(stt_client.send_audio(chunk.data))

    def _handle_stt_result(self, result: STTResult):
        if state_manager.is_stale(result.response_id):
            return

        self._current_transcript = result.text
        self._transcript_final = result.is_final

        if self.on_transcript:
            self.on_transcript(result.text, result.is_final)

        if result.is_final and result.text.strip():
            state_manager.state.mark_t1()
            self._process_user_turn(result.text, result.response_id)

    def _process_user_turn(self, text: str, response_id: int):
        if self._pending_llm_task:
            self._pending_llm_task.cancel()

        self._pending_llm_task = asyncio.create_task(
            self._run_llm_pipeline(text, response_id)
        )

    async def _run_llm_pipeline(self, text: str, response_id: int):
        self._set_status(TurnStatus.PROCESSING)
        state_manager.state.mark_t2()

        sentence_buffer = ""
        tool_calls = []

        try:
            async for chunk in llm_manager.process_turn(text, response_id, on_chunk=self._handle_llm_chunk):
                if state_manager.is_stale(chunk.response_id):
                    return

                sentence_buffer += chunk.content

                if chunk.tool_calls:
                    tool_calls = chunk.tool_calls
                    self._set_status(TurnStatus.TOOL_RUNNING)
                    state_manager.set_tool_running(True)
                    self._pending_tool_task = asyncio.create_task(
                        self._handle_tool_calls(tool_calls, response_id)
                    )

                if chunk.is_final and not chunk.tool_calls:
                    if sentence_buffer.strip():
                        state_manager.state.mark_t3()
                        asyncio.create_task(self._stream_to_rime(sentence_buffer.strip(), response_id))

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"LLM pipeline error: {e}")

    def _handle_llm_chunk(self, chunk: LLMChunk):
        pass

    async def _handle_tool_calls(self, tool_calls: List, response_id: int):
        try:
            for tool_call in tool_calls:
                if state_manager.is_stale(response_id):
                    tool_call.status = "cancelled"
                    return

            if self._pending_tool_task:
                await self._pending_tool_task

            if state_manager.is_stale(response_id):
                return

            follow_up_messages = llm_manager.get_messages()
            sentence_buffer = ""

            async for chunk in llm_manager._client.stream_completion(
                follow_up_messages, response_id
            ):
                if state_manager.is_stale(chunk.response_id):
                    return
                sentence_buffer += chunk.content
                if chunk.is_final and sentence_buffer.strip():
                    state_manager.state.mark_t3()
                    await self._stream_to_rime(sentence_buffer.strip(), response_id)
                    break

        except asyncio.CancelledError:
            pass
        finally:
            state_manager.set_tool_running(False)
            if not state_manager.is_stale(response_id):
                self._set_status(TurnStatus.LISTENING)

    async def _stream_to_rime(self, text: str, response_id: int):
        self._set_status(TurnStatus.SPEAKING)
        state_manager.set_audio_playing(True)

        try:
            async for chunk in rime_tts_manager.speak(text, response_id):
                if state_manager.is_stale(chunk.response_id):
                    self.audio.stop_playback_immediately()
                    state_manager.set_audio_playing(False)
                    return

                if not state_manager.state.current_turn_t5:
                    state_manager.state.mark_t5()
                    if self.on_metrics:
                        self.on_metrics(state_manager.state.to_dict())

        except asyncio.CancelledError:
            pass
        finally:
            state_manager.set_audio_playing(False)
            if not state_manager.is_stale(response_id):
                self._set_status(TurnStatus.LISTENING)

    def interrupt(self) -> int:
        new_response_id = state_manager.interrupt()
        self.audio.stop_playback_immediately()

        if self._pending_llm_task:
            self._pending_llm_task.cancel()
            self._pending_llm_task = None

        if self._pending_tool_task:
            self._pending_tool_task.cancel()
            self._pending_tool_task = None

        state_manager.set_tool_running(False)
        state_manager.set_audio_playing(False)
        self._set_status(TurnStatus.LISTENING)

        return new_response_id

    def get_state(self) -> Dict[str, Any]:
        return state_manager.state.to_dict()


turn_manager = TurnManager()