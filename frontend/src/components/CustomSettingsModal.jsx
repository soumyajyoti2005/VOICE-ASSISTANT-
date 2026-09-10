import { CloseIcon } from './icons.jsx'

const OUTPUT_CHIPS = ['Paragraph', 'Numbered List', 'Essay', 'Titles', 'Summary', 'Speech']
const TONE_CHIPS = ['Conversational', 'Direct', 'Detailed', 'Concise']

/**
 * Dark slide-over drawer ("Custom Settings"):
 *  1. Real-time performance — live latency (T5-T0), response id, turn and
 *     the live pipeline provider badges (Rime TTS / Groq Whisper STT).
 *  2. Output preferences — expected-output chips, output-length slider and
 *     voice/tone chips. Preferences are stored locally in the browser.
 */
export default function CustomSettingsModal({ open, onClose, metrics, prefs, onPrefsChange, connection }) {
  if (!open) return null

  const toggleOutput = (chip) => {
    const set = new Set(prefs.outputs)
    if (set.has(chip)) set.delete(chip)
    else set.add(chip)
    onPrefsChange({ ...prefs, outputs: [...set] })
  }

  return (
    <div className="drawer-root">
      <div className="drawer-overlay" onClick={onClose} aria-hidden="true" />

      <aside className="drawer" role="dialog" aria-modal="true" aria-label="Custom settings">
        <div className="drawer__header">
          <h2 className="drawer__title">Custom Settings</h2>
          <button type="button" className="drawer__close" onClick={onClose} aria-label="Close settings">
            <CloseIcon />
          </button>
        </div>

        <div className="drawer__body">
          {/* Section 1 — Real-Time Performance & Metrics */}
          <section className="drawer__section">
            <h3 className="drawer__section-title">Real-Time Performance</h3>

            <div className="latency-card">
              <span className="latency-value">
                {metrics.latencyMs != null ? Math.round(metrics.latencyMs) : '—'}
                <small> ms</small>
              </span>
              <span className="latency-label">Live Latency (T₅ − T₀)</span>
            </div>

            <div className="metric-grid">
              <div className="metric-card">
                <span className="metric-label">Active Response ID</span>
                <span className="metric-value">#{metrics.activeResponseId}</span>
              </div>
              <div className="metric-card">
                <span className="metric-label">Turn</span>
                <span className="metric-value">{metrics.turnId}</span>
              </div>
              <div className="metric-card">
                <span className="metric-label">Connection</span>
                <span className={`metric-value ${connection === 'connected' ? 'ok' : 'warn'}`}>
                  {connection === 'connected' ? 'Live' : connection === 'connecting' ? '…' : 'Offline'}
                </span>
              </div>
              <div className="metric-card">
                <span className="metric-label">Pipeline</span>
                <span className="metric-value">{metrics.toolRunning ? 'Tool running' : metrics.audioPlaying ? 'Speaking' : 'Ready'}</span>
              </div>
            </div>

            <div className="provider-row">
              <span className="provider-badge"><b>TTS</b> {metrics.speechProvider || 'Rime'} · mist / amber</span>
              <span className="provider-badge"><b>STT</b> Groq · whisper-large-v3-turbo</span>
              <span className="provider-badge"><b>LLM</b> Gemini flash</span>
            </div>
          </section>

          {/* Section 2 — Output Preferences */}
          <section className="drawer__section">
            <h3 className="drawer__section-title">Expected Outputs</h3>
            <div className="chips-row">
              {OUTPUT_CHIPS.map((chip) => (
                <button
                  key={chip}
                  type="button"
                  className={`chip ${prefs.outputs.includes(chip) ? 'chip--active' : ''}`}
                  onClick={() => toggleOutput(chip)}
                  aria-pressed={prefs.outputs.includes(chip)}
                >
                  {chip}
                </button>
              ))}
            </div>

            <h3 className="drawer__section-title">Output Length</h3>
            <div className="slider-row">
              <input
                type="range"
                className="slider"
                min="50"
                max="800"
                step="25"
                value={prefs.length}
                onChange={(e) => onPrefsChange({ ...prefs, length: Number(e.target.value) })}
                aria-label="Output length in characters"
              />
              <span className="slider-value">{prefs.length} chars</span>
            </div>

            <h3 className="drawer__section-title">Voice / Tone</h3>
            <div className="chips-row">
              {TONE_CHIPS.map((chip) => (
                <button
                  key={chip}
                  type="button"
                  className={`chip ${prefs.tone === chip ? 'chip--active' : ''}`}
                  onClick={() => onPrefsChange({ ...prefs, tone: chip })}
                  aria-pressed={prefs.tone === chip}
                >
                  {chip}
                </button>
              ))}
            </div>

            <p className="drawer-footnote">
              Output preferences are stored locally in this browser and do not alter the backend pipeline.
            </p>
          </section>
        </div>
      </aside>
    </div>
  )
}
