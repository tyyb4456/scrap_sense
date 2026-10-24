interface MessageTextProps {
  text: string
  tone: 'assistant' | 'user'
}

const numericPattern =
  /((?:Rs\.?|PKR|₨)\s?\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s?(?:kg|kilos?|kilo|grams?|g|rupay|rupees?|rs)\b)/gi

export function MessageText({ text }: MessageTextProps) {
  const parts = text.split(numericPattern)

  return (
    <span className="block whitespace-pre-wrap break-words">
      {parts.map((part, index) =>
        index % 2 === 1 ? (
          <span
            key={`${index}-${part}`}
            className="font-mono text-[0.93em] tracking-[-0.01em] tabular-nums text-accent-text"
          >
            {part}
          </span>
        ) : (
          <span key={`${index}-text`}>{part}</span>
        ),
      )}
    </span>
  )
}
