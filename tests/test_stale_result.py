import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.agent.state import state_manager, StateManager, ConversationState
from backend.agent.cancellation import (
    TaggedResult,
    fence_result,
    create_tagged_result,
    run_with_fence,
    CancellationError,
)


def reset_state_manager():
    """Reset the global state manager for test isolation."""
    state_manager.reset()


class TestStaleResultFencing:
    def setup_method(self):
        reset_state_manager()

    def test_stt_result_fenced(self):
        state_manager.new_turn()
        response_id = state_manager.get_current_response_id()

        stt_result = create_tagged_result("hello world", response_id)
        assert fence_result(stt_result) == "hello world"

        state_manager.interrupt()

        assert fence_result(stt_result) is None

    def test_llm_result_fenced(self):
        state_manager.new_turn()
        response_id = state_manager.get_current_response_id()

        llm_result = create_tagged_result("I'll help you with that", response_id)
        assert fence_result(llm_result) == "I'll help you with that"

        state_manager.new_turn()

        assert fence_result(llm_result) is None

    def test_tool_result_fenced(self):
        state_manager.new_turn()
        response_id = state_manager.get_current_response_id()

        tool_result = create_tagged_result({"restaurants": [{"name": "Test"}]}, response_id)
        assert fence_result(tool_result) is not None

        state_manager.interrupt()

        assert fence_result(tool_result) is None

    def test_rime_audio_chunk_fenced(self):
        state_manager.new_turn()
        response_id = state_manager.get_current_response_id()

        audio_chunk = create_tagged_result(b"audio_data", response_id)
        assert fence_result(audio_chunk) is not None

        state_manager.interrupt()

        assert fence_result(audio_chunk) is None

    def test_multiple_inflight_operations_fenced_independently(self):
        state_manager.new_turn()
        response_id = state_manager.get_current_response_id()

        stt_result = create_tagged_result("transcript", response_id)
        llm_result = create_tagged_result("response", response_id)
        tool_result = create_tagged_result({"data": "tool"}, response_id)
        audio_result = create_tagged_result(b"audio", response_id)

        state_manager.interrupt()

        assert fence_result(stt_result) is None
        assert fence_result(llm_result) is None
        assert fence_result(tool_result) is None
        assert fence_result(audio_result) is None

    def test_new_turn_resets_response_id(self):
        state_manager.new_turn()
        old_response_id = state_manager.get_current_response_id()

        old_result = create_tagged_result("old", old_response_id)

        state_manager.new_turn()
        new_response_id = state_manager.get_current_response_id()

        assert new_response_id == old_response_id + 1
        assert fence_result(old_result) is None

    def test_response_id_fencing_used_everywhere(self):
        state_manager.new_turn()
        response_id = state_manager.get_current_response_id()

        operations = [
            ("stt", create_tagged_result("text", response_id)),
            ("llm", create_tagged_result("reply", response_id)),
            ("tool", create_tagged_result({"result": "data"}, response_id)),
            ("rime", create_tagged_result(b"audio", response_id)),
        ]

        for name, result in operations:
            assert fence_result(result) is not None, f"{name} should pass fence initially"

        state_manager.interrupt()

        for name, result in operations:
            assert fence_result(result) is None, f"{name} should be fenced after interrupt"


class TestRunWithFence:
    @pytest.mark.asyncio
    async def test_run_with_fence_returns_result_when_valid(self):
        reset_state_manager()
        state_manager.new_turn()
        response_id = state_manager.get_current_response_id()

        async def coro():
            return "success"

        result = await run_with_fence(coro, response_id)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_run_with_fence_returns_none_when_stale(self):
        reset_state_manager()
        state_manager.new_turn()
        response_id = state_manager.get_current_response_id()

        async def coro():
            await asyncio.sleep(0.01)
            return "success"

        state_manager.interrupt()

        result = await run_with_fence(coro, response_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_on_discard_called_when_stale(self):
        reset_state_manager()
        state_manager.new_turn()
        response_id = state_manager.get_current_response_id()

        discard_called = []

        async def on_discard(old_id, new_id):
            discard_called.append((old_id, new_id))

        async def coro():
            return "success"

        state_manager.interrupt()
        await run_with_fence(coro, response_id, on_discard=on_discard)

        assert len(discard_called) == 1
        assert discard_called[0][0] == response_id
        assert discard_called[0][1] == state_manager.get_current_response_id()


class TestConversationHistory:
    def setup_method(self):
        reset_state_manager()

    def test_interrupted_audio_not_logged_as_complete(self):
        state_manager.new_turn()
        state_manager.state.current_turn_t0 = 1000.0

        state_manager.interrupt()

        assert state_manager.state.current_turn_t5 is None
        latency = state_manager.state.get_latency_ms()
        assert latency is None

    def test_only_delivered_audio_logged(self):
        state_manager.new_turn()
        state_manager.state.current_turn_t0 = 1000.0
        state_manager.state.current_turn_t5 = 1001.5

        latency = state_manager.state.get_latency_ms()
        assert latency is not None
        assert latency == 1500.0

        state_manager.new_turn()

        assert state_manager.state.get_latency_ms() is None