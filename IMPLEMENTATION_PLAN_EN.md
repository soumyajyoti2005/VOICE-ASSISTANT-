# Implementation Plan — Voice Assistant (Rime Hackathon)

## 0. Project Summary

A voice-native assistant where Rime TTS acts as the primary spoken output. Three core features will be demonstrated together in a single conversational flow:

1. **Low Perceived Latency** — minimize the time from when the user stops speaking to when they hear the first audio response
2. **Interruption & Recovery** — if the user interrupts mid-turn and says something new, the system reacts immediately
3. **Conversation Continuity During Tool Calls** — while a long-running action (e.g. restaurant search) is in progress, the user can still add constraints, ask for status, or cancel

**Stack:** Backend is fully implemented in Python (async, streaming). Frontend/UI is React only. The assistant is a general native voice agent — default language is English, and the pipeline is language-agnostic (any STT/LLM/TTS language pack can be swapped in).

---

## 1. System Architecture / Flow

```
┌────────────────────────────────────────────────────────────────┐
│                         USER (voice, mic)                       │
└───────────────────────────┬──────────────────────────────────────┘
                             │ streaming audio in
                             ▼
                    ┌──────────────────┐
                    │   audio.py        │  full-duplex: capture + playback
                    │  (mic + speaker)  │  both active simultaneously
                    └────────┬───────────┘
                             ▼
                    ┌──────────────────┐
                    │   stt.py          │  streaming STT (default: English)
                    │                  │  emits partial + final transcripts
                    └────────┬───────────┘
                             │ transcript (T1)
                             ▼
                    ┌──────────────────┐
                    │  turn_manager.py  │  owns conversation loop,
                    │  + state.py       │  turn_id, active_response_id
                    └────────┬───────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │   llm.py          │  streaming decision:
                    │                  │  direct reply OR tool call (T2)
                    └───────┬──────────┘
                     ┌──────┴───────┐
                     ▼              ▼
           ┌──────────────┐  ┌─────────────────┐
           │ tools/        │  │ direct response  │
           │ restaurant.py │  │ (no tool needed) │
           │ search.py     │  └────────┬─────────┘
           └──────┬────────┘           │
                  │ async, cancellable │
                  │ tagged with        │
                  │ response_id        │
                  └─────────┬──────────┘
                            ▼
                  ┌──────────────────┐
                  │  cancellation.py  │  fences stale results:
                  │                  │  if result.response_id !=
                  │                  │  state.active_response_id →
                  │                  │  discard(result)
                  └────────┬───────────┘
                           │ confirmed, current text
                           ▼
                  ┌──────────────────┐
                  │   rime.py         │  Rime streaming TTS call (T3)
                  └────────┬───────────┘
                           │ audio chunks (T4)
                           ▼
                  ┌──────────────────┐
                  │   audio.py        │  playback starts (T5),
                  │  (playback)       │  interruptible mid-stream
                  └────────┬───────────┘
                           ▼
                       USER hears
                           ▲
                           │ user interrupts anytime →
                           │ new speech re-enters STT →
                           │ turn_manager increments active_response_id →
                           │ old playback stopped, old results fenced
                           └──────────────────────────────

     ┌───────────────────────────────┐
     │  metrics/latency.py            │  logs T0–T5 per turn → results.csv
     │  scripts/stress_test.py        │  automated interruption + tool-delay test
     └───────────────────────────────┘
```

### Timestamp definitions (used for evidence/metrics)
| Marker | Meaning |
|---|---|
| T0 | user turn end (speech stops) |
| T1 | STT final transcript ready |
| T2 | LLM decision / first token |
| T3 | Rime TTS request sent |
| T4 | first Rime audio chunk received |
| T5 | first audio actually played to user |

**Primary metric = T5 − T0** (this is what the user actually perceives as "response time")

### Core state object (shared across all 3 features)
```python
state = {
    "conversation_id": "abc",
    "turn_id": 12,
    "active_response_id": 25,
    "tool_running": True,
    "audio_playing": True
}
```
Every async result (STT segment, LLM output, tool result, Rime audio chunk) is tagged with the `response_id` it was generated under. This single mechanism is what powers Feature 2 and Feature 3 below.

---

## 2. Feature 1 — Low Perceived Latency (Response Time)

**Goal:** minimize T5 − T0 as much as possible — not by optimizing a single number, but by cutting delay at every stage of the pipeline.

### Implementation Steps
1. **Use streaming STT**, not batch/file-upload mode. Partial transcripts should arrive while the user is still speaking; there's no need to wait for the entire sentence to finish. This reduces T0→T1.
2. **Stream LLM output** — start processing as soon as the first token arrives, rather than waiting for the full response to complete. This reduces T1→T2.
3. **Sentence-level chunking** — even if the LLM output isn't fully complete, as soon as the first full sentence is available, send it to Rime immediately while the rest continues generating in the background.
4. **Use Rime's streaming audio endpoint** (not downloading the full audio file before playing) — start playback the moment the first audio chunk arrives. This reduces T3→T4→T5.
5. **Warm connections / connection pooling** — keep persistent connections open to the Rime, STT, and LLM APIs instead of doing a fresh handshake on every request.
6. **Latency logging** (`metrics/latency.py`) — log T0–T5 for every turn and save to `results.csv`.
7. **Report cached vs uncached separately** — this is mandatory per the hackathon rules; unverified/mixed numbers receive no credit.

### Evidence / Acceptance Test
- `scripts/stress_test.py` — run the same query repeatedly (both cold and warm) and measure T0–T5, recording results into `results.csv`.
- The README must state the exact model/endpoint/audio format/transport used in the demo.

---

## 3. Feature 2 — Interruption & Recovery

**Goal:** if the user interrupts either while speaking or while TTS is playing and says something new, the old audio/response is immediately cancelled and the system reacts to the new instruction.

### Implementation Steps
1. **Full-duplex audio pipeline** — `audio.py` must always be listening to the mic input, even while Rime audio is playing. A one-way (playback-only) pipeline is not acceptable.
2. **Barge-in detection** — detect new user speech (via VAD / STT partial trigger) and signal `turn_manager` immediately.
3. **Increment response_id** (`state.py`):
   ```python
   state["active_response_id"] += 1
   ```
   This single line invalidates everything that was previously in flight.
4. **Immediate playback stop** — when new speech is detected, signal `audio.py` to instantly clear the queued audio buffer and stop playback.
5. **Result fencing** (`cancellation.py`):
   ```python
   if result.response_id != state["active_response_id"]:
       discard(result)
   ```
   No STT/LLM/tool/audio result carrying an old `response_id` should be spoken to the user or applied to application state.
6. **State consistency** — the conversation history/log must only reflect what the user *actually heard* — the text of mid-sentence, interrupted audio should not be logged in full as if it was spoken completely.

### Evidence / Acceptance Test
- Start a tool call with a fixed delay, then deliberately interrupt while Rime is speaking or the tool is running, giving a new constraint (example: "find me a good restaurant" → mid-way, "actually, only vegetarian, under $20").
- Verify:
  - Old audio stopped immediately
  - The new instruction reached the system
  - The old tool result was not spoken incorrectly
  - The final response reflected the new constraint
- Add procedure + result + recording/log to `RIME_EVIDENCE.md`.

---

## 4. Feature 3 — Conversation Continuity During Tool Calls

**Goal:** while a tool (e.g. restaurant search) takes time to run, the user can still add a new constraint, ask for status, or cancel entirely — without anything being lost.

### Implementation Steps
1. **Async, non-blocking tool calls**:
   ```python
   async def search_restaurants(...):
       await asyncio.sleep(4)   # simulated slow tool
       return results
   ```
2. **Parallel event loop in `turn_manager.py`** — waiting for the tool result and listening for new user input run simultaneously (`asyncio.gather` / separate tasks).
3. **Handle three types of mid-tool interrupts:**
   - **New constraint** → restart/re-parameterize the running tool call, or filter the existing result
   - **Status query** ("how much longer?") → give a spoken intermediate response without stopping the tool
   - **Full cancellation** → stop the running tool with `asyncio.Task.cancel()`
4. **Stale tool-result protection** — reuse the same `response_id` fencing mechanism from Feature 2 — if the user says something new before the tool result comes back, that stale result is silently discarded.

### Evidence / Acceptance Test
- In the normal flow, the tool takes 4 seconds — during that window, the user gives a new constraint/status query/cancellation.
- Save the system's reaction as a log/recording, and add proof to `RIME_EVIDENCE.md` that the final result matched the user's latest intent.

---

## 5. Repo Structure

```
project/
├── backend/                    # 100% Python
│   ├── main.py
│   ├── config.py
│   ├── agent/
│   │   ├── agent.py
│   │   ├── state.py
│   │   ├── turn_manager.py
│   │   └── cancellation.py
│   ├── services/
│   │   ├── rime.py
│   │   ├── stt.py
│   │   ├── llm.py
│   │   └── audio.py
│   ├── tools/
│   │   ├── restaurant.py
│   │   └── search.py
│   └── metrics/
│       └── latency.py
├── tests/
│   ├── test_latency.py
│   ├── test_interruption.py
│   └── test_stale_result.py
├── frontend/                    # React only (UI layer)
├── scripts/
│   └── stress_test.py
├── metrics/
│   └── results.csv
├── .env.example
├── .gitignore
├── README.md
└── RIME_EVIDENCE.md
```

---

## 6. API Keys Needed

| Key | Purpose | Used in |
|---|---|---|
| `RIME_API_KEY` | Text-to-speech (primary spoken output — mandatory) | `services/rime.py` |
| `STT_API_KEY` | Speech-to-text (default English; language-agnostic) | `services/stt.py` |
| `LLM_API_KEY` | Decision-making / response generation | `services/llm.py` |
| `PLACES_API_KEY` (optional) | Only if `restaurant.py` uses a real search API | `tools/restaurant.py` |

`.env.example`:
```
RIME_API_KEY=your_key_here
STT_API_KEY=your_key_here
LLM_API_KEY=your_key_here
PLACES_API_KEY=your_key_here
```

**Rule:** all keys must be kept as server-side secrets — never committed to client code, screenshots, recordings, or the README.

---

## 7. Build Order (what to do first)

1. **Milestone 1** — get just `Python text → Rime API → audio stream/file → playback` working. Only `RIME_API_KEY` is needed.
2. **Milestone 2** — add STT + LLM to complete the basic voice loop (speaking → listening).
3. **Milestone 3** — set up `state.py` + the `response_id` mechanism, then test the interruption feature (Feature 2).
4. **Milestone 4** — add an async tool call (`restaurant.py`) and test Feature 3 (continuity).
5. **Milestone 5** — add Feature 1 (latency) measurement via `metrics/latency.py`, populate `results.csv`.
6. **Milestone 6** — write `RIME_EVIDENCE.md`, `README.md`, `.env.example` and make the repo submission-ready.

---

## 8. Demo Script (4–5 minutes)

| Time | Content |
|---|---|
| 0:00–0:30 | Problem statement — what goes wrong with interruption in a normal chatbot |
| 0:30–1:20 | User + problem introduction |
| 1:20–2:00 | Working product + Rime's role |
| 2:00–3:00 | Interruption/continuity stress case (live) |
| 3:00–3:40 | Result + measurement (latency numbers) |
| 3:40–4:20 | Evidence + reproducibility (show the repeatable script) |
| 4:20–4:50 | Limitations, active provider confirmation, wrap-up |
