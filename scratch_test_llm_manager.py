import asyncio
from backend.services.llm import llm_manager

async def test():
    await llm_manager.initialize()
    print("Sending text to LLM...")
    
    async def on_chunk(chunk):
        if chunk.content:
            print("Content:", chunk.content)
        if chunk.tool_calls:
            print("Tool Calls:", [tc.name for tc in chunk.tool_calls])
            
    async for chunk in llm_manager.process_turn("Can you look up Subhas Chandra Bose?", 1, on_chunk=on_chunk):
        pass

    await llm_manager.close()

if __name__ == "__main__":
    asyncio.run(test())

