import { useEffect, useMemo, useState } from 'react'
import Header from './components/Header.jsx'
import ChatArea from './components/ChatArea.jsx'
import QueryBar from './components/QueryBar.jsx'
import CustomSettingsModal from './components/CustomSettingsModal.jsx'
import { useVoiceAssistant } from './hooks/useVoiceAssistant.js'
import './styles/theme.css'
import './styles/components.css'
import './styles/App.css'

const PREFS_KEY = 'va-output-prefs'
const DEFAULT_PREFS = { outputs: ['Paragraph'], length: 300, tone: 'Conversational' }

function loadPrefs() {
  try {
    const raw = localStorage.getItem(PREFS_KEY)
    return raw ? { ...DEFAULT_PREFS, ...JSON.parse(raw) } : DEFAULT_PREFS
  } catch {
    return DEFAULT_PREFS
  }
}

export default function App() {
  const {
    messages,
    rawStatus,
    connection,
    isAudioPlaying,
    metrics,
    toggleMic,
    sendText,
    clearConversation,
    resumeAudio,
  } = useVoiceAssistant()

  const [settingsOpen, setSettingsOpen] = useState(false)
  const [prefs, setPrefs] = useState(loadPrefs)

  useEffect(() => {
    try {
      localStorage.setItem(PREFS_KEY, JSON.stringify(prefs))
    } catch { /* storage unavailable */ }
  }, [prefs])

  const micState = useMemo(() => {
    if (rawStatus === 'speaking' || isAudioPlaying) return 'speaking'
    if (rawStatus === 'processing' || rawStatus === 'tool_running') return 'thinking'
    if (rawStatus === 'listening') return 'listening'
    if (rawStatus === 'paused') return 'paused'
    return 'idle'
  }, [rawStatus, isAudioPlaying])

  const header = useMemo(() => {
    if (connection !== 'connected') {
      return { label: connection === 'connecting' ? 'Connecting…' : 'Reconnecting…', tone: 'offline' }
    }
    switch (micState) {
      case 'listening': return { label: 'Listening…', tone: 'live' }
      case 'speaking': return { label: 'Speaking…', tone: 'speaking' }
      case 'thinking':
        return { label: rawStatus === 'tool_running' ? 'Searching…' : 'Thinking…', tone: 'busy' }
      case 'paused': return { label: 'Paused', tone: 'paused' }
      default: return { label: 'Live', tone: 'idle' }
    }
  }, [connection, micState, rawStatus])

  const isSpeaking = micState === 'speaking'

  const handleMicClick = () => {
    resumeAudio() // unlock the AudioContext on user gesture
    toggleMic()
  }

  const handleSubmit = (text) => {
    resumeAudio()
    sendText(text)
  }

  const handleOptionSelect = (option) => {
    resumeAudio()
    sendText(option.prompt || option.title || '')
  }

  return (
    <div className="app">
      <div className="app-glow app-glow--top" aria-hidden="true" />
      <div className="app-glow app-glow--bottom" aria-hidden="true" />

      <div className="app-frame">
        <Header
          statusLabel={header.label}
          statusTone={header.tone}
          onClear={clearConversation}
          onOpenSettings={() => setSettingsOpen(true)}
        />

        <ChatArea
          messages={messages}
          isSpeaking={isSpeaking}
          onOptionSelect={handleOptionSelect}
        />

        <QueryBar
          micState={micState}
          onSubmit={handleSubmit}
          onMicClick={handleMicClick}
        />
      </div>

      <CustomSettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        metrics={metrics}
        prefs={prefs}
        onPrefsChange={setPrefs}
        connection={connection}
      />
    </div>
  )
}
