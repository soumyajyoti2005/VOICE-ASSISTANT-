import uuid
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import time


@dataclass
class ConversationState:
    conversation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    turn_id: int = 0
    active_response_id: int = 0
    tool_running: bool = False
    audio_playing: bool = False

    current_turn_t0: Optional[float] = None
    current_turn_t1: Optional[float] = None
    current_turn_t2: Optional[float] = None
    current_turn_t3: Optional[float] = None
    current_turn_t4: Optional[float] = None
    current_turn_t5: Optional[float] = None

    speech_provider: str = "Rime"

    def increment_response_id(self) -> int:
        self.active_response_id += 1
        return self.active_response_id

    def next_turn(self) -> int:
        self.turn_id += 1
        self.active_response_id += 1
        self.tool_running = False
        self.audio_playing = False
        self.current_turn_t0 = time.perf_counter()
        self.current_turn_t1 = None
        self.current_turn_t2 = None
        self.current_turn_t3 = None
        self.current_turn_t4 = None
        self.current_turn_t5 = None
        return self.turn_id

    def mark_t1(self):
        self.current_turn_t1 = time.perf_counter()

    def mark_t2(self):
        self.current_turn_t2 = time.perf_counter()

    def mark_t3(self):
        self.current_turn_t3 = time.perf_counter()

    def mark_t4(self):
        self.current_turn_t4 = time.perf_counter()

    def mark_t5(self):
        self.current_turn_t5 = time.perf_counter()

    def get_latency_ms(self) -> Optional[float]:
        if self.current_turn_t0 is not None and self.current_turn_t5 is not None:
            return (self.current_turn_t5 - self.current_turn_t0) * 1000
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "turn_id": self.turn_id,
            "active_response_id": self.active_response_id,
            "tool_running": self.tool_running,
            "audio_playing": self.audio_playing,
            "latency_ms": self.get_latency_ms(),
            "speech_provider": self.speech_provider,
        }


class StateManager:
    def __init__(self):
        self._state = ConversationState()
        self._lock = False

    def reset(self):
        self._state = ConversationState()

    @property
    def state(self) -> ConversationState:
        return self._state

    def new_turn(self) -> int:
        return self._state.next_turn()

    def interrupt(self) -> int:
        new_id = self._state.increment_response_id()
        self._state.audio_playing = False
        self._state.tool_running = False
        self._state.current_turn_t5 = None
        self._state.current_turn_t0 = None
        return new_id

    def set_tool_running(self, running: bool):
        self._state.tool_running = running

    def set_audio_playing(self, playing: bool):
        self._state.audio_playing = playing

    def get_current_response_id(self) -> int:
        return self._state.active_response_id

    def is_stale(self, response_id: int) -> bool:
        return response_id != self._state.active_response_id


state_manager = StateManager()