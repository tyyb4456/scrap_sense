interface MessageTextProps {
  text: string
  tone?: 'assistant' | 'user'
}

const numericSource =
  String.raw`(?:Rs\.?|PKR|₨)\s?\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s?(?:kg|kilos?|kilo|grams?|g|rupay|rupees?|rs)\b`

const linkSource = String.raw`https?:\/\/[^\s<]+`

const enhancePattern = new RegExp(
  String.raw`(${linkSource}|${numericSource})`,
  'gi',
)

const inlinePattern =
  /(\*\*[^*\n]+\*\*|__[^_\n]+__|`[^`\n]+`|~~[^~\n]+~~|\[[^\]\n]+\]\([^)\s]+\)|\*[^*\n]+\*)/g

const linkPattern = /^\[([^\]\n]+)\]\(([^)\s]+)\)$/

function trimUrl(url: string) {
  return url.replace(/[.,;:!?]+$/, '')
}

function PlainText({ text }: { text: string }) {
  const parts = text.split(enhancePattern)

  return (
    <>
      {parts.map((part, index) => {
        if (!part) return null
        if (index % 2 === 0) return <span key={index}>{part}</span>

        if (/^https?:\/\//i.test(part)) {
          return (
            <a
              key={index}
              href={trimUrl(part)}
              target="_blank"
              rel="noreferrer noopener"
              className="font-medium text-accent-text underline decoration-accent/35 decoration-1 underline-offset-2 transition-colors hover:decoration-accent"
            >
              {part}
            </a>
          )
        }

        return (
          <span
            key={index}
            className="font-mono text-[0.93em] tracking-[-0.01em] tabular-nums text-accent-text"
          >
            {part}
          </span>
        )
      })}
    </>
  )
}

export function MessageText({ text }: MessageTextProps) {
  const parts = text.split(inlinePattern)

  return (
    <span className="block whitespace-pre-wrap break-words">
      {parts.map((part, index) => {
        if (!part) return null
        if (index % 2 === 0) return <PlainText key={index} text={part} />

        if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
          return (
            <strong key={index} className="font-semibold text-ink">
              <PlainText text={part.slice(2, -2)} />
            </strong>
          )
        }

        if (part.startsWith('__') && part.endsWith('__') && part.length > 4) {
          return (
            <strong key={index} className="font-semibold text-ink">
              <PlainText text={part.slice(2, -2)} />
            </strong>
          )
        }

        if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
          return (
            <code
              key={index}
              className="rounded-[5px] border border-rule bg-inset px-[0.35em] py-[0.08em] font-mono text-[0.86em] text-ink"
            >
              {part.slice(1, -1)}
            </code>
          )
        }

        if (part.startsWith('~~') && part.endsWith('~~') && part.length > 4) {
          return (
            <span key={index} className="text-muted line-through">
              {part.slice(2, -2)}
            </span>
          )
        }

        if (part.startsWith('[')) {
          const link = linkPattern.exec(part)
          const href = link?.[2] ?? ''
          if (link && /^(https?:\/\/|mailto:|\/)/i.test(href)) {
            return (
              <a
                key={index}
                href={href}
                target={href.startsWith('/') ? undefined : '_blank'}
                rel={href.startsWith('/') ? undefined : 'noreferrer noopener'}
                className="font-medium text-accent-text underline decoration-accent/35 decoration-1 underline-offset-2 transition-colors hover:decoration-accent"
              >
                {link[1]}
              </a>
            )
          }
          return <span key={index}>{part}</span>
        }

        return (
          <em key={index} className="italic">
            <PlainText text={part.slice(1, -1)} />
          </em>
        )
      })}
    </span>
  )
}
