# Voice Assistant — Rime Hackathon

A voice-native conversational assistant demonstrating three hard voice-engineering problems in a single integrated flow:

1. **Low Perceived Latency** — Minimize time from user speech end to first audio response (T5−T0)
2. **Interruption & Recovery** — Immediate barge-in handling with zero stale audio leakage
3. **Conversation Continuity During Tool Calls** — Users can add constraints, ask status, or cancel mid-tool

## Architecture

```
audio in → STT (streaming) → LLM (streaming, tool-capable) →
optional tool execution (async) → Rime TTS (streaming) → audio out
```

### Core Mechanism: Response ID Fencing
Every async result (STT segment, LLM token, tool result, Rime audio chunk) is tagged with an `active_response_id`. On user interruption:
- `active_response_id` increments
- All in-flight results with stale IDs are discarded before reaching output
- This single mechanism powers both interruption and tool continuity

## Project Structure

```
project/
├── backend/                    # 100% Python async
│   ├── main.py                # FastAPI + WebSocket server
│   ├── config.py              # Environment config (fails fast on missing keys)
│   ├── agent/
│   │   ├── agent.py           # Top-level orchestrator
│   │   ├── state.py           # ConversationState + StateManager
│   │   ├── turn_manager.py    # Full-duplex turn loop
│   │   └── cancellation.py    # Response ID fencing logic
│   ├── services/
│   │   ├── rime.py            # Rime streaming TTS client
│   │   ├── stt.py             # Streaming STT client
│   │   ├── llm.py             # Streaming LLM + tool calls
│   │   └── audio.py           # Full-duplex PyAudio capture/playback
│   ├── tools/
│   │   ├── restaurant.py      # Async restaurant search (4s delay)
│   │   └── search.py          # Generic web search
│   └── metrics/
│       └── latency.py         # T0–T5 logging → results.csv
├── tests/
│   ├── test_latency.py
│   ├── test_interruption.py
│   └── test_stale_result.py
├── frontend/                   # React (UI only)
│   └── src/App.jsx            # ChatGPT-style voice UI
├── scripts/
│   └── stress_test.py         # Automated latency + interruption tests
├── metrics/
│   └── results.csv            # Latency measurements
├── .env.example
└── RIME_EVIDENCE.md
```

## Quick Start

### 1. Prerequisites
- **Python**: 3.11.9 (recommended)
- **Node.js**: 18+ and `npm`
- **Microphone & Speaker**: Hardware mic/speaker or browser audio support

### 2. Environment Setup
Copy `.env.example` to `.env` in the repository root:
```bash
cp .env.example .env
```
Populate your API keys in `.env`:
```ini
RIME_API_KEY=your_rime_api_key
STT_API_KEY=gsk_your_groq_api_key
LLM_API_KEY=your_gemini_api_key
```

### 3. Backend Setup & Run

Create and activate a virtual environment with Python 3.11:

**On Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Start backend with unbuffered logging
$env:PYTHONPATH="."
$env:PYTHONUNBUFFERED="1"
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

**On macOS / Linux (bash):**
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export PYTHONPATH="."
export PYTHONUNBUFFERED="1"
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

The backend server runs on `http://localhost:8000` (WebSocket endpoint at `ws://localhost:8000/ws/{client_id}`).

### 4. Frontend Setup & Run

In a separate terminal window:
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173` in your web browser.

---

## Required API Keys & Configuration

| Key / Variable | Default | Purpose / Details |
|---|---|---|
| `RIME_API_KEY` | *(Required)* | Rime TTS streaming API key |
| `STT_API_KEY` | *(Required)* | Groq API key for high-speed Whisper STT (`whisper-large-v3-turbo`) |
| `LLM_API_KEY` | *(Required)* | Google Gemini API key (accepts free tier keys; also aliases `GEMINI_API_KEY`) |
| `PLACES_API_KEY`| *(Optional)* | Google Places API key for live dining queries |
| `RIME_BASE_URL` | `https://users.rime.ai/v1` | Official Rime TTS streaming endpoint |
| `RIME_VOICE` | `amber` | Speaker voice for Mist model (`amber` validated) |
| `RIME_MODEL` | `mist` | High-quality low-latency Rime model |
| `STT_BASE_URL` | `https://api.groq.com/openai/v1` | Groq OpenAI-compatible STT endpoint |
| `STT_MODEL` | `whisper-large-v3-turbo` | Fast Whisper STT model (~200ms latency) |
| `LLM_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai/` | Google Gemini OpenAI-compatible endpoint |
| `LLM_MODEL` | `gemini-3.5-flash` | Active model with auto-fallback (`gemini-3.1-flash-lite`, `gemini-flash-lite-latest`) |
| `VAD_THRESHOLD` | `0.06` | Energy threshold calibrated for speech detection over ambient room noise |
| `VAD_SILENCE_DURATION` | `0.8` | Silence timeout in seconds to conclude user speech turn ($T_0$) |

---

## Latency Metrics (T0–T5)

| Marker | Definition |
|---|---|
| **T0** | User turn end (speech stops or enter pressed) |
| **T1** | STT final transcript ready |
| **T2** | LLM first token / tool decision |
| **T3** | Rime TTS request sent |
| **T4** | First Rime audio chunk received |
| **T5** | First audio chunk delivered/played to user |

**Primary metric: $T_5 - T_0$** (user-perceived response time).
Results are automatically logged to `metrics/results.csv` with cold and warm turn differentiation.

---

## Key Features & Architecture

1. **Low Perceived Latency ($T_5 - T_0$)**:
   - Audio is streamed chunk-by-chunk directly as generated (PCM 24kHz).
   - TTFT is kept minimal via Groq Whisper and Gemini Flash Lite streaming.
2. **Immediate Interruption / Barge-in**:
   - When the user starts speaking while audio is playing or a tool is running, `TurnManager.interrupt()` increments `active_response_id`.
   - In-flight audio playback is instantly killed on both local hardware (PyAudio) and the browser (Web Audio API), discarding any stale response chunks.
3. **Resilient LLM Multi-Model Fallback**:
   - Google Gemini free tier rate limits (429) and demand spikes (503) trigger automatic exponential backoff retry and dynamic fallback to high-throughput companion models (`gemini-3.1-flash-lite`, `gemini-flash-lite-latest`).
4. **VAD Calibration & Whisper Hallucination Filtering**:
   - Background room noise is isolated with an energy threshold of `0.06` and mean energy check (`0.04`).
   - Common Whisper silence hallucinations (`"Thank you."`, `"Mm-hmm."`) are automatically filtered out to prevent false turn interruptions.
5. **Conversation Continuity During Slow Tools**:
   - During long-running tasks (like a simulated 4s restaurant query), users can ask status updates or modify constraints without breaking dialogue flow.

---

## Running Automated Tests

Make sure your virtual environment is active and `PYTHONPATH` is set to `.`:

```bash
# 1. Run all 32 unit and integration tests:
pytest tests/ -v

# 2. Run stress test suite (latency, interruptions, tool continuity):
python scripts/stress_test.py
```

All 32 tests and 9 stress test scenarios should pass:
```
[PASS] cold_latency
[PASS] warm_latency
[PASS] interruption_during_speech
[PASS] interruption_during_tool_call
[PASS] tool_continuity_new_constraint
[PASS] tool_continuity_status_query
[PASS] tool_cancellation
[PASS] repeated_interruptions
[PASS] concurrent_operations_fenced
```

---

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, asyncio, aiohttp, PyAudio, NumPy
- **Frontend**: React 18, Vite, Web Audio API, WebSocket
- **STT**: Groq Whisper (`whisper-large-v3-turbo`)
- **LLM**: Google Gemini (`gemini-3.5-flash`, `gemini-3.1-flash-lite`, `gemini-flash-lite-latest`)
- **TTS**: Rime (`users.rime.ai/v1/rime-tts`, model `mist`, speaker `amber`, 24kHz PCM)
- **Tools**: Async dining search with simulated 4s delay & generic web search

---

## License

MIT