import { BrandIcon, SlidersIcon } from './icons.jsx'

/**
 * Minimal top navigation: brand mark, live status pill with glowing dot,
 * clear action and the settings toggle for the Custom Settings drawer.
 */
export default function Header({ statusLabel, statusTone, onClear, onOpenSettings }) {
  return (
    <header className="header">
      <div className="brand">
        <span className="brand-mark"><BrandIcon /></span>
        <span className="brand-name">Voice Assistant</span>
      </div>

      <div className={`status-pill tone-${statusTone}`} role="status" aria-live="polite">
        <span className="status-dot" aria-hidden="true" />
        <span className="status-label">{statusLabel}</span>
      </div>

      <div className="header-actions">
        <button type="button" className="header-action" onClick={onClear}>
          Clear
        </button>
        <button
          type="button"
          className="icon-btn"
          onClick={onOpenSettings}
          aria-label="Open custom settings"
          title="Custom settings"
        >
          <SlidersIcon />
        </button>
      </div>
    </header>
  )
}
