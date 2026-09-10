import aiohttp
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def test():
    async with aiohttp.ClientSession() as s:
        payload = {
            'text': 'Test',
            'speaker': 'amber',
            'modelId': 'mist',
            'samplingRate': 24000,
            'audioFormat': 'pcm'
        }
        headers = {
            'Authorization': 'Bearer ' + os.getenv('RIME_API_KEY'),
            'Accept': 'audio/pcm'
        }
        async with s.post('https://users.rime.ai/v1/rime-tts', headers=headers, json=payload) as r:
            print(r.status)
            if r.status == 200:
                print(dict(r.headers))
            else:
                print(await r.text())

asyncio.run(test())

