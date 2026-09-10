import { useState } from 'react'
import { CheckIcon } from './icons.jsx'

/**
 * Horizontal swipeable deck of dark slate option cards (times, prices,
 * choices). The selected card fills with royal blue and shows a checkmark.
 * Clicking a card selects it and (optionally) sends its prompt.
 */
export default function OptionCards({ options, onSelect }) {
  const [selectedId, setSelectedId] = useState(null)

  if (!options?.length) return null

  const handleClick = (option) => {
    setSelectedId(option.id)
    onSelect?.(option)
  }

  return (
    <div className="options-row" role="listbox" aria-label="Options">
      {options.map((option) => {
        const active = selectedId === option.id
        return (
          <button
            key={option.id}
            type="button"
            role="option"
            aria-selected={active}
            className={`option-card ${active ? 'option-card--active' : ''}`}
            onClick={() => handleClick(option)}
          >
            {option.tag && <span className="option-tag">{option.tag}</span>}
            <span className="option-title">{option.title}</span>
            {option.subtitle && <span className="option-sub">{option.subtitle}</span>}
            {option.price && <span className="option-price">{option.price}</span>}
            <span className="option-check" aria-hidden="true"><CheckIcon /></span>
          </button>
        )
      })}
    </div>
  )
}
