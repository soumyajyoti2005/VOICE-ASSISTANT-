import { useCallback, useEffect, useRef, useState } from 'react'

const WS_BASE = 'ws://localhost:8000/ws'
const AUDIO_SAMPLE_RATE = 24000
const RECONNECT_DELAY_MS = 2000
const COALESCE_WINDOW_MS = 1400

/* Generated once per page load (module scope) — stable across re-renders. */
const CLIENT_ID = `client-${Math.random().toString(36).slice(2, 9)}`

const roleOf = (isUser) => (isUser ? 'user' : 'assistant')

let messageSeq = 0
const nextMessageId = () => `msg-${++messageSeq}-${Date.now().toString(36)}`

/**
 * Owns the WebSocket connection to the backend voice pipeline, browser-side
 * playback of streamed TTS audio (raw PCM s16le @ 24kHz), the transcript
 * feed, latency metrics and barge-in interrupt handling.
 *
 * Backend contract (unchanged):
 *   out : {type:'toggle_listening'} | {type:'interrupt'} | {type:'prompt', text}
 *         | {type:'get_state'} | {type:'ping'}
 *   in  : {type:'connected'|'state'|'transcript'|'metrics'|'interrupted'|'pong', ...}
 *         + binary PCM chunks played through the AudioContext.
 */
export function useVoiceAssistant() {
  const [messages, setMessages] = useState([])
  const [rawStatus, setRawStatus] = useState('idle')
  const [connection, setConnection] = useState('connecting')
  const [isAudioPlaying, setIsAudioPlaying] = useState(false)
  const [metrics, setMetrics] = useState({
    conversationId: null,
    turnId: 0,
    activeResponseId: 0,
    latencyMs: null,
    speechProvider: 'Rime',
    toolRunning: false,
    audioPlaying: false,
  })

  const socketRef = useRef(null)
  const clientIdRef = useRef(CLIENT_ID)
  const audioCtxRef = useRef(null)
  const queueRef = useRef([])
  const isPlayingRef = useRef(false)
  const disposedRef = useRef(false)
  const reconnectTimerRef = useRef(0)
  const connectRef = useRef(null)

  /* ------------------------------------------------------------------ */
  /* Browser audio playback (raw PCM s16le -> Float32 @ 24kHz)          */
  /* ------------------------------------------------------------------ */
  const ensureAudioContext = useCallback(() => {
    if (!audioCtxRef.current) {
      const Ctx = window.AudioContext || window.webkitAudioContext
      if (!Ctx) return null
      audioCtxRef.current = new Ctx({ sampleRate: AUDIO_SAMPLE_RATE })
    }
    if (audioCtxRef.current.state === 'suspended') {
      audioCtxRef.current.resume()
    }
    return audioCtxRef.current
  }, [])

  const resumeAudio = useCallback(() => {
    ensureAudioContext()
  }, [ensureAudioContext])

  const stopAudio = useCallback(() => {
    queueRef.current.forEach((src) => {
      try { src.stop() } catch { /* already stopped */ }
    })
    queueRef.current = []
    isPlayingRef.current = false
    setIsAudioPlaying(false)
  }, [])

  const playAudioChunk = useCallback((bytes) => {
    try {
      const ctx = ensureAudioContext()
      if (!ctx) return
      const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
      const numSamples = Math.floor(bytes.byteLength / 2)
      if (numSamples === 0) return

      const buffer = ctx.createBuffer(1, numSamples, AUDIO_SAMPLE_RATE)
      const channelData = buffer.getChannelData(0)
      for (let i = 0; i < numSamples; i++) {
        channelData[i] = view.getInt16(i * 2, true) / 32768.0
      }

      const source = ctx.createBufferSource()
      source.buffer = buffer
      source.connect(ctx.destination)
      queueRef.current.push(source)

      const playNext = () => {
        const next = queueRef.current.shift()
        if (!next) {
          isPlayingRef.current = false
          setIsAudioPlaying(false)
          return
        }
        next.onended = playNext
        try {
          next.start(0)
        } catch {
          playNext()
        }
      }

      if (!isPlayingRef.current) {
        isPlayingRef.current = true
        setIsAudioPlaying(true)
        playNext()
      }
    } catch (err) {
      console.error('Audio chunk playback error:', err)
    }
  }, [ensureAudioContext])


  /* ------------------------------------------------------------------ */
  /* Transcript feed — merges interim/final turns and coalesces the      */
  /* per-sentence final segments the pipeline streams into one bubble.   */
  /* ------------------------------------------------------------------ */
  const applyTranscript = useCallback((text, isFinal, isUser) => {
    const trimmed = (text || '').trim()
    if (!trimmed) return
    const role = roleOf(isUser)

    setMessages((prev) => {
      const last = prev[prev.length - 1]

      if (last && last.role === role && !last.isFinal) {
        const updated = prev.slice(0, -1)
        updated.push({ ...last, text: trimmed, isFinal: Boolean(isFinal) })
        return updated
      }

      if (isFinal) {
        if (last && last.role === role && last.isFinal && last.text === trimmed) {
          return prev
        }
        if (
          last && last.role === role && last.isFinal &&
          Date.now() - last.timestamp < COALESCE_WINDOW_MS
        ) {
          const updated = prev.slice(0, -1)
          updated.push({
            ...last,
            text: `${last.text} ${trimmed}`.replace(/\s+/g, ' ').trim(),
            timestamp: Date.now(),
          })
          return updated
        }
        return [...prev, { id: nextMessageId(), role, text: trimmed, isFinal: true, timestamp: Date.now(), options: null }]
      }

      return [...prev, { id: nextMessageId(), role, text: trimmed, isFinal: false, timestamp: Date.now(), options: null }]
    })
  }, [])

  /* ------------------------------------------------------------------ */
  /* Server metrics (conversation/turn ids, latency T5-T0, providers)    */
  /* ------------------------------------------------------------------ */
  const mergeMetrics = useCallback((data) => {
    if (!data || typeof data !== 'object') return
    setMetrics((prev) => ({
      conversationId: data.conversation_id ?? prev.conversationId,
      turnId: data.turn_id ?? prev.turnId,
      activeResponseId: data.active_response_id ?? prev.activeResponseId,
      latencyMs: typeof data.latency_ms === 'number' ? data.latency_ms : prev.latencyMs,
      speechProvider: data.speech_provider ?? prev.speechProvider,
      toolRunning: data.tool_running ?? prev.toolRunning,
      audioPlaying: data.audio_playing ?? prev.audioPlaying,
    }))
  }, [])

  const sendMessage = useCallback((msg) => {
    const ws = socketRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(msg))
    }
  }, [])

  const handleServerMessage = useCallback((msg) => {
    switch (msg?.type) {
      case 'connected':
        setConnection('connected')
        if (msg.state?.status) setRawStatus(msg.state.status)
        if (msg.state) mergeMetrics(msg.state)
        break
      case 'state':
        if (msg.status) setRawStatus(msg.status)
        if (msg.metrics) mergeMetrics(msg.metrics)
        break
      case 'transcript':
        applyTranscript(msg.text, msg.is_final, msg.is_user)
        break
      case 'metrics':
        mergeMetrics(msg.data)
        break
      case 'interrupted':
        stopAudio()
        break
      case 'options':
        setMessages((prev) => [
          ...prev,
          { id: nextMessageId(), role: 'assistant', text: '', isFinal: true, timestamp: Date.now(), options: Array.isArray(msg.items) ? msg.items : [] },
        ])
        break
      case 'pong':
      default:
        break
    }
  }, [applyTranscript, mergeMetrics, stopAudio])

  /* ------------------------------------------------------------------ */
  /* Connection lifecycle with auto-reconnect                            */
  /* ------------------------------------------------------------------ */
  const connect = useCallback(() => {
    if (disposedRef.current) return
    const socket = new WebSocket(`${WS_BASE}/${clientIdRef.current}`)
    socket.binaryType = 'arraybuffer'

    socket.onopen = () => setConnection('connected')

    socket.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        playAudioChunk(new Uint8Array(event.data))
        return
      }
      try {
        handleServerMessage(JSON.parse(event.data))
      } catch (err) {
        console.error('Failed to parse message:', err)
      }
    }

    socket.onclose = () => {
      socketRef.current = null
      if (disposedRef.current) return
      setConnection('disconnected')
      reconnectTimerRef.current = window.setTimeout(() => connectRef.current?.(), RECONNECT_DELAY_MS)
    }

    socket.onerror = () => { /* onclose always follows an error */ }

    socketRef.current = socket
  }, [handleServerMessage, playAudioChunk])

  /* ------------------------------------------------------------------ */
  /* User actions                                                        */
  /* ------------------------------------------------------------------ */
  const toggleMic = useCallback(() => {
    const busy =
      rawStatus === 'speaking' || rawStatus === 'processing' || rawStatus === 'tool_running'
    if (busy || isAudioPlaying) {
      stopAudio()
      sendMessage({ type: 'interrupt' }) // barge-in
    } else {
      sendMessage({ type: 'toggle_listening' })
    }
  }, [isAudioPlaying, rawStatus, sendMessage, stopAudio])

  const sendText = useCallback((text) => {
    const trimmed = (text || '').trim()
    if (!trimmed) return
    ensureAudioContext()
    sendMessage({ type: 'prompt', text: trimmed })
    applyTranscript(trimmed, true, true)
  }, [applyTranscript, ensureAudioContext, sendMessage])

  const clearConversation = useCallback(() => setMessages([]), [])

  useEffect(() => {
    disposedRef.current = false
    connectRef.current = connect
    connect()
    return () => {
      disposedRef.current = true
      window.clearTimeout(reconnectTimerRef.current)
      const ws = socketRef.current
      if (ws) {
        ws.onclose = null
        ws.close()
        socketRef.current = null
      }
      stopAudio()
      const ctx = audioCtxRef.current
      audioCtxRef.current = null
      if (ctx) ctx.close().catch(() => {})
    }
  }, [connect, stopAudio])

  return {
    messages,
    rawStatus,
    connection,
    isAudioPlaying,
    metrics,
    toggleMic,
    sendText,
    clearConversation,
    resumeAudio,
  }
}
