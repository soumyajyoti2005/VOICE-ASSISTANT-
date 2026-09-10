/**
 * Chat bubbles — user turns on the right in vibrant royal blue, assistant
 * turns on the left in a dark slate capsule. Supports interim (non-final)
 * text with a blinking caret and renders links as clean pill tags.
 */

const MD_LINK_RE = /(\[[^\]]+\]\([^)\s]+\)|https?:\/\/[^\s)]+)/g

function prettyUrl(url) {
  const trimmed = url.replace(/^https?:\/\//, '').replace(/\/$/, '')
  return trimmed.length > 42 ? `${trimmed.slice(0, 42)}…` : trimmed
}

function renderContent(text) {
  const parts = String(text).split(MD_LINK_RE)
  return parts.map((part, i) => {
    if (!part) return null
    const md = part.match(/^\[([^\]]+)\]\(([^)\s]+)\)$/)
    if (md) {
      return (
        <a key={i} className="link-pill" href={md[2]} target="_blank" rel="noreferrer">
          {md[1]}
        </a>
      )
    }
    if (/^https?:\/\//.test(part)) {
      return (
        <a key={i} className="link-pill" href={part} target="_blank" rel="noreferrer">
          {prettyUrl(part)}
        </a>
      )
    }
    return part
  })
}

const formatTime = (ts) =>
  new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

export default function MessageBubble({ role, text, isFinal, timestamp }) {
  const isUser = role === 'user'
  return (
    <div className={`bubble-row ${isUser ? 'user' : 'assistant'}`}>
      <div className={`bubble ${isUser ? 'bubble--user' : 'bubble--assistant'}`}>
        <div className="bubble-text">
          {renderContent(text)}
          {!isFinal && <span className="caret" aria-hidden="true" />}
        </div>
      </div>
      <span className="bubble-time">{formatTime(timestamp)}</span>
    </div>
  )
}
