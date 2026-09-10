import { useEffect, useRef, useState } from 'react'
import { useSpeechWaveform } from '../hooks/useSpeechWaveform.js'
import { MicIcon, MicOffIcon, StopIcon, SendIcon, PaperclipIcon, SpinnerIcon } from './icons.jsx'

const SAMPLE_PROMPTS = [
  'Find a highly rated coffee shop near me',
  'What is the latest news on electric cars?',
  'Plan a quick 2-day trip itinerary',
]

/**
 * Bottom query bar — sleek capsule with an integrated mic on its right edge.
 * Mic states: idle (gray) -> listening (glowing blue + live waveform bars)
 * -> speaking/processing (stop square for barge-in). When the user types,
 * the mic morphs into a blue circular send button.
 */
export default function QueryBar({ micState, onSubmit, onMicClick }) {
  const [value, setValue] = useState('')
  const [samplesOpen, setSamplesOpen] = useState(false)
  const inputRef = useRef(null)
  const { bars } = useSpeechWaveform(micState === 'listening')

  // Close the samples popover on Escape.
  useEffect(() => {
    if (!samplesOpen) return undefined
    const onKey = (e) => {
      if (e.key === 'Escape') setSamplesOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [samplesOpen])

  const hasText = value.trim().length > 0

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!hasText) return
    onSubmit(value.trim())
    setValue('')
    inputRef.current?.focus()
  }

  const handleMicClick = () => {
    setSamplesOpen(false)
    onMicClick()
  }

  const renderRightAction = () => {
    if (hasText) {
      return (
        <button type="submit" className="mic-btn mic-btn--send" aria-label="Send message" title="Send">
          <SendIcon />
        </button>
      )
    }
    if (micState === 'speaking') {
      return (
        <button
          type="button"
          className="mic-btn mic-btn--stop"
          onClick={handleMicClick}
          aria-label="Stop assistant speech"
          title="Stop the assistant (barge-in)"
        >
          <StopIcon />
        </button>
      )
    }
    if (micState === 'thinking') {
      return (
        <button
          type="button"
          className="mic-btn mic-btn--thinking"
          onClick={handleMicClick}
          aria-label="Cancel current response"
          title="Cancel current response"
        >
          <SpinnerIcon />
        </button>
      )
    }
    if (micState === 'listening') {
      return (
        <button
          type="button"
          className="mic-btn mic-btn--listening"
          onClick={handleMicClick}
          aria-label="Microphone live — click to pause"
          title="Listening — click to pause the mic"
        >
          <span className="mic-wave" aria-hidden="true">
            {bars.map((b, i) => (
              <span key={i} style={{ height: `${7 + Math.round(b * 17)}px` }} />
            ))}
          </span>
        </button>
      )
    }
    if (micState === 'paused') {
      return (
        <button
          type="button"
          className="mic-btn mic-btn--paused"
          onClick={handleMicClick}
          aria-label="Microphone paused — click to resume"
          title="Mic paused — click to resume"
        >
          <MicOffIcon />
        </button>
      )
    }
    return (
      <button
        type="button"
        className="mic-btn"
        onClick={handleMicClick}
        aria-label="Toggle microphone"
        title="Toggle microphone"
      >
        <MicIcon />
      </button>
    )
  }

  return (
    <div className="query-wrap">
      {samplesOpen && (
        <>
          <div className="samples-backdrop" onClick={() => setSamplesOpen(false)} aria-hidden="true" />
          <div className="samples-popover" role="menu" aria-label="Sample prompts">
            <span className="samples-title">Try asking</span>
            {SAMPLE_PROMPTS.map((prompt) => (
              <button
                key={prompt}
                type="button"
                className="sample-chip"
                role="menuitem"
                onClick={() => {
                  setValue(prompt)
                  setSamplesOpen(false)
                  inputRef.current?.focus()
                }}
              >
                {prompt}
              </button>
            ))}
          </div>
        </>
      )}

      <form className="query-bar" onSubmit={handleSubmit}>
        <button
          type="button"
          className="query-action"
          onClick={() => setSamplesOpen((open) => !open)}
          aria-label="Sample prompts"
          aria-expanded={samplesOpen}
          title="Sample prompts"
        >
          <PaperclipIcon />
        </button>

        <input
          ref={inputRef}
          type="text"
          className="query-input"
          placeholder="Type something..."
          value={value}
          onChange={(e) => setValue(e.target.value)}
          aria-label="Message"
          autoComplete="off"
          spellCheck="false"
        />

        {renderRightAction()}
      </form>
    </div>
  )
}
