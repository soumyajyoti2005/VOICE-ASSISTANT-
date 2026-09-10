# Voice Assistant — DataForge pathway x rime Hackathon

A state-of-the-art voice-native conversational assistant built to tackle three of the hardest voice-engineering challenges in a single, seamlessly integrated pipeline.

## 🎯 Problem Statements & Our Solutions

### 1. Perceived Response Time
**Problem Statement:** *Reduce the delay from the end of the user's turn to the first audible response. Measure the entire user path, including speech recognition, reasoning, buffering, network, synthesis, and playback. This matters in phone workflows, hands-busy tasks, mobile apps, browser overlays, and other fast exchanges.*

**Our Solution:** 
We engineered a hyper-optimized asynchronous streaming architecture. As soon as the user finishes speaking (T0), the raw PCM audio is instantly transcribed via Groq's low-latency `whisper-large-v3-turbo`. The resulting text is streamed into Google Gemini via OpenAI-compatible endpoints. The LLM streams its response token-by-token directly into the **Rime TTS API**. We configured Rime to return raw, uncompressed 24kHz PCM audio, which bypasses mp3 decoding overhead and is played back chunk-by-chunk the millisecond it arrives. This pipeline aggressively minimizes TTFT (Time-To-First-Token) and achieves incredibly low end-to-end latency ($T_5 - T_0$).

### 2. Interruption and Recovery
**Problem Statement:** *Stop queued TTS input and local playback promptly, then cancel or fence obsolete model and tool results so they cannot re-enter the conversation. Keep application state consistent with what the user actually heard. This fits full-duplex agents, coaching, simulations, games, and other interactive experiences.*

**Our Solution:** 
We implemented a robust **Response ID Fencing** mechanism. Every active operation (STT segment, LLM generation, tool execution, and Rime TTS playback chunk) is tagged with an `active_response_id`. When the Voice Activity Detector (VAD) detects user speech while the agent is talking, a barge-in event is triggered. This immediately increments the `active_response_id` globally. In-flight local playback buffers (PyAudio) and Web Audio API queues are flushed instantly. Any lagging network responses from the LLM or TTS are strictly fenced out and discarded because their IDs are now stale, ensuring zero leakage of obsolete audio or context.

### 3. Conversation Continuity During Tool Work
**Problem Statement:** *Keep the voice session responsive during lookups, actions, and long-running tasks. Let the user add constraints, request status, interrupt, or cancel without losing context. Prevent delayed results and unheard speech from being applied to the wrong conversational state. This is useful in commerce, support, booking, public services, and healthcare operations.*

**Our Solution:** 
Because of our global Response ID Fencing, tools run completely asynchronously without blocking the main event loop. If a user asks, "Find me a flight," and then interrupts 2 seconds later with "Actually, make it a morning flight," the VAD instantly captures the interruption, cancels the original tool's context lock via ID fencing, and seamlessly re-prompts the LLM with the new constraint. The application state perfectly mirrors only what the user has heard, keeping the session fluid and responsive.

---

## 🚧 Challenges Faced & Our Solutions

### Challenge 1: Severe Static & White Noise in TTS Streaming
**The Issue:** When streaming `audioFormat: pcm` directly from the Rime API into PyAudio/Web Audio, we encountered severe metallic static and white noise, despite having the correct 24kHz sample rate.  
**Our Solution:** Raw 16-bit PCM (s16le) requires exactly 2 bytes per sample. Network chunks arrive in arbitrary sizes (often odd byte lengths). If an odd number of bytes is passed to the audio hardware, the 16-bit frames shift out of alignment, catastrophically corrupting the audio data. We engineered a persistent `bytearray` buffer in the TTS streaming loop that strictly aligns data, yielding chunks to the hardware only in even 2-byte multiples. This completely eliminated the static.

### Challenge 2: Background Noise & "Phantom" VAD Barge-ins
**The Issue:** The Voice Activity Detector (VAD) was either too insensitive (ignoring quiet laptop microphones) or too sensitive (triggering on fan noise or breathing). Furthermore, Whisper often hallucinates phrases like *"Thank you."* or *"[BLANK_AUDIO]"* when fed pure silence, causing the agent to repeatedly interrupt itself.  
**Our Solution:** We decoupled raw hardware energy thresholds from logical conversation turns. The VAD threshold was drastically lowered (to `0.01`) to accommodate quiet microphones. However, before the system commits to a full conversation interruption (barge-in), it aggressively filters the STT output against known hallucination artifacts. If the transcript is a hallucination or meaningless punctuation, it is silently dropped without incrementing the `active_response_id`, preserving the ongoing LLM task.

### Challenge 3: Hardware Microphone Locks on Windows
**The Issue:** When building the sleek frontend React UI, integrating a `navigator.mediaDevices.getUserMedia` call for the visual waveform animation caused the backend PyAudio stream to suddenly read absolute silence. Chrome's AGC (Automatic Gain Control) and exclusive hardware locking were fighting with Python for microphone access.  
**Our Solution:** We isolated the frontend strictly as a presentation layer. Instead of hijacking the microphone via WebRTC, we fell back to a smooth, math-based CSS simulated sine wave animation for the UI when the microphone state is active. This cleanly sidestepped the OS-level hardware lock, allowing the robust Python backend to maintain exclusive, uninterrupted, low-latency access to the raw microphone stream.

### Challenge 4: Frequent Free-Tier Rate Limits (HTTP 429)
**The Issue:** During rapid conversational testing, the primary LLM (`gemini-3.5-flash`) frequently hit free-tier rate limits, causing the agent to hang indefinitely.  
**Our Solution:** We implemented an intelligent LLM cascade. The `StreamingLLMClient` intercepts 429 (Resource Exhausted) and 503 errors and instantly falls back to alternate models (`gemini-3.1-flash-lite`, `gemini-flash-lite-latest`) using an asynchronous generator. The user experiences a slight delay rather than a complete failure, ensuring the conversation survives temporary quotas.

---

## 🏗 Architecture

```text
audio in → STT (streaming) → LLM (streaming, tool-capable) →
optional tool execution (async) → Rime TTS (streaming) → audio out
```

### Core Mechanism: Response ID Fencing
Every async result (STT segment, LLM token, tool result, Rime audio chunk) is tagged with an `active_response_id`. On user interruption:
- `active_response_id` increments
- All in-flight results with stale IDs are discarded before reaching output
- This single mechanism powers both interruption and tool continuity

## 📂 Project Structure

```text
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
├── frontend/                   # React 18, Vite UI
│   ├── src/components/        # Modular UI (ChatArea, QueryBar, etc.)
│   └── src/hooks/             # useVoiceAssistant WebSocket integration
├── scripts/
│   └── stress_test.py         # Automated latency + interruption tests
├── metrics/
│   └── results.csv            # Latency measurements
├── .env.example
└── RIME_EVIDENCE.md
```

---

## 🚀 Quick Start

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

## 🔑 Required API Keys & Configuration

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
| `VAD_THRESHOLD` | `0.01` | Energy threshold calibrated for speech detection over ambient room noise |
| `VAD_SILENCE_DURATION` | `0.8` | Silence timeout in seconds to conclude user speech turn ($T_0$) |

---

## ⏱ Latency Metrics (T0–T5)

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

## 🧪 Running Automated Tests

Make sure your virtual environment is active and `PYTHONPATH` is set to `.`:

```bash
# 1. Run all 32 unit and integration tests:
pytest tests/ -v

# 2. Run stress test suite (latency, interruptions, tool continuity):
python scripts/stress_test.py
```

All 32 tests and 9 stress test scenarios should pass:
```text
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

## 🛠 Tech Stack

- **Backend**: Python 3.11+, FastAPI, asyncio, aiohttp, PyAudio, NumPy
- **Frontend**: React 18, Vite, Web Audio API, WebSocket
- **STT**: Groq Whisper (`whisper-large-v3-turbo`)
- **LLM**: Google Gemini (`gemini-3.5-flash`, `gemini-3.1-flash-lite`, `gemini-flash-lite-latest`)
- **TTS**: Rime (`users.rime.ai/v1/rime-tts`, model `mist`, speaker `amber`, 24kHz PCM)
- **Tools**: Async dining search with simulated 4s delay & generic web search

---

## 📄 License

MIT