# Build Prompts — Voice Assistant (Rime Hackathon)

This file has two prompts — one to give an AI coding tool (Claude Code / Cursor / etc.) for building the **frontend UI**, and one for the **backend**. The backend is 100% Python; the frontend is React only for the UI layer. Both can be copied and used independently.

---

## 1. Frontend UI Prompt (Simple, Black & Bold — ChatGPT-style)

```
Build a minimal, black-and-white voice chat interface, visually inspired by
ChatGPT's clean layout, but voice-first instead of text-first.

Design requirements:
- Pure black background (#000000 or near-black #0d0d0d), white/light-gray text.
- Bold, simple sans-serif typography (system font stack, no decorative fonts).
- Centered layout, generous whitespace, no clutter.
- One large circular mic button, center-bottom, similar position to ChatGPT's
  input bar. Button states:
    - Idle: solid white/gray circle with a mic icon
    - Listening: subtle pulsing animation (scale + glow), no bright colors —
      keep it grayscale, maybe a soft white glow
    - Speaking (assistant talking): a different subtle animation (e.g. waveform
      bars) so user can visually tell "assistant is speaking" vs "I am
      listening"
    - Processing/thinking: a simple spinner or 3-dot pulse
- A scrolling transcript area above the mic button, showing turns as simple
  text bubbles:
    - User turns: right-aligned, white text, no background fill or subtle
      dark-gray fill
    - Assistant turns: left-aligned, light-gray text
    - No avatars, no colors, no emojis — keep it text-only and monochrome
- A small, unobtrusive status label near the mic button showing one of:
  "Listening…", "Thinking…", "Speaking…", "Tap to talk"
- A small "interrupt" affordance: if the assistant is speaking, tapping the
  mic button immediately stops playback and starts listening again (visually
  reflect this instantly — no delay in the UI state change)
- A tiny settings/debug icon (top-right corner) that toggles a debug panel
  showing: active_response_id, current turn latency (T5-T0 in ms), and which
  speech provider is active (should say "Rime" during the judged flow)
- No sidebar, no chat history list, no login screen — single-screen app only
- Responsive: works on both desktop and mobile viewport widths
- Keep all styling in one file (plain CSS or Tailwind core utility classes
  only, no external UI kit)
- Do NOT use bright accent colors anywhere. Strictly black, white, and gray
  shades only, with maximum boldness in typography and button design.

Tech constraints:
- Build as a single-page React app (the project stack is: Python backend,
  React frontend — do not use plain HTML/JS, use React).
- Connect to backend via WebSocket for streaming audio in/out and for
  receiving state updates (active_response_id, turn status, latency metrics).
- Must support playing streamed audio chunks as they arrive (not waiting for
  the full response) and must support immediately stopping/clearing queued
  audio the instant an interrupt event is received from the backend.
```

---

## 2. Backend Prompt (Very Detailed — for AI coding tool)

```
Build the backend, entirely in Python, for a native, voice-first
conversational assistant (default language: English; the pipeline itself
is language-agnostic, so the STT/LLM/TTS language pack can be swapped).
Rime must be the primary text-to-speech provider for all spoken output.
The system must demonstrably handle three hard voice-engineering
problems in one integrated flow: (1) low perceived response latency,
(2) mid-turn interruption and recovery, and (3) conversation continuity
during long-running tool calls. Implement all of the following exactly.
The frontend is a separate React app (UI only) — do not build any UI code
here; expose everything the frontend needs over WebSocket.

### 1. Overall pipeline
Build an end-to-end streaming pipeline:
  audio in → STT (streaming) → LLM (streaming, tool-call capable) →
  optional tool execution (async) → Rime TTS (streaming) → audio out (playback)

The pipeline must run as a continuous full-duplex loop per conversation:
the system must keep accepting user audio input at all times, including
while Rime audio is currently playing and while a tool call is in progress.
Never block audio input while output is happening.

### 2. Core state object
Implement a shared state object per conversation, e.g.:

  state = {
      "conversation_id": str,
      "turn_id": int,
      "active_response_id": int,
      "tool_running": bool,
      "audio_playing": bool,
  }

Every asynchronous unit of work in the system — STT segment, LLM output
chunk, tool call result, Rime audio chunk — must be tagged with the
active_response_id that was current at the moment it was created.

Whenever new user speech is detected (barge-in) or the user issues a new
instruction, immediately increment active_response_id:

  state["active_response_id"] += 1

Any consumer of an async result must check, before acting on that result:

  if result.response_id != state["active_response_id"]:
      discard(result)   # never speak it, never apply it to state

This single mechanism must be the backbone of both the interruption feature
and the tool-continuity feature described below. Implement it once in a
shared module (e.g. agent/cancellation.py) and reuse it everywhere.

### 3. Feature 1 — Low perceived latency
Goal: minimize T5 - T0, where:
  T0 = timestamp when user's turn ends (speech stops)
  T1 = timestamp when STT produces the final transcript for that turn
  T2 = timestamp of LLM's first output token / tool-call decision
  T3 = timestamp when the Rime TTS request is sent
  T4 = timestamp when the first Rime audio chunk is received
  T5 = timestamp when the first audio is actually sent to playback

Implementation requirements:
- Use streaming STT, not batch/file-based transcription. Emit partial
  transcripts as they arrive; do not wait for silence-based finalization
  longer than necessary.
- Use streaming LLM output. Do not wait for the full LLM response before
  starting downstream work.
- Implement sentence-level chunking: as soon as the LLM has produced one
  complete sentence (or clause boundary), send that chunk to Rime
  immediately, while the LLM continues generating the rest in the
  background. Concatenate/queue subsequent chunks to Rime in order.
- Use Rime's streaming audio endpoint. Do not download a complete audio
  file before starting playback — start playback on the first received
  audio chunk.
- Reuse persistent connections (HTTP keep-alive / websockets) to STT, LLM,
  and Rime APIs rather than opening a new connection per request.
- Log T0 through T5 for every single turn to a metrics module
  (metrics/latency.py), writing structured rows (turn_id, T0..T5,
  T5-T0 delta, cache_status) to metrics/results.csv.
- Distinguish and separately label "cold" (first call, no warm connection/
  cache) vs "warm" (subsequent calls) latency numbers. Never mix them in a
  single reported average.
- Expose the current turn's live T5-T0 value over the WebSocket connection
  so the frontend debug panel can display it in real time.

### 4. Feature 2 — Interruption and recovery
Goal: when the user starts speaking while the assistant is talking (or
while a response is being prepared), the assistant must stop immediately
and respond only to the new instruction — with zero stale audio or stale
state leaking through.

Implementation requirements:
- Continuously run voice activity detection (VAD) or rely on the streaming
  STT's own speech-start signal on the input audio, even while
  state["audio_playing"] is true.
- The instant new user speech is detected:
  1. Increment state["active_response_id"].
  2. Send an immediate "stop playback" command to the audio output layer,
     clearing any queued/buffered Rime audio chunks that have not yet
     played.
  3. Set state["audio_playing"] = False.
  4. Begin processing the new user speech as a new turn under the new
     active_response_id.
- Any in-flight LLM call, tool call, or Rime TTS call started under the
  previous active_response_id must, upon completing, be checked against
  the current active_response_id and discarded if it no longer matches —
  do not cancel network requests forcibly if that's not feasible, but
  absolutely must not let their results reach the user or the conversation
  state.
- The conversation history/log must only record what the user actually
  heard. If Rime audio was interrupted mid-sentence, do not log the full
  unplayed text as if it was spoken — log only up to the point of
  interruption if that information is available, or mark it clearly as
  "interrupted, not fully delivered."
- Implement this as testable, isolated logic in agent/cancellation.py so
  it can be unit tested without needing live audio hardware (tests/
  test_interruption.py and tests/test_stale_result.py should be able to
  simulate response_id mismatches and assert correct discarding).

### 5. Feature 3 — Conversation continuity during tool calls
Goal: when a tool call (e.g. restaurant search) takes several seconds, the
user must be able to keep talking during that time — adding constraints,
asking for status, or cancelling — without losing context or receiving a
stale result.

Implementation requirements:
- All tool functions must be implemented as async and non-blocking, e.g.:

    async def search_restaurants(query, filters, response_id):
        await asyncio.sleep(4)  # simulated realistic delay for demo/testing
        results = ...
        return ToolResult(response_id=response_id, data=results)

- The turn manager (agent/turn_manager.py) must run tool execution as a
  background task (asyncio.create_task or equivalent) rather than awaiting
  it inline, so the main loop remains free to keep accepting and
  processing new user audio while the tool runs.
- Handle three categories of mid-tool user input:
  1. New constraint (e.g. "only vegetarian, under $20") — either
     re-parameterize and restart the tool call under the new
     active_response_id, or apply the constraint as a filter to the
     eventual tool result if the tool has not yet returned.
  2. Status query (e.g. "how much longer?") — respond with a short spoken
     status update via Rime without cancelling or restarting the tool.
  3. Cancellation (e.g. "never mind") — call task.cancel() on the running
     tool task and confirm cancellation to the user via a short spoken
     response.
- When a tool call eventually completes, check its tagged response_id
  against state["active_response_id"] using the same fencing logic as
  Feature 2 before using its result. If stale, discard silently and do not
  speak or log it.
- Ensure the tool result, once accepted, flows into the same
  LLM → Rime → playback path as any other response.

### 6. Module structure (implement exactly these files, all Python)
backend/
  main.py                  — app entrypoint, WebSocket server setup
  config.py                — loads env vars, validates required API keys present
  agent/
    agent.py               — top-level orchestrator tying STT/LLM/tools/Rime together
    state.py                — defines the state object and increment/read helpers
    turn_manager.py         — the async event loop: listens for input while
                               managing tool tasks and playback state
    cancellation.py         — the response_id fencing helper used everywhere
  services/
    rime.py                  — Rime TTS client, streaming request + chunk handling
    stt.py                   — streaming STT client (default English, language-agnostic)
    llm.py                   — LLM client, streaming + tool-call decision logic
    audio.py                 — mic capture + speaker playback, full-duplex,
                               supports immediate stop/clear
  tools/
    restaurant.py            — async restaurant search tool (simulated delay)
    search.py                 — generic async search tool
  metrics/
    latency.py                — logs T0-T5 per turn to metrics/results.csv
tests/
  test_latency.py
  test_interruption.py
  test_stale_result.py
scripts/
  stress_test.py             — automated repeatable test: fires a slow tool
                               call, injects an interruption mid-call, asserts
                               correct final behavior; also runs repeated
                               latency measurements (cold + warm)

Note: the frontend (React) lives in a separate frontend/ directory and is
out of scope for this backend prompt — it only needs the WebSocket contract
described above.

### 7. Configuration and secrets
- Read all credentials from environment variables only: RIME_API_KEY,
  STT_API_KEY, LLM_API_KEY, and PLACES_API_KEY (optional, only if
  tools/restaurant.py calls a real external search API instead of mock
  data).
- config.py must fail fast with a clear error message at startup if any
  required key is missing.
- Never log, print, or embed any API key value anywhere, including in
  error messages, debug output, or the WebSocket debug channel exposed to
  the frontend.
- Provide a .env.example with placeholder values only (never real keys).

### 8. Observability requirements
- Every turn's active speech provider (should always be "Rime" in the
  judged flow, but must be observable/loggable if a fallback provider is
  ever used) must be exposed via the WebSocket state channel so the
  frontend debug panel can display it.
- Log structured events (not just plain print statements) for: turn start,
  STT final, LLM decision, tool start/cancel/complete, Rime request/first
  chunk, playback start/stop/interrupt, and any discarded stale result
  (include the discarded response_id and the current active_response_id
  in that log line for debuggability).

### 9. What NOT to do
- Do not use Rime only for a static welcome message or final confirmation —
  Rime must generate the primary spoken output for every substantive turn.
- Do not block the async event loop with synchronous/blocking calls to
  STT, LLM, or Rime — everything in the hot path must be async.
- Do not implement interruption or tool-cancellation with naive flags only
  (e.g. a single "should_stop" boolean) — use the response_id fencing
  approach described above so multiple in-flight operations can be
  correctly invalidated independently per turn.
```
