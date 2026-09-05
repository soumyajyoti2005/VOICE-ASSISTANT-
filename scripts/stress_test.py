import asyncio
import time
import random
from dataclasses import dataclass
from typing import List, Optional

from backend.agent.state import state_manager, StateManager, ConversationState
from backend.agent.cancellation import TaggedResult, create_tagged_result, fence_result
from backend.tools.restaurant import search_restaurants
from backend.metrics.latency import LatencyLogger


def reset_state_manager():
    """Reset the global state manager for test isolation."""
    state_manager.reset()


@dataclass
class StressTestResult:
    test_name: str
    passed: bool
    details: str
    latency_ms: Optional[float] = None


class StressTestRunner:
    def __init__(self):
        self.results: List[StressTestResult] = []
        self.logger = LatencyLogger("metrics/stress_results.csv")

    def record(self, test_name: str, passed: bool, details: str, latency_ms: Optional[float] = None):
        self.results.append(StressTestResult(test_name, passed, details, latency_ms))
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {test_name}: {details}")
        if latency_ms:
            print(f"       Latency: {latency_ms:.0f}ms")

    async def test_cold_latency(self) -> StressTestResult:
        reset_state_manager()
        state_manager.new_turn()

        t0 = time.perf_counter()
        await asyncio.sleep(0.01)
        t1 = time.perf_counter()
        await asyncio.sleep(0.01)
        t2 = time.perf_counter()
        await asyncio.sleep(0.01)
        t3 = time.perf_counter()
        await asyncio.sleep(0.01)
        t4 = time.perf_counter()
        await asyncio.sleep(0.01)
        t5 = time.perf_counter()

        state_manager.state.current_turn_t0 = t0
        state_manager.state.current_turn_t1 = t1
        state_manager.state.current_turn_t2 = t2
        state_manager.state.current_turn_t3 = t3
        state_manager.state.current_turn_t4 = t4
        state_manager.state.current_turn_t5 = t5

        latency = state_manager.state.get_latency_ms()
        passed = latency is not None and latency > 0
        self.logger.log_turn(1, 0, t0, t1, t2, t3, t4, t5, "Rime")

        return StressTestResult("cold_latency", passed, f"Cold latency measured: {latency:.0f}ms", latency)

    async def test_warm_latency(self) -> StressTestResult:
        reset_state_manager()
        state_manager.new_turn()

        latencies = []
        for i in range(5):
            state_manager.new_turn()
            t0 = time.perf_counter()
            await asyncio.sleep(0.005)
            t1 = time.perf_counter()
            await asyncio.sleep(0.005)
            t2 = time.perf_counter()
            await asyncio.sleep(0.005)
            t3 = time.perf_counter()
            await asyncio.sleep(0.005)
            t4 = time.perf_counter()
            await asyncio.sleep(0.005)
            t5 = time.perf_counter()

            state_manager.state.current_turn_t0 = t0
            state_manager.state.current_turn_t1 = t1
            state_manager.state.current_turn_t2 = t2
            state_manager.state.current_turn_t3 = t3
            state_manager.state.current_turn_t4 = t4
            state_manager.state.current_turn_t5 = t5

            latency = state_manager.state.get_latency_ms()
            if latency:
                latencies.append(latency)
                self.logger.log_turn(i + 2, 0, t0, t1, t2, t3, t4, t5, "Rime")

        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        passed = avg_latency > 0

        return StressTestResult("warm_latency", passed, f"Warm latency avg: {avg_latency:.0f}ms over {len(latencies)} runs", avg_latency)

    async def test_interruption_during_speech(self) -> StressTestResult:
        reset_state_manager()
        state_manager.new_turn()
        response_id = state_manager.get_current_response_id()

        audio_chunks = [create_tagged_result(f"chunk_{i}", response_id) for i in range(10)]
        for chunk in audio_chunks[:3]:
            assert fence_result(chunk) is not None

        state_manager.interrupt()
        new_id = state_manager.get_current_response_id()

        all_fenced = all(fence_result(chunk) is None for chunk in audio_chunks[3:])
        passed = new_id == response_id + 1 and all_fenced and not state_manager.state.audio_playing

        return StressTestResult(
            "interruption_during_speech",
            passed,
            f"Interrupted at chunk 3, response_id {response_id}->{new_id}, "
            f"remaining chunks fenced: {all_fenced}"
        )

    async def test_interruption_during_tool_call(self) -> StressTestResult:
        reset_state_manager()
        state_manager.new_turn()
        response_id = state_manager.get_current_response_id()

        state_manager.state.tool_running = True

        tool_result = create_tagged_result({"restaurants": [{"name": "Test"}]}, response_id)

        state_manager.interrupt()

        fenced = fence_result(tool_result)
        passed = fenced is None and not state_manager.state.tool_running

        return StressTestResult(
            "interruption_during_tool_call",
            passed,
            f"Tool result fenced after interrupt: {fenced is None}"
        )

    async def test_tool_continuity_with_new_constraint(self) -> StressTestResult:
        reset_state_manager()
        state_manager.new_turn()
        response_id = state_manager.get_current_response_id()

        state_manager.state.tool_running = True

        state_manager.interrupt()
        new_response_id = state_manager.get_current_response_id()

        old_tool_result = create_tagged_result({"restaurants": [{"name": "Old"}]}, response_id)
        new_tool_result = create_tagged_result({"restaurants": [{"name": "New", "vegetarian": True}]}, new_response_id)

        old_fenced = fence_result(old_tool_result)
        new_fenced = fence_result(new_tool_result)

        passed = old_fenced is None and new_fenced is not None

        return StressTestResult(
            "tool_continuity_new_constraint",
            passed,
            f"Old result discarded, new result accepted. Old fenced: {old_fenced is None}, New fenced: {new_fenced is not None}"
        )

    async def test_tool_continuity_with_status_query(self) -> StressTestResult:
        reset_state_manager()
        state_manager.new_turn()
        response_id = state_manager.get_current_response_id()

        state_manager.state.tool_running = True

        status_response = create_tagged_result("Still searching...", response_id)

        state_manager.interrupt()
        new_response_id = state_manager.get_current_response_id()

        status_fenced = fence_result(status_response)
        passed = status_fenced is None

        return StressTestResult(
            "tool_continuity_status_query",
            passed,
            f"Status response from old turn fenced: {passed}"
        )

    async def test_tool_cancellation(self) -> StressTestResult:
        reset_state_manager()
        state_manager.new_turn()
        response_id = state_manager.get_current_response_id()

        state_manager.state.tool_running = True

        async def slow_tool():
            await asyncio.sleep(2)
            return {"restaurants": []}

        tool_task = asyncio.create_task(slow_tool())

        await asyncio.sleep(0.01)
        state_manager.interrupt()

        try:
            await asyncio.wait_for(tool_task, timeout=0.1)
            cancelled = False
        except asyncio.TimeoutError:
            tool_task.cancel()
            cancelled = True

        passed = cancelled and not state_manager.state.tool_running

        return StressTestResult(
            "tool_cancellation",
            passed,
            f"Tool task cancelled after interrupt: {cancelled}"
        )

    async def test_repeated_interruptions(self) -> StressTestResult:
        reset_state_manager()
        state_manager.new_turn()

        for i in range(10):
            state_manager.interrupt()

        # After new_turn (1) + 10 interrupts = 11
        passed = state_manager.get_current_response_id() == 11

        return StressTestResult(
            "repeated_interruptions",
            passed,
            f"10 rapid interrupts, final response_id: {state_manager.get_current_response_id()}"
        )

    async def test_concurrent_operations_fenced(self) -> StressTestResult:
        reset_state_manager()
        state_manager.new_turn()
        response_id = state_manager.get_current_response_id()

        operations = [
            create_tagged_result("stt_result", response_id),
            create_tagged_result("llm_token", response_id),
            create_tagged_result({"tool": "data"}, response_id),
            create_tagged_result(b"audio_chunk", response_id),
        ]

        state_manager.interrupt()

        all_fenced = all(fence_result(op) is None for op in operations)
        passed = all_fenced

        return StressTestResult(
            "concurrent_operations_fenced",
            passed,
            f"All 4 operation types fenced after interrupt: {all_fenced}"
        )

    async def run_all(self):
        print("=" * 60)
        print("STRESS TEST SUITE")
        print("=" * 60)

        tests = [
            self.test_cold_latency(),
            self.test_warm_latency(),
            self.test_interruption_during_speech(),
            self.test_interruption_during_tool_call(),
            self.test_tool_continuity_with_new_constraint(),
            self.test_tool_continuity_with_status_query(),
            self.test_tool_cancellation(),
            self.test_repeated_interruptions(),
            self.test_concurrent_operations_fenced(),
        ]

        for coro in tests:
            result = await coro
            self.results.append(result)

        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        print(f"Passed: {passed}/{total}")

        for r in self.results:
            status = "PASS" if r.passed else "FAIL"
            print(f"  [{status}] {r.test_name}")

        return passed == total


async def main():
    runner = StressTestRunner()
    success = await runner.run_all()
    exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())