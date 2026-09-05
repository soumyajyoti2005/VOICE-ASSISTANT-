import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agent.state import state_manager, StateManager, ConversationState
from backend.agent.cancellation import TaggedResult, check_response_id, fence_result, create_tagged_result
from backend.metrics.latency import LatencyLogger, LatencyRecord


def reset_state_manager():
    """Reset the global state manager for test isolation."""
    state_manager.reset()


class TestStateManager:
    def test_initial_state(self):
        state = ConversationState()
        assert state.turn_id == 0
        assert state.active_response_id == 0
        assert state.tool_running is False
        assert state.audio_playing is False

    def test_increment_response_id(self):
        state = ConversationState()
        assert state.increment_response_id() == 1
        assert state.increment_response_id() == 2
        assert state.active_response_id == 2

    def test_next_turn(self):
        state = ConversationState()
        state.active_response_id = 5
        state.tool_running = True
        state.audio_playing = True

        new_turn = state.next_turn()

        assert new_turn == 1
        assert state.turn_id == 1
        assert state.active_response_id == 6
        assert state.tool_running is False
        assert state.audio_playing is False
        assert state.current_turn_t0 is not None

    def test_latency_calculation(self):
        state = ConversationState()
        state.current_turn_t0 = time.perf_counter()
        time.sleep(0.01)
        state.current_turn_t5 = time.perf_counter()

        latency = state.get_latency_ms()
        assert latency is not None
        assert latency > 5
        assert latency < 50


class TestCancellation:
    def setup_method(self):
        reset_state_manager()

    def test_check_response_id_match(self):
        assert check_response_id(5, 5) is True

    def test_check_response_id_mismatch(self):
        assert check_response_id(5, 6) is False

    def test_fence_result_match(self):
        result = TaggedResult(response_id=5, data="hello", timestamp=time.time())
        assert fence_result(result, 5) == "hello"

    def test_fence_result_mismatch(self):
        result = TaggedResult(response_id=5, data="hello", timestamp=time.time())
        assert fence_result(result, 6) is None

    def test_create_tagged_result(self):
        reset_state_manager()
        state_manager.new_turn()
        response_id = state_manager.get_current_response_id()
        result = create_tagged_result("test", response_id)
        assert result.response_id == response_id
        assert result.data == "test"


class TestLatencyLogger:
    def test_log_turn(self, tmp_path):
        log_file = tmp_path / "test_latency.csv"
        logger = LatencyLogger(str(log_file))

        logger.log_turn(
            turn_id=1,
            response_id=1,
            t0=1000.0,
            t1=1000.1,
            t2=1000.2,
            t3=1000.3,
            t4=1000.4,
            t5=1000.5,
            speech_provider="Rime",
        )

        records = logger.get_recent_records()
        assert len(records) == 1
        assert records[0]['turn_id'] == '1'
        assert records[0]['cache_status'] == 'cold'

    def test_warm_cold_separation(self, tmp_path):
        log_file = tmp_path / "test_latency.csv"
        logger = LatencyLogger(str(log_file))

        logger.log_turn(1, 1, 1000.0, 1000.1, 1000.2, 1000.3, 1000.4, 1000.5, "Rime")
        logger.log_turn(2, 2, 2000.0, 2000.1, 2000.2, 2000.3, 2000.4, 2000.5, "Rime")

        records = logger.get_recent_records()
        assert records[0]['cache_status'] == 'cold'
        assert records[1]['cache_status'] == 'warm'


class TestInterruptionLogic:
    def setup_method(self):
        reset_state_manager()

    @pytest.mark.asyncio
    async def test_interrupt_increments_response_id(self):
        state_manager.new_turn()
        original_id = state_manager.get_current_response_id()

        new_id = state_manager.interrupt()

        assert new_id == original_id + 1
        assert state_manager.get_current_response_id() == new_id
        assert state_manager.state.audio_playing is False

    @pytest.mark.asyncio
    async def test_stale_result_discarded_after_interrupt(self):
        state_manager.new_turn()
        response_id = state_manager.get_current_response_id()

        result = create_tagged_result("old result", response_id)

        state_manager.interrupt()

        fenced = fence_result(result)
        assert fenced is None


class TestToolContinuity:
    def setup_method(self):
        reset_state_manager()

    @pytest.mark.asyncio
    async def test_tool_result_fenced_after_new_turn(self):
        state_manager.new_turn()
        response_id = state_manager.get_current_response_id()

        tool_result = create_tagged_result({"restaurants": []}, response_id)

        state_manager.new_turn()

        fenced = fence_result(tool_result)
        assert fenced is None