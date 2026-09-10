import asyncio
import time
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
import numpy as np

from backend.config import config
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
    PAUSED = "paused"


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
        on_audio_chunk: Optional[Callable[[bytes], Any]] = None,
    ):
        self.on_status_change = on_status_change
        self.on_transcript = on_transcript
        self.on_metrics = on_metrics
        self.on_audio_chunk = on_audio_chunk

        self.audio = FullDuplexAudio(on_input_chunk=self._handle_audio_input)
        self._stt_connected = False
        self._current_transcript = ""
        self._transcript_final = False
        self._pending_llm_task: Optional[asyncio.Task] = None
        self._pending_tool_task: Optional[asyncio.Task] = None
        self._current_turn_metrics: Optional[TurnMetrics] = None
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._is_paused = False

        self._speech_buffer = bytearray()
        self._speech_detected = False
        self._silence_frames = 0

    def _set_status(self, status: TurnStatus):
        if status == TurnStatus.LISTENING and self._is_paused:
            status = TurnStatus.PAUSED
            
        if self.on_status_change:
            self.on_status_change(status)

    def _send_transcript(self, text: str, is_final: bool, is_user: bool = False):
        if not self.on_transcript:
            return
        try:
            self.on_transcript(text, is_final, is_user)
        except TypeError:
            self.on_transcript(text, is_final)

    async def start(self):
        self._loop = asyncio.get_running_loop()
        self._running = True
        await llm_manager.initialize()
        await rime_tts_manager.initialize()
        await stt_client.connect(self._handle_stt_result)
        self._stt_connected = True

        def _handle_playback(audio_bytes: bytes):
            self.audio.write_playback(audio_bytes)
            if self.on_audio_chunk:
                self.on_audio_chunk(audio_bytes)

        rime_tts_manager.set_playback_callback(_handle_playback)
        self.audio.start()
        self._set_status(TurnStatus.LISTENING)

    def process_text_input(self, text: str):
        # Ensure any leftover playback from previous turns is cleared
        self.audio.stop_playback_immediately()

        state_manager.new_turn()
        response_id = state_manager.get_current_response_id()
        state_manager.state.current_turn_t0 = time.perf_counter()
        state_manager.state.mark_t1()
        if self.on_transcript:
            self._send_transcript(text, True, True)
        self._process_user_turn(text, response_id)

    async def stop(self):
        self._running = False
        self.audio.stop()
        await stt_client.close()
        await rime_tts_manager.close()
        await llm_manager.close()

    def toggle_listening(self):
        self._is_paused = not self._is_paused
        if self._is_paused:
            self._speech_detected = False
            self._speech_buffer = bytearray()
            self._set_status(TurnStatus.PAUSED)
        else:
            self._set_status(TurnStatus.LISTENING)

    def _handle_audio_input(self, chunk: AudioChunk):
        if not self._stt_connected or not self._running or self._is_paused:
            return

        if len(chunk.data) < 2:
            return

        # Calculate RMS energy of 16-bit PCM chunk
        samples = np.frombuffer(chunk.data, dtype=np.int16)
        if len(samples) == 0:
            return

        energy = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2))) / 32768.0
        # If audio is playing through speaker, require higher energy to avoid self-interrupting
        is_audio_playing = self.audio.is_playing()
        current_threshold = 0.22 if is_audio_playing else config.vad_threshold
        is_voice = energy > current_threshold

        if is_voice:
            # Immediate barge-in on new speech if audio is playing
            if is_audio_playing:
                self.interrupt()

            if not self._speech_detected:
                self._speech_detected = True
                self._speech_buffer = bytearray()
                self._silence_frames = 0

            self._speech_buffer.extend(chunk.data)
            self._silence_frames = 0

        elif self._speech_detected:
            self._speech_buffer.extend(chunk.data)
            self._silence_frames += 1

            chunk_duration = len(chunk.data) / (chunk.sample_rate * 2)
            silence_duration = self._silence_frames * chunk_duration

            if silence_duration >= config.vad_silence_duration:
                # Speech turn ended (T0)
                self._speech_detected = False
                self._silence_frames = 0
                pcm_data = bytes(self._speech_buffer)
                self._speech_buffer = bytearray()

                # Filter out clicks/noise (<0.5s)
                if len(pcm_data) >= int(chunk.sample_rate * 2 * 0.5):
                    if self._loop and self._loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            self._process_audio_turn(pcm_data, chunk.sample_rate),
                            self._loop,
                        )

    async def _process_audio_turn(self, pcm_data: bytes, sample_rate: int):
        samples = np.frombuffer(pcm_data, dtype=np.int16)
        if len(samples) == 0:
            return

        mean_energy = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2))) / 32768.0
        if mean_energy < 0.03:
            return

        # We pass a dummy response_id for transcription since we haven't committed to a new turn yet
        dummy_id = state_manager.get_current_response_id() + 1

        # Transcribe with Groq whisper-large-v3-turbo
        text = await stt_client.transcribe_audio(pcm_data, dummy_id, sample_rate=sample_rate)

        if not text:
            return

        # Check for junk hallucination transcripts
        clean_text = text.strip().lower().rstrip(".!?,")
        if not clean_text or (clean_text in ("thank you", "thanks", "thanks for watching", "mm-hmm", "yeah", "you", "bye") and len(pcm_data) < sample_rate * 2 * 1.5):
            return

        # Now that we have a valid transcript, commit to a new turn
        self.audio.stop_playback_immediately()
        state_manager.new_turn()
        response_id = state_manager.get_current_response_id()
        
        # Mark T0: User speech ended
        state_manager.state.current_turn_t0 = time.perf_counter()
        self._set_status(TurnStatus.PROCESSING)

        # Mark T1: STT transcript ready
        state_manager.state.mark_t1()
        if self.on_transcript:
            self._send_transcript(text, True, True)

        self._process_user_turn(text, response_id)

    def _handle_stt_result(self, result: STTResult):
        if state_manager.is_stale(result.response_id):
            return

        self._current_transcript = result.text
        self._transcript_final = result.is_final

        if self.on_transcript:
            self._send_transcript(result.text, result.is_final, True)

    def _process_user_turn(self, text: str, response_id: int):
        if self._pending_llm_task and not self._pending_llm_task.done():
            self._pending_llm_task.cancel()

        self._pending_llm_task = asyncio.create_task(
            self._run_llm_pipeline(text, response_id)
        )

    async def _run_llm_pipeline(self, text: str, response_id: int):
        print(f"[TurnManager] Processing turn: {text!r} (response_id={response_id})")
        self._set_status(TurnStatus.PROCESSING)
        state_manager.state.mark_t2()

        sentence_buffer = ""
        tool_calls = []
        first_chunk_sent = False

        try:
            async for chunk in llm_manager.process_turn(text, response_id, on_chunk=self._handle_llm_chunk):
                if state_manager.is_stale(chunk.response_id):
                    return

                sentence_buffer += chunk.content

                if chunk.tool_calls:
                    tool_calls = chunk.tool_calls
                    self._set_status(TurnStatus.TOOL_RUNNING)
                    state_manager.set_tool_running(True)

                # Sentence-level streaming: dispatch first sentence immediately on punctuation boundary
                if not tool_calls and not first_chunk_sent:
                    for delimiter in [". ", "? ", "! ", ".\n", "!\n", "?\n"]:
                        if delimiter in sentence_buffer:
                            parts = sentence_buffer.split(delimiter, 1)
                            first_sentence = parts[0] + delimiter.strip()
                            if len(first_sentence.strip()) > 8:
                                first_chunk_sent = True
                                sentence_buffer = parts[1]
                                state_manager.state.mark_t3()
                                await self._stream_to_rime(first_sentence.strip(), response_id)
                                break

            # Stream remaining buffer after LLM loop
            if not tool_calls and sentence_buffer.strip() and not state_manager.is_stale(response_id):
                if not first_chunk_sent:
                    state_manager.state.mark_t3()
                await self._stream_to_rime(sentence_buffer.strip(), response_id)

            # If tool calls occurred, stream follow-up answer from LLM with sentence-level streaming
            if tool_calls and not state_manager.is_stale(response_id):
                self._set_status(TurnStatus.PROCESSING)
                follow_up_messages = llm_manager.get_messages()
                follow_up_buffer = ""
                tool_first_sent = False
                async for chunk in llm_manager._client.stream_completion(
                    follow_up_messages, response_id
                ):
                    if state_manager.is_stale(chunk.response_id):
                        return
                    follow_up_buffer += chunk.content
                    if not tool_first_sent:
                        for delimiter in [". ", "? ", "! ", ".\n", "!\n", "?\n"]:
                            if delimiter in follow_up_buffer:
                                parts = follow_up_buffer.split(delimiter, 1)
                                first_sentence = parts[0] + delimiter.strip()
                                if len(first_sentence.strip()) > 8:
                                    tool_first_sent = True
                                    follow_up_buffer = parts[1]
                                    state_manager.state.mark_t3()
                                    await self._stream_to_rime(first_sentence.strip(), response_id)
                                    break

                if follow_up_buffer.strip() and not state_manager.is_stale(response_id):
                    if not tool_first_sent:
                        state_manager.state.mark_t3()
                    llm_manager.add_assistant_message(follow_up_buffer.strip())
                    await self._stream_to_rime(follow_up_buffer.strip(), response_id)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"LLM pipeline error: {e}")
        finally:
            state_manager.set_tool_running(False)
            state_manager.set_audio_playing(False)
            self._set_status(TurnStatus.LISTENING)

    def _handle_llm_chunk(self, chunk: LLMChunk):
        pass

    async def _stream_to_rime(self, text: str, response_id: int):
        if state_manager.is_stale(response_id):
            return

        print(f"[TurnManager] Streaming {len(text)} chars to Rime TTS: {text!r} (response_id={response_id})")
        if self.on_transcript:
            self._send_transcript(text, True, False)

        self._set_status(TurnStatus.SPEAKING)
        state_manager.set_audio_playing(True)

        try:
            async for chunk in rime_tts_manager.speak(text, response_id):
                if state_manager.is_stale(chunk.response_id):
                    self.audio.stop_playback_immediately()
                    return

                if not state_manager.state.current_turn_t5:
                    state_manager.state.mark_t5()
                    log_turn_metrics(state_manager.state.to_dict())
                    if self.on_metrics:
                        self.on_metrics(state_manager.state.to_dict())

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[TurnManager] Rime TTS playback error: {e}")
        finally:
            state_manager.set_audio_playing(False)
            self._set_status(TurnStatus.LISTENING)

    def interrupt(self) -> int:
        new_response_id = state_manager.interrupt()
        self.audio.stop_playback_immediately()
        self._speech_detected = False
        self._speech_buffer = bytearray()
        self._silence_frames = 0

        if self._pending_llm_task and not self._pending_llm_task.done():
            self._pending_llm_task.cancel()
            self._pending_llm_task = None

        if self._pending_tool_task and not self._pending_tool_task.done():
            self._pending_tool_task.cancel()
            self._pending_tool_task = None

        state_manager.set_tool_running(False)
        state_manager.set_audio_playing(False)
        self._set_status(TurnStatus.LISTENING)

        return new_response_id

    def get_state(self) -> Dict[str, Any]:
        return state_manager.state.to_dict()


turn_manager = TurnManager()