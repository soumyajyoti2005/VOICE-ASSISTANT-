import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.agent.state import state_manager, StateManager, ConversationState
from backend.agent.cancellation import TaggedResult, fence_result, create_tagged_result
from backend.agent.turn_manager import TurnManager, TurnStatus


def reset_state_manager():
    """Reset the global state manager for test isolation."""
    state_manager.reset()


class TestInterruption:
    def setup_method(self):
        reset_state_manager()

    @pytest.mark.asyncio
    async def test_barge_in_detection_triggers_interrupt(self):
        state_manager.new_turn()
        original_id = state_manager.get_current_response_id()

        state_manager.state.audio_playing = True
        state_manager.state.tool_running = True

        new_id = state_manager.interrupt()

        assert new_id == original_id + 1
        assert state_manager.state.audio_playing is False
        assert state_manager.state.tool_running is False

    @pytest.mark.asyncio
    async def test_multiple_interrupts_increment_response_id(self):
        state_manager.new_turn()
        ids = []
        for _ in range(3):
            ids.append(state_manager.interrupt())

        assert ids == [2, 3, 4]
        assert state_manager.get_current_response_id() == 4

    @pytest.mark.asyncio
    async def test_interrupt_clears_audio_playback(self):
        state_manager.new_turn()
        state_manager.state.audio_playing = True

        state_manager.interrupt()

        assert state_manager.state.audio_playing is False

    @pytest.mark.asyncio
    async def test_interrupt_stops_tool_execution(self):
        state_manager.new_turn()
        state_manager.state.tool_running = True

        state_manager.interrupt()

        assert state_manager.state.tool_running is False

    @pytest.mark.asyncio
    async def test_conversation_history_only_actual_audio(self):
        state_manager.new_turn()
        state_manager.state.current_turn_t0 = 1000.0
        state_manager.state.current_turn_t5 = 1002.0

        state_manager.interrupt()

        assert state_manager.state.current_turn_t5 is None or state_manager.state.get_latency_ms() is None


class TestInterruptionIntegration:
    def setup_method(self):
        reset_state_manager()

    @pytest.mark.asyncio
    async def test_full_interrupt_flow(self):
        state_manager.new_turn()

        response_id = state_manager.get_current_response_id()
        result = create_tagged_result("audio chunk", response_id)

        assert fence_result(result) == "audio chunk"

        state_manager.interrupt()

        assert fence_result(result) is None
        assert state_manager.get_current_response_id() == response_id + 1