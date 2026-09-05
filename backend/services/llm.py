import asyncio
import aiohttp
import json
from typing import AsyncGenerator, Optional, List, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum

from backend.config import config
from backend.agent.state import state_manager
from backend.agent.cancellation import create_tagged_result, fence_result
from backend.tools.restaurant import search_restaurants
from backend.tools.search import web_search


class ToolCallStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class ToolCall:
    name: str
    arguments: Dict[str, Any]
    call_id: str
    status: ToolCallStatus = ToolCallStatus.PENDING
    result: Optional[Any] = None
    response_id: int = 0


@dataclass
class LLMChunk:
    content: str
    is_final: bool
    tool_calls: Optional[List[ToolCall]] = None
    response_id: int = 0


class StreamingLLMClient:
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._base_url = config.llm_base_url
        self._api_key = config.llm_api_key
        self._model = config.llm_model
        self._temperature = config.llm_temperature

        self._tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_restaurants",
                    "description": "Search for restaurants with filters",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "cuisine": {"type": "string", "description": "Cuisine type filter"},
                            "price_max": {"type": "number", "description": "Maximum price"},
                            "dietary": {"type": "string", "description": "Dietary restrictions"},
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web for information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                        },
                        "required": ["query"],
                    },
                },
            },
        ]

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=120),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()
            self._session = None

    async def stream_completion(
        self,
        messages: List[Dict[str, str]],
        response_id: int,
        on_chunk: Optional[Callable[[LLMChunk], None]] = None,
    ) -> AsyncGenerator[LLMChunk, None]:
        if not self._session:
            raise RuntimeError("LLMClient not initialized")

        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
            "stream": True,
            "tools": self._tools,
            "tool_choice": "auto",
        }

        buffer = ""
        tool_calls_buffer: Dict[int, Dict] = {}

        async with self._session.post(f"{self._base_url}/chat/completions", json=payload) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise RuntimeError(f"LLM error: {resp.status} - {error_text}")

            async for line in resp.content:
                line = line.decode("utf-8").strip()
                if not line or line == "data: [DONE]":
                    continue
                if line.startswith("data: "):
                    line = line[6:]

                try:
                    data = json.loads(line)
                    choices = data.get("choices", [])
                    if not choices:
                        continue

                    delta = choices[0].get("delta", {})
                    finish_reason = choices[0].get("finish_reason")

                    content = delta.get("content", "")
                    tool_calls = delta.get("tool_calls")

                    if tool_calls:
                        for tc in tool_calls:
                            index = tc.get("index", 0)
                            if index not in tool_calls_buffer:
                                tool_calls_buffer[index] = {"id": "", "name": "", "arguments": ""}
                            if tc.get("id"):
                                tool_calls_buffer[index]["id"] = tc["id"]
                            if tc.get("function", {}).get("name"):
                                tool_calls_buffer[index]["name"] = tc["function"]["name"]
                            if tc.get("function", {}).get("arguments"):
                                tool_calls_buffer[index]["arguments"] += tc["function"]["arguments"]

                    if content:
                        buffer += content
                        chunk = LLMChunk(
                            content=content,
                            is_final=False,
                            response_id=response_id,
                        )
                        if on_chunk:
                            on_chunk(chunk)
                        yield chunk

                    if finish_reason == "tool_calls" and tool_calls_buffer:
                        tool_call_list = []
                        for idx, tc_data in tool_calls_buffer.items():
                            try:
                                args = json.loads(tc_data["arguments"])
                            except json.JSONDecodeError:
                                args = {}
                            tool_call = ToolCall(
                                name=tc_data["name"],
                                arguments=args,
                                call_id=tc_data["id"],
                                response_id=response_id,
                            )
                            tool_call_list.append(tool_call)

                        chunk = LLMChunk(
                            content="",
                            is_final=True,
                            tool_calls=tool_call_list,
                            response_id=response_id,
                        )
                        if on_chunk:
                            on_chunk(chunk)
                        yield chunk
                        break

                    if finish_reason == "stop" and buffer:
                        chunk = LLMChunk(
                            content="",
                            is_final=True,
                            response_id=response_id,
                        )
                        if on_chunk:
                            on_chunk(chunk)
                        yield chunk
                        break

                except json.JSONDecodeError:
                    continue


class LLMManager:
    def __init__(self):
        self._client: Optional[StreamingLLMClient] = None
        self._conversation_history: List[Dict[str, str]] = []

    async def initialize(self):
        self._client = StreamingLLMClient()
        await self._client.__aenter__()

    async def close(self):
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None

    def add_user_message(self, content: str):
        self._conversation_history.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str):
        self._conversation_history.append({"role": "assistant", "content": content})

    def add_tool_result(self, call_id: str, result: Any):
        self._conversation_history.append({
            "role": "tool",
            "tool_call_id": call_id,
            "content": json.dumps(result) if not isinstance(result, str) else result,
        })

    def get_messages(self) -> List[Dict[str, str]]:
        system_prompt = {
            "role": "system",
            "content": (
                "You are a helpful voice assistant. Keep responses concise and natural for speech. "
                "Use the search_restaurants tool for food/dining queries. Use web_search for general queries. "
                "When a tool is running, you can provide status updates without calling tools."
            ),
        }
        return [system_prompt] + self._conversation_history

    async def process_turn(
        self,
        user_text: str,
        response_id: int,
        on_chunk: Optional[Callable[[LLMChunk], None]] = None,
    ) -> AsyncGenerator[LLMChunk, None]:
        self.add_user_message(user_text)
        messages = self.get_messages()

        full_response = ""
        tool_calls = []

        async for chunk in self._client.stream_completion(messages, response_id, on_chunk):
            fenced = fence_result(chunk)
            if fenced is None:
                return
            full_response += chunk.content
            if chunk.tool_calls:
                tool_calls = chunk.tool_calls
            yield fenced

        if full_response:
            self.add_assistant_message(full_response)

        for tool_call in tool_calls:
            tool_call.status = ToolCallStatus.RUNNING
            try:
                if tool_call.name == "search_restaurants":
                    result = await search_restaurants(
                        tool_call.arguments.get("query", ""),
                        tool_call.arguments.get("cuisine"),
                        tool_call.arguments.get("price_max"),
                        tool_call.arguments.get("dietary"),
                        response_id=tool_call.response_id,
                    )
                elif tool_call.name == "web_search":
                    result = await web_search(
                        tool_call.arguments.get("query", ""),
                        response_id=tool_call.response_id,
                    )
                else:
                    result = {"error": f"Unknown tool: {tool_call.name}"}

                tool_call.result = result
                tool_call.status = ToolCallStatus.COMPLETED
                self.add_tool_result(tool_call.call_id, result)

            except asyncio.CancelledError:
                tool_call.status = ToolCallStatus.CANCELLED
                raise
            except Exception as e:
                tool_call.status = ToolCallStatus.FAILED
                tool_call.result = {"error": str(e)}
                self.add_tool_result(tool_call.call_id, {"error": str(e)})


llm_manager = LLMManager()