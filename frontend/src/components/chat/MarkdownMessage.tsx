import type { ReactNode } from 'react'
import { MessageText } from './MessageText'

interface MarkdownMessageProps {
  text: string
  tone?: 'assistant' | 'user'
}

type Block =
  | { kind: 'paragraph'; text: string }
  | { kind: 'heading'; level: number; text: string }
  | { kind: 'list'; ordered: boolean; start: number; items: string[] }
  | { kind: 'code'; language: string | null; code: string }
  | { kind: 'quote'; text: string }
  | { kind: 'table'; header: string[]; rows: string[][] }
  | { kind: 'rule' }

const headingPattern = /^\s{0,3}(#{1,6})\s+(.*)$/
const orderedItemPattern = /^\s{0,3}(\d{1,4})[.)]\s+(.*)$/
const unorderedItemPattern = /^\s{0,3}[-*+]\s+(.*)$/
const quotePattern = /^\s{0,3}>\s?(.*)$/
const rulePattern = /^\s{0,3}(?:-{3,}|\*{3,}|_{3,})\s*$/
const fencePattern = /^\s{0,3}```\s*([\w-]*)\s*$/
const tableDividerPattern =
  /^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)+\|?\s*$/

function splitRow(line: string) {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim())
}

function parseBlocks(input: string): Block[] {
  const lines = input.replace(/\r\n?/g, '\n').split('\n')
  const blocks: Block[] = []
  let paragraph: string[] = []
  let index = 0

  const flushParagraph = () => {
    if (!paragraph.length) return
    const text = paragraph.join('\n').trim()
    if (text) blocks.push({ kind: 'paragraph', text })
    paragraph = []
  }

  while (index < lines.length) {
    const line = lines[index]

    if (!line.trim()) {
      flushParagraph()
      index += 1
      continue
    }

    const fence = fencePattern.exec(line)
    if (fence) {
      flushParagraph()
      index += 1
      const codeLines: string[] = []
      while (index < lines.length && !/^\s{0,3}```/.test(lines[index])) {
        codeLines.push(lines[index])
        index += 1
      }
      index += 1
      blocks.push({ kind: 'code', language: fence[1] || null, code: codeLines.join('\n') })
      continue
    }

    const heading = headingPattern.exec(line)
    if (heading) {
      flushParagraph()
      blocks.push({ kind: 'heading', level: heading[1].length, text: heading[2].trim() })
      index += 1
      continue
    }

    if (rulePattern.test(line)) {
      flushParagraph()
      blocks.push({ kind: 'rule' })
      index += 1
      continue
    }

    if (line.includes('|') && tableDividerPattern.test(lines[index + 1] ?? '')) {
      flushParagraph()
      const header = splitRow(line)
      index += 2
      const rows: string[][] = []
      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
        rows.push(splitRow(lines[index]))
        index += 1
      }
      blocks.push({ kind: 'table', header, rows })
      continue
    }

    const quote = quotePattern.exec(line)
    if (quote) {
      flushParagraph()
      const quoteLines = [quote[1]]
      index += 1
      while (index < lines.length) {
        const next = quotePattern.exec(lines[index])
        if (!next) break
        quoteLines.push(next[1])
        index += 1
      }
      blocks.push({ kind: 'quote', text: quoteLines.join('\n').trim() })
      continue
    }

    const ordered = orderedItemPattern.exec(line)
    const unordered = ordered ? null : unorderedItemPattern.exec(line)

    if (ordered || unordered) {
      flushParagraph()
      const isOrdered = Boolean(ordered)
      const start = ordered ? Number(ordered[1]) : 1
      const first = ordered ?? unordered!
      const items = [first[first.length - 1]]
      index += 1

      while (index < lines.length) {
        const current = lines[index]

        if (!current.trim()) {
          const next = lines[index + 1] ?? ''
          const sameList = isOrdered
            ? orderedItemPattern.test(next)
            : unorderedItemPattern.test(next)
          if (sameList) {
            index += 1
            continue
          }
          break
        }

        const nextOrdered = orderedItemPattern.exec(current)
        const nextUnordered = nextOrdered ? null : unorderedItemPattern.exec(current)

        if (isOrdered && nextOrdered) {
          items.push(nextOrdered[2])
          index += 1
          continue
        }

        if (!isOrdered && nextUnordered) {
          items.push(nextUnordered[1])
          index += 1
          continue
        }

        if (
          headingPattern.test(current) ||
          rulePattern.test(current) ||
          quotePattern.test(current) ||
          fencePattern.test(current) ||
          tableDividerPattern.test(current)
        ) {
          break
        }

        items[items.length - 1] = `${items[items.length - 1]} ${current.trim()}`
        index += 1
      }

      blocks.push({ kind: 'list', ordered: isOrdered, start, items })
      continue
    }

    paragraph.push(line.replace(/\s+$/, ''))
    index += 1
  }

  flushParagraph()
  return blocks
}

function Heading({ level, children }: { level: number; children: ReactNode }) {
  const Tag = `h${Math.min(level + 2, 6)}` as 'h3' | 'h4' | 'h5' | 'h6'
  return (
    <Tag className="mt-3 mb-1 text-[15px] font-semibold leading-6 text-ink first:mt-0 sm:text-[15.5px]">
      {children}
    </Tag>
  )
}

export function MarkdownMessage({ text, tone = 'assistant' }: MarkdownMessageProps) {
  const blocks = parseBlocks(text)

  return (
    <div className="min-w-0 space-y-2 break-words">
      {blocks.map((block, index) => {
        switch (block.kind) {
          case 'paragraph':
            return <MessageText key={index} text={block.text} tone={tone} />

          case 'heading':
            return (
              <Heading key={index} level={block.level}>
                <MessageText text={block.text} tone={tone} />
              </Heading>
            )

          case 'list':
            return block.ordered ? (
              <ol
                key={index}
                start={block.start}
                className="my-1.5 list-decimal space-y-1 ps-5 marker:font-mono marker:text-[12px] marker:text-accent-text"
              >
                {block.items.map((item, itemIndex) => (
                  <li key={itemIndex} className="ps-0.5">
                    <MessageText text={item} tone={tone} />
                  </li>
                ))}
              </ol>
            ) : (
              <ul
                key={index}
                className="my-1.5 list-disc space-y-1 ps-5 marker:text-accent/70"
              >
                {block.items.map((item, itemIndex) => (
                  <li key={itemIndex} className="ps-0.5">
                    <MessageText text={item} tone={tone} />
                  </li>
                ))}
              </ul>
            )

          case 'code':
            return (
              <div
                key={index}
                className="my-2 overflow-x-auto rounded-lg border border-rule bg-inset px-3 py-2.5"
              >
                <pre className="font-mono text-[12.5px] leading-5 text-ink">
                  <code>{block.code}</code>
                </pre>
              </div>
            )

          case 'quote':
            return (
              <blockquote
                key={index}
                className="my-2 border-s-2 border-accent/40 ps-3 text-muted"
              >
                <MessageText text={block.text} tone={tone} />
              </blockquote>
            )

          case 'table':
            return (
              <div
                key={index}
                className="my-2 overflow-x-auto rounded-lg border border-rule"
              >
                <table className="w-full min-w-[320px] border-collapse text-left text-[13px] leading-5">
                  <thead>
                    <tr className="bg-inset">
                      {block.header.map((cell, cellIndex) => (
                        <th
                          key={cellIndex}
                          className="border-b border-rule px-3 py-2 text-[11px] font-semibold tracking-wide text-muted uppercase"
                        >
                          <MessageText text={cell} tone={tone} />
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {block.rows.map((row, rowIndex) => (
                      <tr key={rowIndex} className="border-t border-rule">
                        {row.map((cell, cellIndex) => (
                          <td key={cellIndex} className="px-3 py-2 align-top">
                            <MessageText text={cell} tone={tone} />
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )

          case 'rule':
            return <hr key={index} className="my-3 border-rule" />
        }
      })}
    </div>
  )
}
