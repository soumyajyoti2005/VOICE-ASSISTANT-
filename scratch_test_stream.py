import aiohttp
import asyncio
import os
import json
from dotenv import load_dotenv

load_dotenv()

async def test():
    async with aiohttp.ClientSession() as s:
        payload = {
            'model': 'gemini-3.5-flash',
            'messages': [{'role': 'user', 'content': 'Can you look up Subhas Chandra Bose?'}],
            'stream': True
        }
        headers = {'Authorization': 'Bearer ' + os.environ.get('LLM_API_KEY')}
        print("Sending request...")
        async with s.post('https://generativelanguage.googleapis.com/v1beta/openai/chat/completions', headers=headers, json=payload) as r:
            print(r.status)
            async for line in r.content:
                print(line)

asyncio.run(test())

