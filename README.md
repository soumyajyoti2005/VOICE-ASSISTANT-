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

### Backend
```bash
cd backend
cp ../.env.example .env
# Edit .env with your API keys
pip install -r requirements.txt
python main.py
```
Server runs on `http://localhost:8000` (WebSocket at `ws://localhost:8000/ws/{client_id}`)

### Frontend
```bash
cd frontend
npm install
npm run dev
```
UI runs on `http://localhost:5173`

## Required API Keys

| Key | Purpose |
|-----|---------|
| `RIME_API_KEY` | Primary TTS (mandatory) |
| `STT_API_KEY` | Streaming STT (OpenAI Whisper) |
| `LLM_API_KEY` | LLM decisions (GPT-4o-mini) |
| `PLACES_API_KEY` | Optional real restaurant search |

## Latency Metrics (T0–T5)

| Marker | Definition |
|--------|------------|
| T0 | User turn end (speech stops) |
| T1 | STT final transcript ready |
| T2 | LLM first token / tool decision |
| T3 | Rime TTS request sent |
| T4 | First Rime audio chunk received |
| T5 | First audio played to user |

**Primary metric: T5 − T0** (user-perceived response time)

Results logged to `metrics/results.csv` with cold/warm separation.

## Features Demonstrated

### Interruption Test
```
User: "Find me a good restaurant"
Assistant: [starts speaking results...]
User: (interrupts) "Actually only vegetarian under $20"
Assistant: [stops immediately, searches with new constraint]
```

### Tool Continuity Test
```
User: "Find restaurants"
Assistant: [tool starts, 4s delay]
User: (during tool) "How much longer?"
Assistant: "Still searching..." [tool continues]
User: "Only vegan"
Assistant: [tool restarts with vegan filter]
```

## Running Tests

```bash
# Backend tests
cd backend
python -m pytest tests/ -v

# Stress test (latency + interruption + tool continuity)
python scripts/stress_test.py
```

## Evidence

See `RIME_EVIDENCE.md` for:
- Latency measurements (cold/warm)
- Interruption behavior logs
- Tool continuity demonstration
- Recordings/screenshots

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, asyncio, aiohttp, PyAudio
- **Frontend**: React 18, Vite, WebSocket
- **STT**: OpenAI Whisper (streaming)
- **LLM**: GPT-4o-mini (streaming, tool calling)
- **TTS**: Rime (streaming, primary provider)
- **Tools**: Mock restaurant search (4s simulated delay)

## License

MIT