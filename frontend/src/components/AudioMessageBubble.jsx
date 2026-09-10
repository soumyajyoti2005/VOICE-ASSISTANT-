import { useEffect, useRef, useState } from 'react'
import { PlayIcon, PauseIcon } from './icons.jsx'

/* Deterministic bar heights so the waveform looks the same every render. */
const BAR_HEIGHTS = [0.42, 0.78, 0.55, 0.92, 0.38, 0.7, 0.5, 0.85, 0.32, 0.66,
  0.48, 0.9, 0.36, 0.72, 0.58, 0.82, 0.44, 0.68, 0.52, 0.88, 0.4, 0.74]
const SPEEDS = [1, 1.5, 2]

const formatTime = (seconds) => {
  if (!Number.isFinite(seconds)) return '0:00'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

/**
 * Sleek voice pill player. Two modes:
 *  - `speaking`  : live indicator while the assistant's voice is streaming
 *                  (animated equalizer bars + LIVE badge).
 *  - with `src`  : fully interactive player (play/pause, dancing bars while
 *                  playing, playback speed cycle, duration badge).
 */
export default function AudioMessageBubble({ src, speaking = false }) {
  const audioRef = useRef(null)
  const [playing, setPlaying] = useState(false)
  const [speedIndex, setSpeedIndex] = useState(0)
  const [duration, setDuration] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return undefined
    const onTime = () => setCurrentTime(audio.currentTime)
    const onEnd = () => setPlaying(false)
    const onMeta = () => setDuration(audio.duration || 0)
    audio.addEventListener('timeupdate', onTime)
    audio.addEventListener('ended', onEnd)
    audio.addEventListener('loadedmetadata', onMeta)
    return () => {
      audio.removeEventListener('timeupdate', onTime)
      audio.removeEventListener('ended', onEnd)
      audio.removeEventListener('loadedmetadata', onMeta)
    }
  }, [src])

  if (!src && !speaking) return null

  const interactive = Boolean(src)
  const isActive = interactive ? playing : speaking
  const speed = SPEEDS[speedIndex]

  const togglePlay = () => {
    const audio = audioRef.current
    if (!audio) return
    if (playing) {
      audio.pause()
      setPlaying(false)
    } else {
      audio.play().then(() => setPlaying(true)).catch(() => setPlaying(false))
    }
  }

  const cycleSpeed = () => {
    const nextIndex = (speedIndex + 1) % SPEEDS.length
    setSpeedIndex(nextIndex)
    if (audioRef.current) audioRef.current.playbackRate = SPEEDS[nextIndex]
  }

  return (
    <div className={`audio-pill ${isActive ? 'audio-pill--active' : ''} ${interactive ? '' : 'audio-pill--live'}`}>
      {interactive ? (
        <button
          type="button"
          className="audio-pill__play"
          onClick={togglePlay}
          aria-label={playing ? 'Pause voice message' : 'Play voice message'}
        >
          {playing ? <PauseIcon /> : <PlayIcon />}
        </button>
      ) : (
        <span className="audio-pill__live-dot" aria-hidden="true" />
      )}

      <span className={`audio-pill__bars ${isActive ? 'eq--active' : ''}`} aria-hidden="true">
        {BAR_HEIGHTS.map((h, i) => (
          <span key={i} style={{ '--h': `${Math.round(h * 100)}%`, '--d': `${(i % 7) * 0.09}s` }} />
        ))}
      </span>

      <span className="audio-pill__meta">
        {interactive ? (
          <>
            <span className="audio-pill__time">{formatTime(currentTime)} / {formatTime(duration)}</span>
            <button type="button" className="audio-pill__speed" onClick={cycleSpeed} aria-label="Playback speed">
              {speed.toFixed(1)}x
            </button>
          </>
        ) : (
          <span className="badge badge--live">LIVE</span>
        )}
      </span>

      {interactive && (
        <audio ref={audioRef} src={src} preload="metadata" style={{ display: 'none' }} />
      )}
    </div>
  )
}
