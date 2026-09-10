import asyncio
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass

from backend.agent.turn_manager import turn_manager, TurnManager, TurnStatus
from backend.agent.state import state_manager, ConversationState
from backend.metrics.latency import log_turn_metrics


@dataclass
class AgentState:
    status: TurnStatus = TurnStatus.IDLE
    transcript: str = ""
    transcript_final: bool = False
    metrics: Dict[str, Any] = None


class VoiceAgent:
    def __init__(
        self,
        on_state_change: Optional[Callable[[AgentState], None]] = None,
        on_transcript: Optional[Callable[[str, bool], None]] = None,
        on_metrics: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_audio_chunk: Optional[Callable[[bytes], None]] = None,
    ):
        self.on_state_change = on_state_change
        self.on_transcript = on_transcript
        self.on_metrics = on_metrics
        self.on_audio_chunk = on_audio_chunk

        self._turn_manager = TurnManager(
            on_status_change=self._handle_status_change,
            on_transcript=self._handle_transcript,
            on_metrics=self._handle_metrics,
            on_audio_chunk=self._handle_audio_chunk,
        )
        self._current_state = AgentState()

    def _handle_audio_chunk(self, chunk: bytes):
        if self.on_audio_chunk:
            self.on_audio_chunk(chunk)

    def _dispatch_callback(self, cb, *args):
        if not cb:
            return
        res = cb(*args)
        if asyncio.iscoroutine(res):
            loop = None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                if getattr(self, "_turn_manager", None) and self._turn_manager._loop and self._turn_manager._loop.is_running():
                    loop = self._turn_manager._loop

            if loop and loop.is_running():
                try:
                    current_loop = asyncio.get_running_loop()
                    if current_loop is loop:
                        loop.create_task(res)
                    else:
                        asyncio.run_coroutine_threadsafe(res, loop)
                except RuntimeError:
                    asyncio.run_coroutine_threadsafe(res, loop)

    def _handle_status_change(self, status: TurnStatus):
        self._current_state.status = status
        self._dispatch_callback(self.on_state_change, self._current_state)

    def _handle_transcript(self, text: str, is_final: bool, is_user: bool = False):
        self._current_state.transcript = text
        self._current_state.transcript_final = is_final
        self._dispatch_callback(self.on_transcript, text, is_final, is_user)

    def _handle_metrics(self, metrics: Dict[str, Any]):
        self._current_state.metrics = metrics
        self._dispatch_callback(self.on_metrics, metrics)

    async def start(self):
        await self._turn_manager.start()
        self._current_state.status = TurnStatus.LISTENING

    async def stop(self):
        await self._turn_manager.stop()

    def interrupt(self) -> int:
        return self._turn_manager.interrupt()

    def toggle_listening(self):
        self._turn_manager.toggle_listening()

    def process_text_input(self, text: str):
        self._turn_manager.process_text_input(text)

    def get_state(self) -> Dict[str, Any]:
        return self._turn_manager.get_state()

    def get_agent_state(self) -> AgentState:
        return self._current_state


voice_agent = VoiceAgent()