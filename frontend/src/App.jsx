import { useState, useEffect, useRef, useCallback } from 'react'
import './App.css'

const WS_URL = 'ws://localhost:8000/ws'

const MIC_SVG = (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
    <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
    <line x1="12" y1="19" x2="12" y2="22" />
  </svg>
)

const STOP_SVG = (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor">
    <rect x="6" y="6" width="12" height="12" rx="2" />
  </svg>
)

const WAVE_SVG = (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <line x1="12" y1="18" x2="12" y2="6" />
    <line x1="8" y1="14" x2="8" y2="10" />
    <line x1="16" y1="14" x2="16" y2="10" />
    <line x1="4" y1="20" x2="4" y2="16" />
    <line x1="20" y1="20" x2="20" y2="16" />
  </svg>
)

const SPINNER_SVG = (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
    <circle cx="12" cy="12" r="10" strokeOpacity="0.25" />
    <path d="M12 2a10 10 0 0 1 10 10" />
  </svg>
)

const SETTINGS_SVG = (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1Z" />
  </svg>
)

const CLOSE_SVG = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
)

function App() {
  const [ws, setWs] = useState(null)
  const [clientId] = useState(() => `client-${Math.random().toString(36).slice(2, 9)}`)
  const [status, setStatus] = useState('Tap to talk')
  const [transcript, setTranscript] = useState([])
  const [debugOpen, setDebugOpen] = useState(false)
  const [debugData, setDebugData] = useState({
    activeResponseId: 0,
    latencyMs: null,
    speechProvider: 'Rime',
  })
  const [audioPlaying, setAudioPlaying] = useState(false)
  const audioContextRef = useRef(null)
  const audioQueueRef = useRef([])
  const isPlayingRef = useRef(false)

  const addTranscript = useCallback((text, isFinal, isUser) => {
    setTranscript(prev => {
      if (!text || !text.trim()) return prev
      const trimmed = text.trim()
      if (prev.length > 0) {
        const last = prev[prev.length - 1]
        if (last.text === trimmed && last.isUser === isUser && last.isFinal && isFinal) {
          return prev
        }
      }
      if (isFinal) {
        if (prev.length > 0 && !prev[prev.length - 1].isFinal && prev[prev.length - 1].isUser === isUser) {
          const updated = [...prev]
          updated[updated.length - 1] = { text: trimmed, isUser, timestamp: Date.now(), isFinal: true }
          return updated
        }
        return [...prev, { text: trimmed, isUser, timestamp: Date.now(), isFinal: true }]
      } else {
        const newTranscript = [...prev]
        if (newTranscript.length > 0 && !newTranscript[newTranscript.length - 1].isFinal && newTranscript[newTranscript.length - 1].isUser === isUser) {
          newTranscript[newTranscript.length - 1] = { text: trimmed, isUser, timestamp: Date.now(), isFinal: false }
        } else {
          newTranscript.push({ text: trimmed, isUser, timestamp: Date.now(), isFinal: false })
        }
        return newTranscript
      }
    })
  }, [])

  const playAudioChunk = useCallback(async (audioData) => {
    try {
      if (!audioContextRef.current) {
        audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 })
      }
      const ctx = audioContextRef.current
      if (ctx.state === 'suspended') await ctx.resume()

      // Convert raw 16-bit linear PCM (pcm_s16le, 24kHz) to Float32 AudioBuffer
      const dataView = new DataView(audioData.buffer, audioData.byteOffset, audioData.byteLength)
      const numSamples = Math.floor(audioData.byteLength / 2)
      if (numSamples === 0) return

      const audioBuffer = ctx.createBuffer(1, numSamples, 24000)
      const channelData = audioBuffer.getChannelData(0)
      for (let i = 0; i < numSamples; i++) {
        channelData[i] = dataView.getInt16(i * 2, true) / 32768.0
      }

      const source = ctx.createBufferSource()
      source.buffer = audioBuffer
      source.connect(ctx.destination)

      audioQueueRef.current.push(source)

      if (!isPlayingRef.current) {
        isPlayingRef.current = true
        setAudioPlaying(true)
        playNext()
      }

      function playNext() {
        const next = audioQueueRef.current.shift()
        if (next) {
          next.onended = playNext
          try {
            next.start(0)
          } catch (e) {
            playNext()
          }
        } else {
          isPlayingRef.current = false
          setAudioPlaying(false)
        }
      }
    } catch (err) {
      console.error('Audio chunk playback error:', err)
    }
  }, [])

  const stopAudio = useCallback(() => {
    audioQueueRef.current.forEach(source => {
      try { source.stop() } catch (e) {}
    })
    audioQueueRef.current = []
    isPlayingRef.current = false
    setAudioPlaying(false)
  }, [])

  const connect = useCallback(() => {
    const websocket = new WebSocket(`${WS_URL}/${clientId}`)
    websocket.binaryType = 'arraybuffer'

    websocket.onopen = () => {
      console.log('WebSocket connected')
      setStatus('Tap to talk')
    }

    websocket.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        const audioData = new Uint8Array(event.data)
        playAudioChunk(audioData)
        return
      }

      try {
        const msg = JSON.parse(event.data)
        handleMessage(msg)
      } catch (e) {
        console.error('Failed to parse message:', e)
      }
    }

    websocket.onclose = () => {
      console.log('WebSocket disconnected')
      setStatus('Disconnected')
      setTimeout(connect, 2000)
    }

    websocket.onerror = (err) => {
      console.error('WebSocket error:', err)
    }

    setWs(websocket)
  }, [clientId, playAudioChunk])

  const formatStatus = (raw) => {
    switch (raw?.toLowerCase()) {
      case 'listening': return 'Listening…'
      case 'processing': return 'Thinking…'
      case 'tool_running': return 'Searching…'
      case 'speaking': return 'Speaking…'
      case 'idle': return 'Tap to talk'
      default: return raw || 'Tap to talk'
    }
  }

  const handleMessage = (msg) => {
    switch (msg.type) {
      case 'state':
        if (msg.status) setStatus(formatStatus(msg.status))
        if (msg.metrics) {
          setDebugData(prev => ({
            ...prev,
            activeResponseId: msg.metrics.active_response_id || prev.activeResponseId,
            latencyMs: msg.metrics.latency_ms || prev.latencyMs,
            speechProvider: msg.metrics.speech_provider || prev.speechProvider,
          }))
        }
        break
      case 'transcript':
        addTranscript(msg.text, msg.is_final, msg.is_user ?? false)
        break
      case 'interrupted':
        stopAudio()
        break
      case 'connected':
        setDebugData(prev => ({ ...prev, activeResponseId: msg.state?.active_response_id || 0 }))
        if (msg.state?.status) setStatus(formatStatus(msg.state.status))
        break
    }
  }

  const sendMessage = useCallback((msg) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(msg))
    }
  }, [ws])

  const handleMicClick = () => {
    if (audioContextRef.current && audioContextRef.current.state === 'suspended') {
      audioContextRef.current.resume()
    }
    if (status === 'Speaking…' || audioPlaying) {
      sendMessage({ type: 'interrupt' })
      stopAudio()
      setStatus('Listening…')
    } else {
      sendMessage({ type: 'interrupt' })
      setStatus('Listening…')
    }
  }

  useEffect(() => {
    connect()
    const unlockAudio = () => {
      if (audioContextRef.current && audioContextRef.current.state === 'suspended') {
        audioContextRef.current.resume()
      }
    }
    window.addEventListener('click', unlockAudio)
    return () => {
      window.removeEventListener('click', unlockAudio)
      if (ws) ws.close()
      stopAudio()
    }
  }, [connect, stopAudio])

  const statusClass = status === 'Listening…' ? 'listening' :
                      status === 'Speaking…' ? 'speaking' :
                      (status === 'Thinking…' || status === 'Searching…') ? 'thinking' : 'idle'

  const [inputText, setInputText] = useState('')

  const handleSendText = (e) => {
    e.preventDefault()
    if (!inputText.trim()) return
    if (audioContextRef.current && audioContextRef.current.state === 'suspended') {
      audioContextRef.current.resume()
    }
    const text = inputText.trim()
    sendMessage({ type: 'prompt', text })
    addTranscript(text, true, true)
    setInputText('')
  }

  return (
    <div className="app">
      <div className="debug-toggle" onClick={() => setDebugOpen(!debugOpen)}>
        {SETTINGS_SVG}
      </div>

      <div className="transcript-area">
        {transcript.map((turn, i) => (
          <div key={i} className={`turn ${turn.isUser ? 'user' : 'assistant'}`}>
            <div className="turn-text">{turn.text}</div>
          </div>
        ))}
        {!transcript.length && <div className="empty-hint">Mic is live! Speak anytime, or send a prompt below</div>}
      </div>

      <div className="status-bar">
        <span className={`status-indicator ${statusClass}`}></span>
        <span className="status-text">{status}</span>
      </div>

      <button
        className={`mic-button ${statusClass} ${audioPlaying ? 'playing' : ''}`}
        onClick={handleMicClick}
        aria-label="Microphone"
      >
        {status === 'Speaking…' || audioPlaying ? STOP_SVG :
         status === 'Listening…' ? WAVE_SVG :
         (status === 'Thinking…' || status === 'Searching…') ? SPINNER_SVG : MIC_SVG}
      </button>

      <form className="text-input-form" onSubmit={handleSendText}>
        <input
          type="text"
          placeholder="Or type a message to test voice..."
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
        />
        <button type="submit">Send</button>
      </form>

      {debugOpen && (
        <div className="debug-panel">
          <div className="debug-header">
            <span>Debug</span>
            <button onClick={() => setDebugOpen(false)}>{CLOSE_SVG}</button>
          </div>
          <div className="debug-row">
            <span>Active Response ID:</span>
            <span>{debugData.activeResponseId}</span>
          </div>
          <div className="debug-row">
            <span>Latency (ms):</span>
            <span>{debugData.latencyMs ? debugData.latencyMs.toFixed(0) : '—'}</span>
          </div>
          <div className="debug-row">
            <span>Speech Provider:</span>
            <span>{debugData.speechProvider}</span>
          </div>
        </div>
      )}
    </div>
  )
}

export default App