import { useEffect, useRef } from 'react'
import MessageBubble from './MessageBubble.jsx'
import AudioMessageBubble from './AudioMessageBubble.jsx'
import OptionCards from './OptionCards.jsx'
import { SparkIcon } from './icons.jsx'

/**
 * Scrollable conversation feed with stick-to-bottom auto-scroll.
 * Assistant turns render text bubbles plus a live voice player pill while
 * the assistant is speaking, and option decks when structured results exist.
 */
export default function ChatArea({ messages, isSpeaking, onOptionSelect }) {
  const scrollRef = useRef(null)
  const stickRef = useRef(true)

  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 96
  }

  // Auto-scroll only when the user is already at (or near) the bottom.
  useEffect(() => {
    const el = scrollRef.current
    if (el && stickRef.current) {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    }
  }, [messages])

  const lastAssistantId = [...messages].reverse().find((m) => m.role === 'assistant' && m.text)?.id

  return (
    <main className="chat-area" ref={scrollRef} onScroll={handleScroll}>
      {messages.length === 0 ? (
        <div className="empty-state">
          <div className="empty-orb" aria-hidden="true">
            <span className="empty-orb-core" />
          </div>
          <h1 className="empty-title">Your conversation lives here</h1>
          <p className="empty-hint">
            The mic is live — just start speaking, or type below.
            The assistant replies with voice in real time.
          </p>
          <div className="empty-tip">
            <SparkIcon size={14} />
            <span>Tip: tap the mic while the assistant is talking to barge in instantly.</span>
          </div>
        </div>
      ) : (
        <div className="chat-feed">
          {messages.map((msg) => (
            <div key={msg.id} className="chat-item">
              {msg.options?.length ? (
                <OptionCards options={msg.options} onSelect={onOptionSelect} />
              ) : msg.role === 'assistant' ? (
                <>
                  <MessageBubble
                    role="assistant"
                    text={msg.text}
                    isFinal={msg.isFinal}
                    timestamp={msg.timestamp}
                  />
                  {isSpeaking && msg.id === lastAssistantId && (
                    <AudioMessageBubble speaking />
                  )}
                </>
              ) : (
                <MessageBubble
                  role="user"
                  text={msg.text}
                  isFinal={msg.isFinal}
                  timestamp={msg.timestamp}
                />
              )}
            </div>
          ))}
        </div>
      )}
    </main>
  )
}
