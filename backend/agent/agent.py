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
    ):
        self.on_state_change = on_state_change
        self.on_transcript = on_transcript
        self.on_metrics = on_metrics

        self._turn_manager = TurnManager(
            on_status_change=self._handle_status_change,
            on_transcript=self._handle_transcript,
            on_metrics=self._handle_metrics,
        )
        self._current_state = AgentState()

    def _handle_status_change(self, status: TurnStatus):
        self._current_state.status = status
        if self.on_state_change:
            self.on_state_change(self._current_state)

    def _handle_transcript(self, text: str, is_final: bool):
        self._current_state.transcript = text
        self._current_state.transcript_final = is_final
        if self.on_transcript:
            self.on_transcript(text, is_final)

    def _handle_metrics(self, metrics: Dict[str, Any]):
        self._current_state.metrics = metrics
        if self.on_metrics:
            self.on_metrics(metrics)

    async def start(self):
        await self._turn_manager.start()
        self._current_state.status = TurnStatus.LISTENING

    async def stop(self):
        await self._turn_manager.stop()

    def interrupt(self) -> int:
        return self._turn_manager.interrupt()

    def get_state(self) -> Dict[str, Any]:
        return self._turn_manager.get_state()

    def get_agent_state(self) -> AgentState:
        return self._current_state


voice_agent = VoiceAgent()