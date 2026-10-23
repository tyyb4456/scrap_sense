import { useEffect, useRef, useState, type FormEvent } from 'react'
import { errorMessage, sendMessage } from '../lib/api'
import { useAccessToken } from '../lib/useAccessToken'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
}

const greeting: ChatMessage = {
  id: 'greeting',
  role: 'assistant',
  content:
    'Assalam-o-alaikum. Tell me about a scrap sale or ask what a material is worth.',
}

export function Chat() {
  const getToken = useAccessToken()
  const [messages, setMessages] = useState<ChatMessage[]>([greeting])
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, sending])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const text = draft.trim()
    if (!text || sending) {
      return
    }

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
    }
    setMessages((current) => [...current, userMessage])
    setDraft('')
    setError(null)
    setSending(true)

    try {
      const response = await sendMessage(await getToken(), text)
      setMessages((current) => [
        ...current,
        { id: crypto.randomUUID(), role: 'assistant', content: response.reply },
      ])
    } catch (sendError) {
      setError(errorMessage(sendError))
    } finally {
      setSending(false)
    }
  }

  return (
    <section className="flex h-[calc(100svh-8.5rem)] min-h-[28rem] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex-1 space-y-4 overflow-y-auto p-4 sm:p-6" aria-live="polite">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <p
              className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                message.role === 'user'
                  ? 'rounded-br-sm bg-emerald-600 text-white'
                  : 'rounded-bl-sm bg-slate-100 text-slate-800'
              }`}
            >
              {message.content}
            </p>
          </div>
        ))}

        {sending ? (
          <div className="flex justify-start">
            <p className="rounded-2xl rounded-bl-sm bg-slate-100 px-4 py-3 text-sm text-slate-500">
              ScrapSense is thinking…
            </p>
          </div>
        ) : null}
        <div ref={endRef} />
      </div>

      {error ? (
        <p className="border-t border-rose-100 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {error}
        </p>
      ) : null}

      <form
        onSubmit={handleSubmit}
        className="flex items-end gap-2 border-t border-slate-200 bg-white p-3 sm:p-4"
      >
        <label htmlFor="chat-message" className="sr-only">
          Message
        </label>
        <textarea
          id="chat-message"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              event.currentTarget.form?.requestSubmit()
            }
          }}
          rows={2}
          maxLength={4000}
          placeholder="Example: aaj maine 2 kilo plastic becha, 300 rupay mila"
          className="max-h-40 min-h-12 flex-1 resize-none rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200"
        />
        <button
          type="submit"
          disabled={sending || draft.trim().length === 0}
          className="rounded-xl bg-emerald-600 px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {sending ? 'Sending…' : 'Send'}
        </button>
      </form>
    </section>
  )
}
