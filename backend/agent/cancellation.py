from dataclasses import dataclass
from typing import Generic, TypeVar, Optional, Callable, Awaitable, Any
import asyncio
import time

from .state import state_manager


T = TypeVar("T")


@dataclass
class TaggedResult(Generic[T]):
    response_id: int
    data: T
    timestamp: float


class CancellationError(Exception):
    def __init__(self, response_id: int, current_id: int):
        self.response_id = response_id
        self.current_id = current_id
        super().__init__(f"Stale result discarded: response_id={response_id}, current_id={current_id}")


def check_response_id(response_id: int, current_id: Optional[int] = None) -> bool:
    if current_id is None:
        current_id = state_manager.get_current_response_id()
    return response_id == current_id


def fence_result(result: Any, current_id: Optional[int] = None) -> Optional[Any]:
    if result is None or not hasattr(result, "response_id"):
        return None
    if check_response_id(result.response_id, current_id):
        if hasattr(result, "data"):
            return result.data
        return result
    return None


async def run_with_fence(
    coro: Callable[[], Awaitable[T]],
    response_id: int,
    on_discard: Optional[Callable[[int, int], Awaitable[None]]] = None,
) -> Optional[T]:
    result = await coro()
    tagged = TaggedResult(response_id=response_id, data=result, timestamp=time.time())
    fenced = fence_result(tagged)
    if fenced is None and on_discard:
        await on_discard(response_id, state_manager.get_current_response_id())
    return fenced


def create_tagged_result(data: T, response_id: Optional[int] = None) -> TaggedResult[T]:
    if response_id is None:
        response_id = state_manager.get_current_response_id()
    return TaggedResult(response_id=response_id, data=data, timestamp=time.time())