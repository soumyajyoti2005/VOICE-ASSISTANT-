import asyncio
import aiohttp
import os
import io
import wave
import base64
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("LLM_API_KEY")
gemini_base_url = "https://generativelanguage.googleapis.com/v1beta/openai"

def make_test_wav():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00" * 16000)
    return buf.getvalue()

async def test_gemini_audio():
    # Test Google Gemini native endpoint: https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key=...
    wav_bytes = make_test_wav()
    b64_audio = base64.b64encode(wav_bytes).decode("utf-8")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": "Transcribe this audio exactly or say [silence] if silent."},
                    {
                        "inlineData": {
                            "mimeType": "audio/wav",
                            "data": b64_audio
                        }
                    }
                ]
            }
        ]
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            print(f"Gemini Audio Native API -> Status: {resp.status}")
            data = await resp.json()
            print(data)

asyncio.run(test_gemini_audio())
