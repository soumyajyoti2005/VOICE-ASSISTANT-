import asyncio
from backend.services.llm import llm_manager

async def main():
    await llm_manager.initialize()
    llm_manager.add_user_message("Give me the first paragraph of Mahatma Gandhi Wikipedia page")
    print("User: Give me the first paragraph of Mahatma Gandhi Wikipedia page")
    async for chunk in llm_manager._client.stream_completion(llm_manager.get_messages(), 1):
        if chunk.tool_calls:
            print("Tool call:", chunk.tool_calls)
        if chunk.content:
            print("Content:", chunk.content)

    print("\n---")
    llm_manager.add_user_message("Give me the next paragraph as well.")
    print("User: Give me the next paragraph as well.")
    async for chunk in llm_manager._client.stream_completion(llm_manager.get_messages(), 2):
        if chunk.tool_calls:
            print("Tool call:", chunk.tool_calls)
        if chunk.content:
            print("Content:", chunk.content)

asyncio.run(main())

