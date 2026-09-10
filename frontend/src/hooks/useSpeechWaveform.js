import { useEffect, useRef, useState } from 'react'

const BAR_COUNT = 5
const UPDATE_EVERY_N_FRAMES = 2

/**
 * Real-time microphone energy visualizer (5 bars, 0..1).
 *
 * Uses getUserMedia purely to *analyze* local mic energy for the waveform UI —
 * nothing is streamed to the backend (the server pipeline captures audio on
 * its side and is toggled via the `toggle_listening` WebSocket message).
 * Falls back to a smooth simulated animation when the mic is unavailable or
 * permission is denied.
 */
export function useSpeechWaveform(active) {
  const [bars, setBars] = useState(() => Array(BAR_COUNT).fill(0.14))
  const frameRef = useRef(0)

  useEffect(() => {
    if (!active) {
      return undefined
    }

    let cancelled = false
    let rafId = 0
    let stream = null
    let audioCtx = null
    let source = null
    let analyser = null
    let phase = 0
    let frameCount = 0
    frameRef.current = 0

    const startSimulated = () => {
      if (cancelled) return
      const tick = () => {
        phase += 0.09
        if (frameCount++ % UPDATE_EVERY_N_FRAMES === 0) {
          setBars(Array.from({ length: BAR_COUNT }, (_, i) =>
            0.16 + Math.abs(Math.sin(phase + i * 0.85)) * 0.66,
          ))
        }
        rafId = requestAnimationFrame(tick)
      }
      rafId = requestAnimationFrame(tick)
    }

    startSimulated()

    return () => {
      cancelled = true
      cancelAnimationFrame(rafId)
    }
  }, [active])

  return { bars }
}
